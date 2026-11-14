"""
Pydantic data models for Enterprise Multi-Vendor Lifecycle Scraper.
Database-ready normalization, semantic firmware cleaning, vendor-exact terminology,
UTC date normalization, and record fingerprinting for append/upsert operations.
"""

import calendar
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scraper.security import inspect_security_threats


def normalize_firmware_version(raw_firmware: Optional[str]) -> Optional[str]:
    """
    Cleans and normalizes firmware strings to database-ready semantic versions (e.g. '1.0.0', '2.1.0').
    Hardware-only items or non-versioned parts are normalized to None (SQL NULL).
    """
    if not raw_firmware or not isinstance(raw_firmware, str):
        return None

    cleaned = raw_firmware.strip()
    if not cleaned or cleaned.lower() in ("n/a", "none", "null", "all", "all revisions", "all firmware revisions", "unknown", "hardware", "hardware revision"):
        return None

    # Pattern 1: Semantic 3 or 4-part version: 1.2.3 or 1.2.3.4 or v1.2.3
    m_semver = re.search(r'\b[vV]?(\d+\.\d+\.\d+(?:\.\d+)?)\b', cleaned)
    if m_semver:
        return m_semver.group(1)

    # Pattern 2: 2-part version: 1.0 or Ver. 2.1
    m_twopart = re.search(r'\b(?:[vV]|ver\.?|version)?\s*(\d+\.\d+)\b', cleaned, re.IGNORECASE)
    if m_twopart:
        return f"{m_twopart.group(1)}.0"

    # Pattern 3: Revision code (e.g. Rev. D, Rev 3) - strictly 1 to 3 chars, not the word 'Revision'
    m_rev = re.search(r'\bRev\.?\s*([A-Z0-9]{1,3})\b', cleaned, re.IGNORECASE)
    if m_rev and m_rev.group(1).lower() not in ("isi", "isio", "ision"):
        return f"Rev {m_rev.group(1).upper()}"

    # Pattern 4: Japanese / Vendor code like V0700 -> 7.0.0
    m_code = re.search(r'\bV0?(\d)(\d)00\b', cleaned, re.IGNORECASE)
    if m_code:
        return f"{m_code.group(1)}.{m_code.group(2)}.0"

    return None


REGIONAL_TOKEN_STR = (
    r'(?:[A-Za-z]{2,3}|Global|Worldwide|ROW|North America|NA|EMEA|APAC|'
    r'Europe|Canada|Japan|US|UK|EU|AU|JP|CN|WW|DE|FR|IT|ES|IN|BR|MX)'
)
REGIONAL_SUFFIX_PATTERN = re.compile(
    r'\s*[\(\[]\s*' + REGIONAL_TOKEN_STR + r'(?:\s*[-/,\s]+\s*' + REGIONAL_TOKEN_STR + r')*\s*[\)\]]\s*$',
    re.IGNORECASE
)


def strip_regional_suffix(model_or_alias: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Strips regional/country suffix from model identifiers, aliases, and replacements.
    Examples:
      'GR60 (EU)' -> ('GR60', 'EU')
      'GR60 (UK)' -> ('GR60', 'UK')
      'MS220-8P (US)' -> ('MS220-8P', 'US')
      'GR12-HW (US - EU)' -> ('GR12-HW', 'US - EU')
      'GR62-HW (US - UK - EU)' -> ('GR62-HW', 'US - UK - EU')
      'Product (Canada)' -> ('Product', 'Canada')
    """
    if not model_or_alias or not isinstance(model_or_alias, str):
        return model_or_alias, None
    clean = model_or_alias.strip()
    m = REGIONAL_SUFFIX_PATTERN.search(clean)
    if m:
        extracted_reg = clean[m.start():].strip(" ()[]")
        clean_model = clean[:m.start()].strip()
        if clean_model:
            return clean_model, extracted_reg
    return clean, None


COOKIE_AND_POLICY_SUBSTRINGS = {
    "performance cookies", "cookie notice", "manage consent preferences", "consent preferences",
    "strictly necessary cookies", "functional cookies", "targeting cookies", "cookies settings",
    "cookie policy", "cookie", "privacy policy", "terms of use", "terms and conditions",
    "terms of service", "all rights reserved", "privacy statement", "legal notice",
    "cookie preferences", "manage cookies", "copyright notice"
}

EXACT_DISALLOWED_MODEL_TOKENS = {
    # Geographic / Regional
    "global", "americas", "asia-pacific", "europe", "europe, cis, middle east & africa",
    "north america", "latin america", "japan", "china", "germany", "france", "united states",
    # Website Navigation / Legal / Web Chrome / URL Slugs
    "terms", "terms-canada", "terms-us", "terms-conditions", "terms-of-use", "terms-of-service",
    "terms and conditions", "terms of use", "terms of service", "tools", "top-connect",
    "text-display", "timing-relays", "privacy", "privacy policy", "imprint", "legal",
    "legal notice", "disclaimer", "cookie-policy", "site map", "site-map", "sitemap", "contact",
    "contact us", "about", "about us", "sustainability", "news", "newsroom",
    "follow us", "search", "home", "products", "all products",
    "solutions", "support", "downloads", "training", "documentation", "resources", "overview",
    "specifications", "features", "details", "comments", "notes", "action", "status", "stage",
    "category", "family", "series", "main series", "complete series", "complete serie", "expansion units",
    "all models", "all modules", "all units", "the whole series", "whole series", "affects the complete series",
    "includes the whole series", "includes all modules", "includes the following models",
    "includes the following models:", "replacement manual", "qans - main series", "ans - main series",
    "ana/ann/anu - main series", "n/a", "none", "null", "nan", "unknown", "tbd", "undefined",
    "mini", "micro", "nano", "sfp", "sfp+", "qsfp", "qsfp+", "accessories", "licenses",
    "antenna mounts", "mount kits", "power supplies and fans", "power supplies",
    # Hardware packaging, accessories, categories rejected by LLM
    "controllers", "controller", "vision components", "vision component", "cables", "cable",
    "trunk case", "carrying case", "battery adapter", "sub-batterypack", "charger",
    "wall plug", "solar", "indoor", "outdoor", "booster amplifier", "measurement system",
    "5y", "7y", "10y", "1y", "3y", "1 year", "3 year", "5 year", "7 year", "10 year",
    "gp-ib control system", "ppp",
    "document", "document id", "page", "lang page", "security level", "external en",
    "all rights reserved", "copyright",
    "model", "models", "part number", "part numbers", "product", "item", "description",
    "catalog number", "order number", "order code", "article number", "type code",
    "model number", "model name", "product name", "product number", "part no", "part no.",
    "effective date", "discontinuation date", "end of life date", "last time buy date",
    "end of support date", "end of service date", "replacement model", "replacement part",
    "recommended replacement", "successor", "successor model", "migration path",
    "skip to content", "skip to main content", "menu", "back to top", "read more", "learn more",
    "view details", "see all", "click here", "show more", "load more", "page not found",
    "shopping cart", "cart", "checkout", "sign in", "log in", "register", "my account",
    "feedback", "newsletter", "subscribe", "share", "print",
    # Multilingual UI tokens (Japanese, German, French, Chinese)
    "目次", "お問い合わせ", "製品情報", "サイト利用規約", "個人情報保護方針", "サイトマップ", "詳細はこちら",
    "ダウンロード", "サポート", "ホーム", "製品", "形名", "形式", "型番", "品名", "生産終了日",
    "修理対応終了日", "代替品", "代替推奨品", "標準価格", "納期", "備考", "仕様", "概要",
    "inhaltsverzeichnis", "kontakt", "kontaktieren sie uns", "impressum", "datenschutz",
    "weitere informationen", "startseite", "produkte", "artikelnummer", "bestellnummer",
    "nachfolgeprodukt", "auslaufdatum", "ersatzteil", "hinweise", "technische daten",
    "table des matières", "contactez-nous", "mentions légales", "politique de confidentialité",
    "plan du site", "en savoir plus", "téléchargements", "accueil", "référence",
    "produit de remplacement", "date d'arrêt", "remarques", "caractéristiques",
    "目录", "联系我们", "隐私政策", "网站地图", "了解更多", "下载中心", "首页", "产品型号",
    "订货号", "停产日期", "替代型号", "产品概述", "技术规格"
}

CONVERSATIONAL_STOP_WORDS = {
    "this", "that", "these", "those", "have", "been", "will", "would", "could", "should",
    "please", "contact", "refer", "customer", "support", "service", "available", "subject",
    "change", "without", "notice", "information", "regarding", "following", "replaced",
    "discontinued", "successor", "representative", "distributor", "further", "assistance",
    "bulletin", "technical", "announcement", "effective", "immediately"
}

LIFECYCLE_STATUS_TOKENS = {
    "discontinued", "discontinued model", "discontinued product",
    "end of life", "end of life (eol)", "eol",
    "end of sale", "end of sales", "end of service", "end of service (eos)", "eos",
    "end of service life", "end of service life (eosl)", "eosl",
    "end of support", "last date of support", "ldos",
    "end of availability", "end of availability (eoa)", "eoa",
    "last time buy", "last time buy (ltb)", "ltb", "last order date", "final order date",
    "phase out", "phase-out", "phaseout", "phase-out product", "phase-out announced",
    "obsolete", "active", "active mature", "classic", "limited", "stop shipment",
    "product cancellation", "product discontinuation", "announced discontinuation",
    "delivery release", "maintenance only", "in production", "active / in production",
    # Multilingual status terms
    "生産終了", "販売終了", "製造中止", "最終受注", "最終注文", "最終出荷", "修理対応終了", "保守終了",
    "auslauftyp", "abkündigung", "produktabkündigung", "lieferstopp", "serviceende",
    "fin de vie", "fin de support", "fin de commercialisation", "arrêt de commercialisation",
    "utgående produkt", "sista orderdatum", "service upphör",
    "停产", "停售", "停产公告", "终止服务", "终止支持", "最后订购",
    "단종", "생산종料", "판매종료", "지원종료"
}

TABLE_HEADER_TOKENS = {
    "model", "models", "model name", "model no", "model no.", "model number", "model #",
    "part", "parts", "part name", "part no", "part no.", "part number", "part numbers", "part #",
    "catalog no", "catalog no.", "catalog number", "catalog #",
    "order no", "order no.", "order number", "order code", "ordering code",
    "article no", "article no.", "article number", "article code", "type code", "type designation",
    "item", "items", "item no", "item no.", "item number", "item #", "item description",
    "product name", "product line", "product code", "product family", "product description",
    "discontinued model", "discontinued models", "discontinued product", "discontinued products",
    "discontinued part", "discontinued parts", "discontinued items",
    "replacement model", "replacement models", "replacement part", "replacement parts",
    "replacement product", "replacement products", "recommended replacement",
    "successor", "successor model", "successor models", "successor part", "successor parts",
    "alternate model", "substitute model",
    "discontinuation date", "effective date", "announcement date", "phase out date",
    "last order date", "last time buy date", "final order date", "end of support date", "end of service date",
    "series name", "product series", "lifecycle status", "current status", "stage", "category",
    "quantity", "qty", "unit price", "list price", "price", "total", "subtotal",
    "availability", "stock status", "lead time", "action", "actions", "details",
    "datasheet", "manual", "specifications", "features", "overview",
    "milestone", "milestones", "milestone name", "milestones name", "definition", "definitions",
    "key milestone", "key milestones", "milestone date", "milestone dates",
    # Japanese
    "形名", "形式", "型番", "品名", "品目", "仕様", "概要", "代替品", "代替推奨品",
    "標準価格", "納期", "備考", "後継品", "後継機種", "対象機種", "対象形名", "旧機種", "現行機種",
    # German
    "artikelnummer", "bestellnummer", "typbezeichnung", "nachfolgeprodukt", "auslaufdatum",
    "ersatztyp", "bezeichnung", "produktlinie", "warengruppe", "nachfolger", "lieferstopp",
    # French
    "référence", "reference", "désignation", "designation", "code article", "produit de remplacement",
    "date d'arrêt", "successeur", "caractéristiques",
    # Chinese
    "产品型号", "订货号", "产品名称", "替代型号", "停产型号", "推荐替代", "产品描述", "物料编码",
    # Spanish / Italian
    "código", "codigo", "número de parte", "numero de parte", "modelo sustituto", "referencia", "descripción",
    "codice", "codice articolo", "modello", "prodotto sostitutivo"
}

# Pure electrical, mechanical, or physical engineering ratings/units masquerading as model numbers
SPECIFICATION_PATTERN = re.compile(
    r'^(?:'
    # Engineering units: e.g. 24VDC, 100-240VAC, 50/60Hz, 0.75kW, 4-20mA, 10A, 250g, 100mm, 10bar, 100psi, 120ohm
    r'\d+(?:\.\d+)?(?:\s*[-~/]\s*\d+(?:\.\d+)?)?\s*(?:vac|vdc|vac/vdc|vdc/vac|v\s*ac|v\s*dc|v|a|ma|w|kw|mw|hp|hz|khz|mhz|ghz|ohm|kohm|mohm|rpm|bar|psi|kg|g|mg|mm|cm|m)'
    r'|'
    # Electrical phase ratings: e.g. 1-phase, 3-phase, single-phase, three-phase
    r'(?:\d+|single|three|poly|split)[- ]?phase'
    r'|'
    # Ingress Protection or NEMA enclosures: IP67, IP20, NEMA 4X, NEMA 12
    r'(?:ip\s*[0-6][0-9][a-z]?|nema\s*\d+[a-z]?)'
    r'|'
    # Physical dimensions: 100x50x25mm, 100 x 50 mm, 50x50mm
    r'\d+(?:\.\d+)?\s*[xX*]\s*\d+(?:\.\d+)?(?:\s*[xX*]\s*\d+(?:\.\d+)?)?\s*(?:mm|cm|m|in|inch)?'
    r'|'
    # Standalone connector / serial interfaces: RJ45, M12, M8, RS-485, USB-C, SFP
    r'(?:rj45|rj11|rj12|m12|m8|m5|rs-?232[a-z]?|rs-?485[a-z]?|rs-?422[a-z]?|usb[- ]?[a-c]|usb[- ]?[1-3](?:\.[0-2])?|sfp\+?|qsfp\+?)'
    r')$',
    re.IGNORECASE
)

# Commercial prices, currency values, stock, availability, and order quantity terms
PRICE_AND_COMMERCIAL_PATTERN = re.compile(
    r'^(?:'
    r'[$€£¥₹]\s*[\d,]+(?:\.\d+)?'
    r'|'
    r'(?:usd|eur|gbp|jpy|cny|inr|cad|aud|chf)\s*[\d,]+(?:\.\d+)?'
    r'|'
    r'[\d,]+(?:\.\d+)?\s*(?:usd|eur|gbp|jpy|cny|inr|cad|aud|chf)'
    r'|'
    r'[\d,]+\.\d{2}'
    r'|'
    r'in\s+stock|out\s+of\s+stock|available|unavailable|backorder|on\s+backorder|'
    r'call\s+for\s+price|contact\s+factory|contact\s+us|request\s+quote|rfq|'
    r'lead\s*time\b.*|qty\b.*|quantity\b.*|moq\b.*'
    r')$',
    re.IGNORECASE
)

# UI Navigation artifacts: breadcrumb trails, pagination markers, search noise, button texts
UI_AND_BREADCRUMB_PATTERN = re.compile(
    r'^(?:'
    r'.*(?:\s+[>»]\s+|\s+->\s+).*'
    r'|'
    r'page\s+\d+(?:\s*(?:of|/)\s*\d+)?|next\s+page|previous\s+page|first\s+page|last\s+page|'
    r'showing\s+\d+.*|results\s+\d+.*|viewing\s+\d+.*'
    r'|'
    r'click\s+here|read\s+more|learn\s+more|view\s+details|see\s+details|'
    r'download\s+pdf|download\s+now|search\s+results|back\s+to\s+top|go\s+to\s+top'
    r')$',
    re.IGNORECASE
)

# Generic Industrial / IT product categories, solution overviews, and marketing classifications
GENERIC_PRODUCT_CATEGORY_TOKENS = {
    "human machine interface", "human machine interfaces", "hmi", "hmis",
    "circuit and load protection", "circuit-and-load-protection",
    "circuit breaker & load protection", "circuit breakers", "motor circuit protectors",
    "variable frequency drive", "variable frequency drives", "variable frequency drives (vfds)", "vfd", "vfds",
    "cubic modular system", "cubic modular system enclosures", "cubic-modular-system",
    "programmable controller", "programmable controllers", "plc", "plcs",
    "programmable automation controller", "programmable automation controllers", "pac", "pacs",
    "distributed control system", "distributed control systems", "dcs",
    "industrial automation", "industrial computers", "industrial computers and monitors",
    "motion control", "motor control", "motor controls",
    "sensors and switches", "safety products", "safety components",
    "lighting and relays", "condition monitoring",
    "network security and infrastructure", "networks and security", "ethernet networks", "ethernet-networks",
    "power supplies", "power supply", "in-cabinet distributed i/o", "distributed i/o",
    "allen-bradley", "allen-bradley products", "rockwell automation",
    "low voltage ac drive", "architecture drive",
    "remote access router", "stratix 4300 remote access router",
    "5g-routers", "5g routers", "routers", "switches", "gateways", "firewalls",
    "web-ui", "web ui", "timing-relays", "safety-relays", "safety relays",
    "soft-starter", "soft starter", "soft-starters", "soft starters",
    "air-circuit-breakers", "air circuit breakers", "molded-case-circuit-breaker",
    "molded case circuit breaker", "solid-state-relay", "solid state relay",
    "intelligent-link-module", "intelligent link module",
    "1718 ex i/o", "1718-ex-i-o", "20g-powerflex-755t", "2098-ultraware-software",
    "2094-kinetix-6000m-integrated"
}

# Boilerplate non-model phrases commonly appearing in replacement fields across vendors
BOILERPLATE_REPLACEMENT_TOKENS = {
    "contact repair & replacement", "contact repair and replacement", "contact repair",
    "not applicable", "n/a", "none", "-", "--", "na",
    "see product details", "view product details", "see details", "product details",
    "contact local distributor or sales office", "contact local distributor", "contact distributor",
    "contact local sales office", "contact sales office", "contact local sales", "contact sales",
    "contact customer support", "contact support", "call for replacement",
    "repair only", "repair service", "repair services", "repair & replacement services",
    "no planned replacement", "no planned ra replacement", "no replacement", "no ra replacement",
    "refer to compatibility", "refer to migration solutions", "consult sales", "consult factory",
    "direct replacement", "engineering replacement", "functional replacement",
    "custom engineered solution", "replacement available",
    "contact your local distributor", "contact your authorized distributor"
}

# Table row index numbers: 1, 2, 99, 100, #1, #25 (table row numbers, not product models)
ROW_INDEX_PATTERN = re.compile(r'^#?\d{1,3}$')


def is_valid_replacement_model(name: Optional[str]) -> bool:
    """
    Validates whether a replacement string represents an authentic successor hardware/software model.
    Strictly rejects boilerplate instructional text (e.g. 'CONTACT REPAIR & REPLACEMENT', 'NOT APPLICABLE',
    'No planned RA replacement', 'No Honeywell Replacement - contact NCR', 'See Product Details', 'Engineering Replacement')
    and ensures only genuine model SKUs are populated in the replacement column.
    """
    if not name or not isinstance(name, str):
        return False
    cleaned = name.strip()
    if not cleaned or len(cleaned) < 2 or len(cleaned) > 100:
        return False
    c_lower = cleaned.lower()
    c_norm = re.sub(r'[\s_\-]+', ' ', c_lower).strip()
    if c_lower in ("n/a", "none", "null", "nan", "-", "--", "na", "unknown") or c_norm in ("n/a", "none", "null", "nan", "na", "unknown"):
        return False
    if re.search(r'\b(?:contact|consult|representative|distributor|no\s+.*replacement|no\s+replacement|not\s+applicable|refer\s+to|see\s+|view\s+|call\s+|repair\s+only|repair\s+service)\b', c_norm):
        return False
    if c_lower in BOILERPLATE_REPLACEMENT_TOKENS or c_norm in BOILERPLATE_REPLACEMENT_TOKENS:
        return False
    for phrase in BOILERPLATE_REPLACEMENT_TOKENS:
        if phrase in c_norm and len(phrase) >= 6:
            return False
    # Must also pass general product model validity
    return is_valid_product_model(cleaned)


def is_valid_product_model(name: Optional[str]) -> bool:
    """
    Validates whether an extracted string represents a genuine industrial hardware/software model name.
    Strictly permits alphanumeric characters and sensible standard symbols (- / : . _ + & ( ) # space).
    Rejects corrupt data, mojibake, control characters, decorative icons/emojis, web navigation strings,
    cookie consent headers, URLs, and generic phrases.
    """
    if not name or not isinstance(name, str):
        return False
    # Enterprise Security Incident Check: Reject SQLi, XSS, Path Traversal, Command Injection
    is_th, _, _ = inspect_security_threats(name, field_name="model_name")
    if is_th:
        return False

    cleaned = name.strip()
    if len(cleaned) < 2 or len(cleaned) > 120:
        return False

    # Check for formula injection prefix (e.g. '=Model or =Model)
    check_str = cleaned
    if check_str.startswith("'"):
        check_str = check_str[1:]
    if check_str.startswith(("=", "+", "-", "@")):
        check_str = check_str[1:].strip()

    if len(check_str) < 2:
        return False

    # Reject corrupt characters, control characters, replacement glyphs, emojis, decorative symbols
    if re.search(r'[\x00-\x1f\x7f-\x9f\ufeff\u200b\u200c\u200d\ufffd§©®™★•►✓✗▪▫◆▲▼※~^$%=|\\{}<>;"`\']', check_str):
        return False

    # Reject markdown links: [ Name ](url) or plain URLs
    if check_str.startswith("[") or "http://" in check_str or "https://" in check_str or "](" in check_str:
        return False
    c_lower = check_str.lower()
    for sub in COOKIE_AND_POLICY_SUBSTRINGS:
        if sub in c_lower:
            return False
    if c_lower in EXACT_DISALLOWED_MODEL_TOKENS:
        return False
    # Reject table header and column labels masquerading as product models
    if c_lower in TABLE_HEADER_TOKENS:
        return False
    # Reject generic product categories, solution overviews, and marketing classifications
    if c_lower in GENERIC_PRODUCT_CATEGORY_TOKENS:
        return False
    c_slug = re.sub(r'[\-_/]+', ' ', c_lower).strip()
    if c_slug in GENERIC_PRODUCT_CATEGORY_TOKENS:
        return False
    # Reject table row index numbers (e.g. 1, 2, 99, 100, #1, #25)
    if ROW_INDEX_PATTERN.match(check_str):
        return False
    # Reject pure engineering specifications (electrical, mechanical, ingress, connector standards)
    if SPECIFICATION_PATTERN.match(check_str):
        return False
    # Reject commercial pricing, currency values, stock, and order terms
    if PRICE_AND_COMMERCIAL_PATTERN.match(check_str):
        return False
    # Reject UI navigation, breadcrumb paths, pagination markers, button noise
    if UI_AND_BREADCRUMB_PATTERN.match(check_str):
        return False
    # Reject lifecycle statuses masquerading as product models
    if c_lower in LIFECYCLE_STATUS_TOKENS:
        return False
    # Reject lifecycle milestone descriptions masquerading as product models
    if any(m in c_lower for m in ("end of sale", "end of life", "last ship", "last date of support", "end of support", "sw maintenance", "routine failure", "service attachment", "contract renewal", "order date", "ship date")) and any(d in c_lower for d in ("date", "announcement", "milestone")):
        return False

    # Reject documentation artifacts and manuals masquerading as product models
    if any(c_lower.endswith(sfx) for sfx in (" manual", " manuals", " guide", " guides", " datasheet", " datasheets", " brochure", " handbook", " literature", "-literature", "-brochure", "-whitepaper", "-case-study")):
        return False
    if any(k in c_lower for k in ("replacement manual", "instruction manual", "user manual", "hardware manual", "programming manual", "product-line-literature", "product line literature", "case-study", "case study", "whitepaper", "press-release")):
        return False

    # Reject series descriptors, lead-in phrases, and headings masquerading as product models
    if any(c_lower.endswith(sfx) for sfx in ("- main series", " main series", " sub series", " product series", " complete serie", " power supplies and fans", " power supplies", " mount kits", " antenna mounts", " accessories", " licenses")):
        return False
    if any(k in c_lower for k in ("main series", "includes the following", "affects the following", "following models", "replacement manual")):
        return False
    # Reject pure date strings or strings containing calendar dates (e.g. 2023-03-31, April 30 - 2026, 15-May-2024, or 4-digit years)
    if not is_well_known_os_or_software(model_name=check_str):
        if parse_to_utc_iso(check_str):
            return False
        if re.search(r'\b(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b[^\w\n]*\d{1,2}[^\w\n]*(?:19|20)\d{2}\b', c_lower):
            return False
        if re.search(r'\b\d{1,2}[^\w\n]*(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b[^\w\n]*(?:19|20)\d{2}\b', c_lower):
            return False
        if re.search(r'\b(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b[^\w\n]*(?:19|20)\d{2}\b', c_lower):
            return False
        if re.search(r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-]+(?:\d{1,2}[\s\-]+)?\d{2,4}\b', c_lower):
            return False
        if re.search(r'\b(?:\d{1,2}[\s\-]+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-]+\d{2,4}\b', c_lower):
            return False
        if re.match(r'^(?:(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{1,2}[-/\s]+[A-Za-z]{3,9}[-/\s]+(?:19|20)\d{2}|(?:19|20)\d{2}[-/.]\d{1,2})$', check_str):
            return False
        if re.match(r'^(?:19|20)\d{2}$', check_str):
            return False
    # Reject strings that start with conversational / instructional text
    if any(c_lower.startswith(p) for p in ("consult ", "see ", "official ", "click ", "read ", "download ", "view ", "affects ", "please ", "refer ")):
        return False

    # Reject strings with conversational sentence structure (3+ conversational stop words)
    tokens = set(re.findall(r'\b[a-z]{3,}\b', c_lower))
    if len(tokens.intersection(CONVERSATIONAL_STOP_WORDS)) >= 3:
        return False

    # Reject overly long strings without digits (prose or narrative headings)
    if len(check_str) > 50 and not re.search(r'\d', check_str) and not is_well_known_os_or_software(model_name=check_str):
        return False

    # Must contain at least one alphanumeric character
    if not re.search(r'[A-Za-z0-9]', check_str):
        return False

    # Strictly enforce alphanumeric + standard sensible symbols: - / : . _ + & ( ) # space ,
    if not re.match(r'^[A-Za-z0-9\-_/:.+&()# ,]+$', check_str):
        return False

    return True


WELL_KNOWN_OS_KEYWORDS = {
    "linux", "debian", "windows", "ubuntu", "rhel", "redhat", "red hat",
    "centos", "fedora", "suse", "sles", "arch", "alpine", "rocky", "almalinux",
    "oracle linux", "freebsd", "openbsd", "netbsd", "solaris", "sunos", "aix",
    "hp-ux", "vxworks", "qnx", "freertos", "zephyr", "integrity", "android",
    "ios", "macos", "darwin", "unix"
}

SOFTWARE_CATEGORY_TERMS = {
    "software", "application", "operating system", "os", "firmware package",
    "scada", "scada software", "engineering software", "suite", "driver", "middleware"
}


def is_well_known_os_or_software(
    category: Optional[str] = None,
    os_name: Optional[str] = None,
    model_name: Optional[str] = None
) -> bool:
    """
    Checks if a record is an operating system, software application, or well-known OS entry
    (e.g., Linux, Debian, Windows, Ubuntu, RHEL).
    Model name is ONLY permitted to be empty for these entries; hardware records strictly require model_name.
    """
    cat_str = (category or "").strip().lower()
    os_str = (os_name or "").strip().lower()
    mod_str = (model_name or "").strip().lower()

    # 1. Check if category matches software or operating system
    for term in SOFTWARE_CATEGORY_TERMS:
        if term == cat_str or term in cat_str:
            return True

    # 2. Check if os_name, model_name, or category matches well-known OS keywords
    for target in (os_str, mod_str, cat_str):
        if not target:
            continue
        for kw in WELL_KNOWN_OS_KEYWORDS:
            if kw == target or re.search(r'\b' + re.escape(kw) + r'\b', target):
                return True

    return False


def parse_to_utc_iso(date_val: Optional[str]) -> Optional[str]:
    """
    Normalizes any date string (ISO, US, European, Asian, or text) to standard UTC ISO 8601 format:
    YYYY-MM-DDTHH:MM:SSZ.
    Handles invalid days (e.g. Nov 31 typos) by clamping to the valid month end.
    """
    if not date_val or not isinstance(date_val, str):
        return None

    cleaned = date_val.strip()
    if not cleaned or cleaned.lower() in ("n/a", "none", "tbd", "unknown", "announced"):
        return None

    # Remove brackets, parentheses or trailing text
    cleaned = re.sub(r'[\(\[\{].*?[\)\]\}]', '', cleaned).strip()

    # Strip romance language connecting words (e.g. '15 de Mayo de 2026' -> '15 Mayo 2026')
    cleaned = re.sub(r'\b(?:de|del|le|du)\b', ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    # Normalize commas and dashes in dates (e.g. "September, 2024" -> "September 2024", "April 30 - 2026" -> "April 30 2026")
    cleaned = re.sub(r'([A-Za-z]+)\s+(\d{1,2})\s*[-,\s]+\s*(\d{2,4})', r'\1 \2 \3', cleaned)
    cleaned = re.sub(r'([A-Za-z]+),\s*(\d{2,4})', r'\1 \2', cleaned)
    cleaned = re.sub(r'(\d{1,2})\s+([A-Za-z]+),\s*(\d{2,4})', r'\1 \2 \3', cleaned)
    cleaned = re.sub(r'([A-Za-z]+)\s+(\d{1,2}),\s*(\d{2,4})', r'\1 \2 \3', cleaned)

    # Normalize German, French, Spanish, Italian month names to English
    intl_months = {
        # German
        r'\bjanuar\b': "January",
        r'\bfebruar\b': "February",
        r'\bmärz\b': "March",
        r'\bmaerz\b': "March",
        r'\bmai\b': "May",
        r'\bjuni\b': "June",
        r'\bjuli\b': "July",
        r'\boktober\b': "October",
        r'\bdezember\b': "December",
        # French
        r'\bjanvier\b': "January",
        r'\bf[ée]vrier\b': "February",
        r'\bmars\b': "March",
        r'\bavril\b': "April",
        r'\bjuin\b': "June",
        r'\bjuillet\b': "July",
        r'\bao[uû]t\b': "August",
        r'\bseptembre\b': "September",
        r'\boctobre\b': "October",
        r'\bnovembre\b': "November",
        r'\bd[ée]cembre\b': "December",
        # Spanish / Italian
        r'\benero\b': "January",
        r'\bfebrero\b': "February",
        r'\bmarzo\b': "March",
        r'\babril\b': "April",
        r'\bmayo\b': "May",
        r'\bmaggio\b': "May",
        r'\bgiugno\b': "June",
        r'\bluglio\b': "July",
        r'\bagosto\b': "August",
        r'\bsettembre\b': "September",
        r'\bseptiembre\b': "September",
        r'\bnoviembre\b': "November",
        r'\bdiciembre\b': "December",
        r'\bdicembre\b': "December",
    }
    for pat, e_month in intl_months.items():
        cleaned = re.sub(pat, e_month, cleaned, flags=re.IGNORECASE)

    # Pattern: Quarter milestones (e.g. Q1 2025, 2025-Q3, 4Q2026, Q2/2024, Q3/25, FY25 Q3, Q1 FY26)
    m_q1 = re.search(r'\b(?:Q([1-4])[\s\/-]*(?:FY|CY)?\s*(\d{2,4})|(?:FY|CY)?\s*(\d{2,4})[\s\/-]*Q([1-4])|([1-4])Q[\s\/-]*(?:FY|CY)?\s*(\d{2,4}))\b', cleaned, re.IGNORECASE)
    if m_q1:
        q = int(m_q1.group(1) or m_q1.group(4) or m_q1.group(5))
        raw_y = int(m_q1.group(2) or m_q1.group(3) or m_q1.group(6))
        y = (2000 + raw_y) if raw_y < 100 else raw_y
        q_month_day = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
        m, d = q_month_day[q]
        return _safe_make_utc(y, m, d)

    # Pattern: Half-year milestones (e.g. H1 2026, 2H2025, 2026-H2, H2/25)
    m_h = re.search(r'\b(?:H([1-2])[\s\/-]*(?:FY|CY)?\s*(\d{2,4})|(?:FY|CY)?\s*(\d{2,4})[\s\/-]*H([1-2])|([1-2])H[\s\/-]*(?:FY|CY)?\s*(\d{2,4}))\b', cleaned, re.IGNORECASE)
    if m_h:
        h = int(m_h.group(1) or m_h.group(4) or m_h.group(5))
        raw_y = int(m_h.group(2) or m_h.group(3) or m_h.group(6))
        y = (2000 + raw_y) if raw_y < 100 else raw_y
        m, d = (6, 30) if h == 1 else (12, 31)
        return _safe_make_utc(y, m, d)

    # Pattern: Japanese/Asian date with day: 2026年9月30日
    m_asian = re.search(r'(\d{4})[年/\.-](\d{1,2})[月/\.-](\d{1,2})日?', cleaned)
    if m_asian:
        y, m, d = int(m_asian.group(1)), int(m_asian.group(2)), int(m_asian.group(3))
        return _safe_make_utc(y, m, d)

    # Pattern: Japanese/Asian year and month only: 2026年9月 -> clamp to month end
    m_asian_m = re.search(r'(\d{4})[年/\.-](\d{1,2})月', cleaned)
    if m_asian_m:
        y, m = int(m_asian_m.group(1)), int(m_asian_m.group(2))
        return _safe_make_utc(y, m, 31)

    # Pattern: Standard YYYY-MM-DD or YYYY/MM/DD or YYYY.MM.DD
    m_iso = re.search(r'(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})', cleaned)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        return _safe_make_utc(y, m, d)

    # Pattern: YYYY.MM or YYYY-MM or YYYY/MM (Year and month only)
    m_ym = re.fullmatch(r'(\d{4})[-/\.](\d{1,2})', cleaned)
    if m_ym:
        y, m = int(m_ym.group(1)), int(m_ym.group(2))
        if 1 <= m <= 12:
            return _safe_make_utc(y, m, 31)

    # Pattern: DD.MM.YYYY or DD/MM/YYYY or MM/DD/YYYY
    m_euro = re.search(r'(\d{1,2})[\./-](\d{1,2})[\./-](\d{4})', cleaned)
    if m_euro:
        p1, p2, y = int(m_euro.group(1)), int(m_euro.group(2)), int(m_euro.group(3))
        if p2 > 12 and p1 <= 12:
            # Clearly US format MM/DD/YYYY
            m, d = p1, p2
        else:
            d, m = p1, p2
        return _safe_make_utc(y, m, d)

    # Strip ordinal period from day (e.g. "31. March 2026" -> "31 March 2026")
    cleaned = re.sub(r'\b(\d{1,2})\.\s+([A-Za-z]+)', r'\1 \2', cleaned)

    # Fallback to dateutil / datetime parsing if available
    for fmt in (
        "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y",
        "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%d. %B %Y", "%d. %b %Y",
        "%d.%m.%Y", "%d.%m.%y"
    ):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
        except Exception:
            continue

    # Month and Year only (e.g. September 2000, Jun 2002, 09/2000, 2024-09, September, 2024) -> clamp to end of month
    for m_fmt in ("%B %Y", "%b %Y", "%B, %Y", "%b, %Y", "%m/%Y", "%Y-%m", "%Y/%m"):
        try:
            dt = datetime.strptime(cleaned, m_fmt)
            return _safe_make_utc(dt.year, dt.month, 31)
        except Exception:
            continue

    # Standalone Fiscal Year (e.g. FY25, FY26, CY24, FY2025) -> clamp to end of year
    m_fy = re.search(r'\b(?:CY|FY)\s*(\d{2,4})\b', cleaned, re.IGNORECASE)
    if m_fy:
        raw_y = int(m_fy.group(1))
        y = (2000 + raw_y) if raw_y < 100 else raw_y
        return _safe_make_utc(y, 12, 31)

    # Standalone 4-digit Calendar Year (e.g. 2026, 1999) -> clamp to end of year
    m_yr = re.fullmatch(r'^(20\d{2}|19\d{2})$', cleaned)
    if m_yr:
        y = int(m_yr.group(1))
        return _safe_make_utc(y, 12, 31)

    return None


def _safe_make_utc(year: int, month: int, day: int) -> Optional[str]:
    """Clamps invalid days (e.g. Nov 31 -> Nov 30) and produces UTC ISO string for realistic lifecycle years (1970-2099)."""
    if year < 1970 or year > 2099:
        return None
    month = max(1, min(12, month))
    max_day = calendar.monthrange(year, month)[1]
    day = max(1, min(max_day, day))
    dt = datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT00:00:00Z")


def extract_date_from_bulletin_code(bulletin: Optional[str]) -> Optional[str]:
    """
    Extracts UTC ISO date from standard technical bulletin reference codes
    (e.g. 'EOL-PLC-240408-1961-SCA' -> '2024-04-08T00:00:00Z').
    """
    if not bulletin or not isinstance(bulletin, str):
        return None
    m = re.search(r'\b(?:EOL|LTB|EOS)?[A-Z\-]*?(\d{2})(\d{2})(\d{2})\b', bulletin)
    if m:
        yy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        year = 2000 + yy if yy < 80 else 1900 + yy
        if 1 <= mm <= 12 and 1 <= dd <= 31:
            return _safe_make_utc(year, mm, dd)
    return None


def extract_candidate_article_or_page_date(metadata: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Extracts article, page creation, release, or sitemap publication dates
    from metadata dictionary.
    """
    if not metadata or not isinstance(metadata, dict):
        return None
    candidate_keys = [
        "article_date",
        "page_creation_date",
        "release_date",
        "publication_date",
        "published_date",
        "date_published",
        "lastmod",
        "page_date",
        "created_at",
        "announcement_date_utc",
        "news_date",
        "post_date",
    ]
    for key in candidate_keys:
        val = metadata.get(key)
        if val and isinstance(val, str) and val.strip():
            v_clean = val.strip()
            if v_clean.lower() not in ("nan", "none", "null", "n/a", "unknown", "tbd", "undefined"):
                return v_clean
    return None


def resolve_fallback_stage_date(
    current_stage_date: Optional[str],
    candidate_date: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    reference_now: Optional[datetime] = None,
) -> str:
    """
    Resolves lifecycle stage date with deterministic fallback:
    1. If an authentic lifecycle date exists, it is strictly preserved without modification.
    2. If no lifecycle date exists, falls back to article, page creation, or release date.
       - If that candidate date is at least 1 month old (>= 30 days), it is used.
       - If it is younger than 1 month old, in the future, or missing, a date exactly
         1 month old (30 days ago) from current date is used.
    """
    now = reference_now if reference_now is not None else datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)
    one_month_ago_iso = cutoff.strftime("%Y-%m-%dT00:00:00Z")

    # Invariant: Never overwrite an existing authentic lifecycle date
    if current_stage_date and isinstance(current_stage_date, str):
        c = current_stage_date.strip()
        if c and c.lower() not in ("nan", "none", "null", "n/a", "unknown", "tbd", "undefined", ""):
            if c.endswith("Z") and "T" in c:
                return c
            parsed_auth = parse_to_utc_iso(c)
            if parsed_auth:
                return parsed_auth

    # No authentic lifecycle date found -> Attempt candidate date fallback
    cand = candidate_date or extract_candidate_article_or_page_date(metadata)
    if cand and isinstance(cand, str):
        cand_str = cand.strip()
        cand_iso = parse_to_utc_iso(cand_str)
        if cand_iso:
            try:
                cand_dt = datetime.strptime(cand_iso[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if cand_dt <= cutoff:
                    return cand_iso
            except Exception:
                pass
        else:
            try:
                from dateutil import parser as dt_parser
                parsed_dt = dt_parser.parse(cand_str, fuzzy=True)
                if parsed_dt.tzinfo is None:
                    parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
                else:
                    parsed_dt = parsed_dt.astimezone(timezone.utc)
                if 1970 <= parsed_dt.year <= 2099:
                    if parsed_dt <= cutoff:
                        return parsed_dt.strftime("%Y-%m-%dT00:00:00Z")
            except Exception:
                pass

    # Younger than 1 month, unparseable, or missing -> exactly 1 month old from current date
    return one_month_ago_iso


def sanitize_alias_string(v: Any) -> Optional[str]:
    """Cleans and validates an aliases string or list of alias candidates."""
    if not v:
        return None
    if isinstance(v, list):
        items = [str(x).strip() for x in v if str(x).strip()]
    elif isinstance(v, str):
        items = [x.strip() for x in re.split(r'[,;]+', v) if x.strip()]
    else:
        items = [str(v).strip()]
    valid_items = []
    for itm in items:
        if not itm or itm.lower() in ("n/a", "none", "null", "-", "--", "nan", "unknown", "undefined"):
            continue
        itm_clean = itm.rstrip(":").strip()
        itm_low = itm_clean.lower()
        # Reject lead-in phrases, table headers, instructional noise, or documentation artifacts
        if re.search(r'\b(?:includes|including|following|affects|affected|applicable)\s+(?:the\s+)?(?:following\s+)?(?:models?|modules?|cpus?)', itm_low):
            continue
        if re.search(r'\b(?:replacement|instruction|user|hardware|programming)\s+(?:manual|guide|handbook)\b', itm_low) or itm_low.endswith((" manual", " manuals", " guide", " handbook")):
            continue
        if re.search(r'^(?:example of\s+)?main\s+units\b', itm_low) or itm_low.endswith(("- main series", " main series", "- sub series", " sub series")):
            continue
        if any(kw in itm_low for kw in ("includes the following", "following models", "replacement manual", "affects the following")):
            continue
        # Strictly reject calendar dates from aliases column
        if parse_to_utc_iso(itm_clean):
            continue
        if re.search(r'\b(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b[^\w\n]*\d{1,2}[^\w\n]*(?:19|20)\d{2}\b', itm_clean, re.I):
            continue
        if re.search(r'\b\d{1,2}[^\w\n]*(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b[^\w\n]*(?:19|20)\d{2}\b', itm_clean, re.I):
            continue
        if re.search(r'\b(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b[^\w\n]*(?:19|20)\d{2}\b', itm_clean, re.I):
            continue
        if re.search(r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-]+(?:\d{1,2}[\s\-]+)?\d{2,4}\b', itm_clean, re.I):
            continue
        if re.search(r'\b(?:\d{1,2}[\s\-]+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-]+\d{2,4}\b', itm_clean, re.I):
            continue
        inspect_security_threats(itm_clean, field_name="aliases", raise_error=True)
        if not is_valid_product_model(itm_clean):
            continue
        valid_items.append(itm_clean)
    deduped = list(dict.fromkeys(valid_items))
    return ", ".join(deduped) if deduped else None


def sanitize_replacement_string(v: Any) -> Optional[str]:
    """Cleans and validates a replacement model string."""
    if not v:
        return None
    s = str(v).strip()
    if not s or s.lower() in ("n/a", "none", "null", "-", "--", "nan", "unknown", "undefined"):
        return None
    # Strictly reject calendar dates from replacement column
    if parse_to_utc_iso(s) or re.search(r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-]+\d{2,4}\b', s, re.I):
        return None
    if re.search(r'\b(?:contact|consult|representative|distributor|no\s+.*replacement|no\s+replacement|not\s+applicable|refer\s+to|see\s+bulletin|official sales|sales rep)\b', s.lower()):
        return None
    if not is_valid_replacement_model(s):
        return None
    return s


class CanonicalStatus(str, Enum):
    """
    Canonical lifecycle status ENUM across all vendor-specific terminology.
    Normalizes multi-vendor and localized stages into 6 consistent stages.
    """
    ACTIVE = "Active"
    ACTIVE_MATURE = "Active Mature"
    PHASE_OUT = "Phase Out"
    END_OF_SALE = "End of Sale"
    END_OF_SUPPORT = "End of Support"
    OBSOLETE = "Obsolete"


CANONICAL_STATUS_MAP: Dict[str, CanonicalStatus] = {
    # Active (General Availability, Current production, Active orderable)
    "active": CanonicalStatus.ACTIVE,
    "available": CanonicalStatus.ACTIVE,
    "current": CanonicalStatus.ACTIVE,
    "in production": CanonicalStatus.ACTIVE,
    "normal": CanonicalStatus.ACTIVE,
    "general availability": CanonicalStatus.ACTIVE,
    "ga": CanonicalStatus.ACTIVE,
    "standard": CanonicalStatus.ACTIVE,
    "supported": CanonicalStatus.ACTIVE,
    "orderable": CanonicalStatus.ACTIVE,
    "mass production": CanonicalStatus.ACTIVE,
    "lieferbar": CanonicalStatus.ACTIVE,
    "aktuell": CanonicalStatus.ACTIVE,
    "prodotti attivi": CanonicalStatus.ACTIVE,
    "en vente": CanonicalStatus.ACTIVE,
    "现货/在产": CanonicalStatus.ACTIVE,
    "販売中": CanonicalStatus.ACTIVE,
    "standard lifecycle": CanonicalStatus.ACTIVE,
    "regular availability": CanonicalStatus.ACTIVE,
    "delivery release": CanonicalStatus.ACTIVE,
    "full support": CanonicalStatus.ACTIVE,
    "longevity commitment": CanonicalStatus.ACTIVE,
    "new": CanonicalStatus.ACTIVE,
    "special order products from hid global": CanonicalStatus.ACTIVE,
    "buy american": CanonicalStatus.ACTIVE,
    "powerg life safety": CanonicalStatus.ACTIVE,

    # Active Mature (Mature, Sustaining, NRND, Not recommended for new designs, Classic)
    "active mature": CanonicalStatus.ACTIVE_MATURE,
    "mature": CanonicalStatus.ACTIVE_MATURE,
    "nrnd": CanonicalStatus.ACTIVE_MATURE,
    "not recommended for new designs": CanonicalStatus.ACTIVE_MATURE,
    "classic": CanonicalStatus.ACTIVE_MATURE,
    "limited": CanonicalStatus.ACTIVE_MATURE,
    "post-production": CanonicalStatus.ACTIVE_MATURE,
    "reifephase": CanonicalStatus.ACTIVE_MATURE,
    "sustaining": CanonicalStatus.ACTIVE_MATURE,
    "maintenance only": CanonicalStatus.ACTIVE_MATURE,
    "extended maintenance": CanonicalStatus.ACTIVE_MATURE,
    "limited support": CanonicalStatus.ACTIVE_MATURE,
    "care/maintenance": CanonicalStatus.ACTIVE_MATURE,

    # Phase Out (Announced EOL, Pending Discontinuation, Phase-Out)
    "phase-out": CanonicalStatus.PHASE_OUT,
    "phase out": CanonicalStatus.PHASE_OUT,
    "phaseout": CanonicalStatus.PHASE_OUT,
    "phase-out product": CanonicalStatus.PHASE_OUT,
    "phase-out announced": CanonicalStatus.PHASE_OUT,
    "auslauftyp": CanonicalStatus.PHASE_OUT,
    "auslaufphase": CanonicalStatus.PHASE_OUT,
    "announced eol": CanonicalStatus.PHASE_OUT,
    "announced discontinuation": CanonicalStatus.PHASE_OUT,
    "end of life announced": CanonicalStatus.PHASE_OUT,
    "pre-discontinued": CanonicalStatus.PHASE_OUT,
    "pending discontinuation": CanonicalStatus.PHASE_OUT,
    "abkündigung angekündigt": CanonicalStatus.PHASE_OUT,
    "vorabkündigung": CanonicalStatus.PHASE_OUT,
    "retiring": CanonicalStatus.PHASE_OUT,
    "to be discontinued": CanonicalStatus.PHASE_OUT,

    # End of Sale (EOS, Last Time Buy, Order Stop, Discontinued for Order)
    "end of sale": CanonicalStatus.END_OF_SALE,
    "end of sales": CanonicalStatus.END_OF_SALE,
    "end of sale (eos)": CanonicalStatus.END_OF_SALE,
    "eos": CanonicalStatus.END_OF_SALE,
    "last time buy": CanonicalStatus.END_OF_SALE,
    "last time buy (ltb)": CanonicalStatus.END_OF_SALE,
    "ltb": CanonicalStatus.END_OF_SALE,
    "end of life order": CanonicalStatus.END_OF_SALE,
    "last buy date": CanonicalStatus.END_OF_SALE,
    "sale stop": CanonicalStatus.END_OF_SALE,
    "verkaufsstopp": CanonicalStatus.END_OF_SALE,
    "fin de vente": CanonicalStatus.END_OF_SALE,
    "販売終了": CanonicalStatus.END_OF_SALE,
    "停止销售": CanonicalStatus.END_OF_SALE,
    "order stop": CanonicalStatus.END_OF_SALE,
    "discontinued for order": CanonicalStatus.END_OF_SALE,
    "final order date": CanonicalStatus.END_OF_SALE,
    "last order date": CanonicalStatus.END_OF_SALE,
    "last order": CanonicalStatus.END_OF_SALE,
    "last purchase date": CanonicalStatus.END_OF_SALE,
    "last purchase": CanonicalStatus.END_OF_SALE,
    "letzte bestellmöglichkeit": CanonicalStatus.END_OF_SALE,
    "end-of-build": CanonicalStatus.END_OF_SALE,
    "stop shipment": CanonicalStatus.END_OF_SALE,

    # End of Support (EOSL, End of Service Life, End of Maintenance, EOM, LDOS)
    "end of support": CanonicalStatus.END_OF_SUPPORT,
    "support end": CanonicalStatus.END_OF_SUPPORT,
    "support ends": CanonicalStatus.END_OF_SUPPORT,
    "end of service life": CanonicalStatus.END_OF_SUPPORT,
    "end of service life (eosl)": CanonicalStatus.END_OF_SUPPORT,
    "eosl": CanonicalStatus.END_OF_SUPPORT,
    "end of service": CanonicalStatus.END_OF_SUPPORT,
    "end of service (eos)": CanonicalStatus.END_OF_SUPPORT,
    "end-of-service": CanonicalStatus.END_OF_SUPPORT,
    "end of maintenance": CanonicalStatus.END_OF_SUPPORT,
    "eom": CanonicalStatus.END_OF_SUPPORT,
    "end of vulnerability support": CanonicalStatus.END_OF_SUPPORT,
    "eovs": CanonicalStatus.END_OF_SUPPORT,
    "last date of support": CanonicalStatus.END_OF_SUPPORT,
    "last date of support (ldos)": CanonicalStatus.END_OF_SUPPORT,
    "ldos": CanonicalStatus.END_OF_SUPPORT,
    "last support date": CanonicalStatus.END_OF_SUPPORT,
    "engineering support expired": CanonicalStatus.END_OF_SUPPORT,
    "premier support ended": CanonicalStatus.END_OF_SUPPORT,
    "premier support ends": CanonicalStatus.END_OF_SUPPORT,
    "extended support ended": CanonicalStatus.END_OF_SUPPORT,
    "extended support ends": CanonicalStatus.END_OF_SUPPORT,
    "sustaining support ended": CanonicalStatus.END_OF_SUPPORT,
    "end of updates": CanonicalStatus.END_OF_SUPPORT,
    "end of sw maintenance": CanonicalStatus.END_OF_SUPPORT,
    "end of software maintenance": CanonicalStatus.END_OF_SUPPORT,
    "end of engineering": CanonicalStatus.END_OF_SUPPORT,
    "limited support end": CanonicalStatus.END_OF_SUPPORT,
    "wartungsende": CanonicalStatus.END_OF_SUPPORT,
    "supportende": CanonicalStatus.END_OF_SUPPORT,
    "fin de support": CanonicalStatus.END_OF_SUPPORT,
    "サポート終了": CanonicalStatus.END_OF_SUPPORT,
    "停止技术支持": CanonicalStatus.END_OF_SUPPORT,
    "service discontinued": CanonicalStatus.END_OF_SUPPORT,
    "pc service": CanonicalStatus.END_OF_SUPPORT,
    "repair": CanonicalStatus.END_OF_SUPPORT,
    "repair end": CanonicalStatus.END_OF_SUPPORT,
    "repair termination": CanonicalStatus.END_OF_SUPPORT,
    "einstellung der reparatur": CanonicalStatus.END_OF_SUPPORT,
    "ersatzteilende": CanonicalStatus.END_OF_SUPPORT,

    # Obsolete (Discontinued, Vintage, Historical, Legacy, EOL, Retired)
    "obsolete": CanonicalStatus.OBSOLETE,
    "discontinued": CanonicalStatus.OBSOLETE,
    "discontinued model": CanonicalStatus.OBSOLETE,
    "discontinued product": CanonicalStatus.OBSOLETE,
    "discontinuation notification": CanonicalStatus.OBSOLETE,
    "vintage": CanonicalStatus.OBSOLETE,
    "historical": CanonicalStatus.OBSOLETE,
    "legacy": CanonicalStatus.OBSOLETE,
    "legacy product": CanonicalStatus.OBSOLETE,
    "retired": CanonicalStatus.OBSOLETE,
    "nla": CanonicalStatus.OBSOLETE,
    "no longer available": CanonicalStatus.OBSOLETE,
    "no longer sold": CanonicalStatus.OBSOLETE,
    "abgekündigt": CanonicalStatus.OBSOLETE,
    "eingestellt": CanonicalStatus.OBSOLETE,
    "obsoleto": CanonicalStatus.OBSOLETE,
    "discontinuado": CanonicalStatus.OBSOLETE,
    "produit obsolète": CanonicalStatus.OBSOLETE,
    "废弃": CanonicalStatus.OBSOLETE,
    "淘汰": CanonicalStatus.OBSOLETE,
    "生産終了": CanonicalStatus.OBSOLETE,
    "完全停产": CanonicalStatus.OBSOLETE,
    "end of life": CanonicalStatus.OBSOLETE,
    "end of life (eol)": CanonicalStatus.OBSOLETE,
    "endoflife": CanonicalStatus.OBSOLETE,
    "eol": CanonicalStatus.OBSOLETE,
    "end-of-life": CanonicalStatus.OBSOLETE,
    "product end of life": CanonicalStatus.OBSOLETE,
    "end of life cycle": CanonicalStatus.OBSOLETE,
    "produktabkündigung": CanonicalStatus.OBSOLETE,
    "abkündigung": CanonicalStatus.OBSOLETE,
    "product cancellation": CanonicalStatus.OBSOLETE,
    "product discontinuation": CanonicalStatus.OBSOLETE,
    "production termination": CanonicalStatus.OBSOLETE,
    "production withdrawal": CanonicalStatus.OBSOLETE,
    "withdrawal": CanonicalStatus.OBSOLETE,
    "inactive": CanonicalStatus.OBSOLETE,
    "deprecated": CanonicalStatus.OBSOLETE,
}


def normalize_to_canonical_status(raw_status: Optional[str], vendor_name: Optional[str] = None) -> str:
    """
    Normalizes vendor-specific status string into one of 6 canonical ENUM statuses:
    - Active
    - Active Mature
    - Phase Out
    - End of Sale
    - End of Support
    - Obsolete
    """
    if not raw_status or not isinstance(raw_status, str):
        return CanonicalStatus.OBSOLETE.value

    cleaned = raw_status.strip()
    cleaned = re.sub(r'[\*\_\#\`]', '', cleaned).strip()
    cleaned = re.sub(r':$', '', cleaned).strip()
    s_lower = cleaned.lower()

    if not s_lower:
        return CanonicalStatus.OBSOLETE.value

    # 1. Exact match in canonical dictionary
    if s_lower in CANONICAL_STATUS_MAP:
        return CANONICAL_STATUS_MAP[s_lower].value

    # 2. Explicit 'end of ...' patterns (ensures modifiers like 'standard' or 'regular' do not misclassify)
    if re.search(r'\bend\s+of\s+(?:[a-z]+\s+)?(?:support|service|maintenance|engineering|updates|warranty)\b', s_lower):
        return CanonicalStatus.END_OF_SUPPORT.value
    if re.search(r'\bend\s+of\s+(?:[a-z]+\s+)?(?:sale|sales|order|build)\b', s_lower):
        return CanonicalStatus.END_OF_SALE.value
    if re.search(r'\bend\s+of\s+(?:[a-z]+\s+)?(?:life|availability)\b', s_lower):
        return CanonicalStatus.OBSOLETE.value

    # 3. Check for substring match (prioritizing specific lifecycle phases, longest first)
    for pattern, canon in sorted(CANONICAL_STATUS_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if pattern in s_lower:
            return canon.value

    # 3. Fallback keywords
    if any(k in s_lower for k in ["support", "service", "maintenance", "eom", "eosl", "vulnerability", "patch"]):
        return CanonicalStatus.END_OF_SUPPORT.value
    if any(k in s_lower for k in ["sale", "order", "buy", "purchase", "eos", "ltb", "shipment"]):
        return CanonicalStatus.END_OF_SALE.value
    if any(k in s_lower for k in ["phase", "pre-discontinued", "pending", "retiring", "auslauf"]):
        return CanonicalStatus.PHASE_OUT.value
    if any(k in s_lower for k in ["mature", "nrnd", "classic", "limited", "sustaining"]):
        return CanonicalStatus.ACTIVE_MATURE.value
    if any(k in s_lower for k in ["active", "available", "current", "production", "ga", "standard", "orderable"]):
        return CanonicalStatus.ACTIVE.value

    return CanonicalStatus.OBSOLETE.value


def compare_and_select_latest_record(rec_a: Dict[str, Any], rec_b: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enforces Requirement 11 & 12:
    When two records match on (vendor, model, canonical_status), strictly retains
    the record with the latest date, and merges non-empty replacements, aliases, and metadata.
    """
    dt_a_str = str(rec_a.get("stage_date_utc") or "").strip()
    dt_b_str = str(rec_b.get("stage_date_utc") or "").strip()

    dt_a = parse_to_utc_iso(dt_a_str) if dt_a_str else None
    dt_b = parse_to_utc_iso(dt_b_str) if dt_b_str else None

    # Determine winner based on date
    if dt_a and dt_b:
        winner = rec_b if dt_b > dt_a else rec_a
        loser = rec_a if dt_b > dt_a else rec_b
    elif dt_b and not dt_a:
        winner, loser = rec_b, rec_a
    else:
        winner, loser = rec_a, rec_b

    result = dict(winner)

    # Merge non-empty fields from loser if winner is empty
    for field in ("replacement", "aliases", "os", "firmware", "source_url", "category"):
        if not str(result.get(field) or "").strip() and str(loser.get(field) or "").strip():
            result[field] = loser[field]

    # Merge metadata
    meta_win: Dict[str, Any] = {}
    meta_lose: Dict[str, Any] = {}
    try:
        raw_mw = result.get("metadata")
        meta_win = json.loads(raw_mw) if isinstance(raw_mw, str) else dict(raw_mw or {})
    except Exception:
        pass
    try:
        raw_ml = loser.get("metadata")
        meta_lose = json.loads(raw_ml) if isinstance(raw_ml, str) else dict(raw_ml or {})
    except Exception:
        pass
    merged_meta = {**meta_lose, **meta_win}
    result["metadata"] = json.dumps(merged_meta, ensure_ascii=False) if isinstance(result.get("metadata"), str) else merged_meta

    return result


def classify_hardware_or_software(
    vendor_name: str,
    model_name: str,
    os_name: Optional[str] = None,
    category: Optional[str] = None
) -> Tuple[str, Optional[str]]:
    """
    Determines if a product is Hardware, Software, Firmware, or Operating System.
    Returns (category_classification: str, extracted_os: Optional[str]).
    """
    m_clean = (model_name or "").strip()
    o_clean = (os_name or "").strip()
    c_clean = (category or "").strip()

    # Check if model name itself is an Operating System (e.g. Apple iOS, macOS, watchOS, Windows, Ubuntu)
    os_match = re.search(
        r'^(?:Apple\s+)?(iOS|iPadOS|macOS|watchOS|tvOS|visionOS|OS X|Windows|Ubuntu|Red Hat|RHEL|SUSE|CentOS|Debian|Android)\b(?:\s+([A-Za-z]+))?\s*(.*)?$',
        m_clean,
        re.IGNORECASE
    )
    if os_match:
        os_family = os_match.group(1).strip()
        os_sub = os_match.group(2).strip() if os_match.group(2) else ""
        os_ver = os_match.group(3).strip() if os_match.group(3) else ""
        parts = [p for p in (os_family, os_sub, os_ver) if p]
        full_os = " ".join(parts).strip()
        return "Software - OS", full_os

    # Check if model name represents firmware
    if re.search(r'\bfirmware\s+update\b', m_clean, re.IGNORECASE):
        return "Firmware", o_clean or None

    # Check if category or model represents software / apps / SDKs
    if any(kw in m_clean.lower() for kw in [" software", " sdk", " driver", " application", " plugin", " connect ", " music ", " pages ", " keynote ", " numbers ", " garageband ", " safari "]):
        return "Software", o_clean or None

    if is_well_known_os_or_software(category=c_clean, os_name=o_clean, model_name=m_clean):
        return ("Software - OS" if (o_clean or any(w in m_clean.lower() for w in ["windows", "linux", "ios", "macos", "android"])) else "Software"), (o_clean or None)

    return "Hardware", o_clean or None


class ProductRecord(BaseModel):
    """
    Database-ready product lifecycle record representing a single status milestone.
    Includes exact vendor terminology, normalized semantic firmware, UTC dates,
    and a deterministic SHA-256 fingerprint for database upserts/appends.

    MANDATORY NOT-NULL INVARIANTS:
    - vendor_name: Non-empty string
    - model_name: Non-empty, verified hardware/software model part number
    - status: Non-empty vendor-exact status string
    - stage_date_utc: Non-empty UTC ISO 8601 timestamp (YYYY-MM-DDTHH:MM:SSZ)
    """
    fingerprint: Optional[str] = Field(default=None, description="Deterministic SHA-256 hash for DB upsert/append operations")
    vendor_name: str = Field(min_length=1, description="Manufacturer / Vendor name in English (MANDATORY, NO NULL ALLOWED)")
    model_name: str = Field(min_length=1, description="Individual product part number or model name (MANDATORY, NO NULL ALLOWED)")
    aliases: Optional[str] = Field(default=None, description="Comma-separated model aliases, marketing codes, or alternative common names pointing to model_name")
    os: Optional[str] = Field(default=None, description="Operating system / software runtime or None")
    firmware: Optional[str] = Field(default=None, description="Semantic firmware version (e.g. '1.0.0', '2.1.0') or None for hardware")
    status: str = Field(default="Discontinued", min_length=1, description="Unified lifecycle status representing exact official vendor terminology without limitation (MANDATORY, NO NULL ALLOWED)")
    stage: str = Field(default="", description="Lifecycle stage matching exact vendor terminology without limitation")
    vendor_status: str = Field(default="", description="EXACT official terminology used by the vendor (e.g., 'Phase-Out', 'Delivery Release', 'End of Sale', 'Classic', 'Limited', 'Obsolete')")
    stage_date_utc: Optional[str] = Field(default=None, description="ISO 8601 UTC timestamp: YYYY-MM-DDTHH:MM:SSZ or None if vendor does not publish date")
    source_url: Optional[str] = Field(default="", description="Source portal or bulletin URL")
    category: Optional[str] = Field(default="General Automation", description="Normalized category: PLC, Industrial PC, HMI, Inverter, etc.")
    product_category: Optional[str] = Field(default="General Automation", description="Normalized category")
    replacement: Optional[str] = Field(default=None, description="Successor / migration model recommendation")
    canonical_status: Optional[str] = Field(default=None, description="Canonical ENUM status (Active, Active Mature, Phase Out, End of Sale, End of Support, Obsolete)")
    first_discovered_utc: Optional[str] = Field(default=None, description="Timestamp when record was first extracted")
    last_updated_utc: Optional[str] = Field(default=None, description="Timestamp of the most recent scrape update")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata dictionary containing all additional attributes in JSON")

    @model_validator(mode="before")
    @classmethod
    def populate_mandatory_status_and_defaults(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Prioritize vendor_status, then stage, then status
            st = data.get("status")
            vs = data.get("vendor_status")
            sg = data.get("stage")

            chosen = None
            for candidate in (vs, sg, st):
                if candidate and isinstance(candidate, str) and candidate.strip():
                    if candidate.strip().lower() not in ("n/a", "none", "null", "nan"):
                        chosen = candidate.strip()
                        break

            if chosen:
                data["status"] = chosen
                if not data.get("vendor_status"):
                    data["vendor_status"] = chosen
                if not data.get("stage"):
                    data["stage"] = chosen

            # If stage_date_utc is missing or empty, attempt recovery from bulletin code or fallback logic
            dt = data.get("stage_date_utc")
            if not dt or (isinstance(dt, str) and dt.strip().lower() in ("", "n/a", "none", "null", "nan")):
                b_code = data.get("bulletin_code")
                meta = data.get("metadata") or {}
                b_title = None
                if isinstance(meta, dict):
                    b_title = meta.get("bulletin_title") or meta.get("bulletin_code")
                rec_dt = extract_date_from_bulletin_code(b_code or b_title)
                if rec_dt:
                    data["stage_date_utc"] = rec_dt
                else:
                    if "metadata" not in data or not isinstance(data.get("metadata"), dict):
                        data["metadata"] = {}
                    cand_dt = extract_candidate_article_or_page_date(data.get("metadata"))
                    fallback_dt = resolve_fallback_stage_date(None, candidate_date=cand_dt, metadata=data.get("metadata"))
                    data["stage_date_utc"] = fallback_dt
                    data["metadata"]["missing_date"] = True
                    data["metadata"]["fallback_date_applied"] = True

            # Model is allowed empty ONLY for software applications or well-known OS entries (e.g. Linux, Debian, Windows)
            cat = (data.get("category") or data.get("product_category") or "").strip()
            os_val = (data.get("os") or "").strip()
            model_val = data.get("model_name")
            is_sw_or_os = is_well_known_os_or_software(category=cat, os_name=os_val, model_name=str(model_val or ""))

            # Hardware vs Software / OS classification
            v_name = str(data.get("vendor_name") or "")
            prod_class, ext_os = classify_hardware_or_software(
                vendor_name=v_name,
                model_name=str(model_val or ""),
                os_name=os_val or None,
                category=cat or None
            )
            if ext_os and not data.get("os"):
                data["os"] = ext_os
            if not cat or cat.lower() in ("general automation", "general", "it", "ot", "iot"):
                if prod_class and prod_class != "Hardware":
                    data["category"] = prod_class
                    data["product_category"] = prod_class

            # Derive and populate canonical_status
            raw_st = data.get("status") or data.get("vendor_status") or chosen
            c_status = normalize_to_canonical_status(raw_st, v_name)
            data["canonical_status"] = c_status
            if "metadata" in data and isinstance(data["metadata"], dict):
                data["metadata"]["canonical_status"] = c_status
                if chosen and chosen != c_status:
                    data["metadata"]["raw_vendor_status"] = chosen

            if not model_val or (isinstance(model_val, str) and model_val.strip().lower() in ("", "n/a", "none", "null", "nan")):
                if is_sw_or_os:
                    data["model_name"] = os_val or ""
                else:
                    data["model_name"] = None

        return data

    @field_validator("vendor_name", mode="before")
    def validate_vendor_name(cls, v):
        if not v or not isinstance(v, str) or not v.strip() or v.strip().lower() in ("n/a", "none", "null", "nan"):
            raise ValueError("vendor_name is mandatory and cannot be null or empty")
        inspect_security_threats(v, field_name="vendor_name", raise_error=True)
        return v.strip()

    @field_validator("model_name", mode="before")
    def validate_model_name(cls, v):
        if v is None:
            raise ValueError("model_name is mandatory and cannot be null or empty for hardware or non-OS/software products")
        if not isinstance(v, str):
            raise ValueError("model_name must be a string")
        cleaned = v.strip().replace("\xa0", " ").replace("\u00a0", " ")
        if not cleaned:
            # Empty string permitted only for software / well-known OS records
            return ""
        if cleaned.lower() in ("n/a", "none", "null", "nan"):
            raise ValueError("model_name cannot be 'n/a', 'none', or 'null'")
        inspect_security_threats(cleaned, field_name="model_name", raise_error=True)
        if not is_valid_product_model(cleaned):
            raise ValueError(f"Disallowed or invalid model name: '{cleaned}'")
        return cleaned

    @field_validator("aliases", mode="before")
    @classmethod
    def clean_aliases(cls, v: Any) -> Optional[str]:
        return sanitize_alias_string(v)

    @field_validator("status", mode="before")
    def validate_status(cls, v):
        if not v or not isinstance(v, str) or not v.strip() or v.strip().lower() in ("n/a", "none", "null", "nan"):
            raise ValueError("status is mandatory and cannot be null or empty")
        inspect_security_threats(v, field_name="status", raise_error=True)
        return v.strip()

    @field_validator("firmware", mode="before")
    def clean_firmware(cls, v):
        return normalize_firmware_version(v)

    @field_validator("stage_date_utc", mode="before")
    def validate_utc(cls, v):
        if not v or not isinstance(v, str) or not v.strip() or v.strip().lower() in ("n/a", "none", "null", "nan", "unknown", "tbd", "undefined", ""):
            return resolve_fallback_stage_date(None)
        cleaned = v.strip()
        if cleaned.endswith("Z") and "T" in cleaned:
            return cleaned
        parsed = parse_to_utc_iso(cleaned)
        if not parsed:
            return resolve_fallback_stage_date(None)
        return parsed

    @field_validator("replacement", mode="before")
    @classmethod
    def clean_replacement(cls, v: Any) -> Optional[str]:
        return sanitize_replacement_string(v)

    @model_validator(mode="after")
    def compute_fingerprint_and_defaults(self):
        # Strict validation: model_name must not be empty unless software/application or well-known OS
        if not self.model_name and not is_well_known_os_or_software(self.category, self.os):
            raise ValueError(
                "model_name is mandatory and can only be empty for software applications or "
                "well-known OS entries (e.g., Linux, Debian, Windows)."
            )

        # Synchronize status, stage, and vendor_status so they are unified
        chosen_status = self.vendor_status or self.stage or self.status or "Discontinued"
        self.status = chosen_status
        self.vendor_status = chosen_status
        self.stage = chosen_status

        # Synchronize category and replacement
        if not self.category or self.category == "General Automation":
            self.category = self.product_category or "General Automation"
        self.product_category = self.category

        if not self.source_url:
            self.source_url = (self.metadata or {}).get("source_url", "")
        
        # Rigorous replacement cleaning: reject N/A, None, -, and conversational filler
        candidate_repl = self.replacement
        if not candidate_repl:
            meta_repl = (self.metadata or {}).get("replacement")
            if meta_repl:
                candidate_repl = str(meta_repl).strip()
        self.replacement = sanitize_replacement_string(candidate_repl) if candidate_repl else None

        # Synchronize aliases from metadata if not explicitly provided, and sanitize strictly
        if not self.aliases:
            meta = self.metadata or {}
            meta_al = meta.get("aliases") or meta.get("model_aliases") or meta.get("common_name")
            if meta_al:
                self.aliases = sanitize_alias_string(meta_al)
        elif self.aliases:
            self.aliases = sanitize_alias_string(self.aliases)

        # Filter out aliases that match model_name exactly (case-insensitive)
        if self.aliases and self.model_name:
            m_norm = self.model_name.strip().upper()
            filtered = [
                a.strip() for a in self.aliases.split(",")
                if a.strip() and a.strip().upper() != m_norm
            ]
            self.aliases = ", ".join(filtered) if filtered else None

        # Generate deterministic fingerprint: SHA-256(vendor|model/os|status|date)
        model_part = (self.model_name or self.os or "").strip().upper()
        key = f"{self.vendor_name.strip().upper()}|{model_part}|{self.status.strip().upper()}|{(self.stage_date_utc or '').strip()}"
        self.fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not self.first_discovered_utc:
            self.first_discovered_utc = now_utc
        self.last_updated_utc = now_utc
        return self


class AIProductItem(BaseModel):
    """
    Universal structured extraction item schema for all AI providers
    (Google Gemini, OpenAI, Anthropic Claude, Azure OpenAI, AWS Bedrock, Ollama).
    Uses strictly defined scalar fields with extra='ignore' for maximum cross-provider compatibility.
    """
    model_config = ConfigDict(extra="ignore")

    vendor_name: Optional[str] = Field(default="", description="Manufacturer or brand name in English")
    model_name: str = Field(description="Individual product part number or model name (never bundled)")
    aliases: Optional[str] = Field(default=None, description="Comma-separated model aliases, marketing codes, or alternative common names pointing to model_name")
    status: Optional[str] = Field(default="Discontinued", description="Exact vendor lifecycle status / phase without limitation")
    stage_date_utc: Optional[str] = Field(default=None, description="Milestone date in ISO 8601 UTC (YYYY-MM-DDTHH:MM:SSZ) or null if unspecified")
    category: Optional[str] = Field(default="General Automation", description="Product category (e.g. PLC, HMI, Inverter, Camera, Switch)")
    replacement: Optional[str] = Field(default=None, description="Recommended successor or replacement model")
    os: Optional[str] = Field(default=None, description="Operating system if explicitly stated")
    firmware: Optional[str] = Field(default=None, description="Semantic firmware version if explicitly stated")
    bulletin_code: Optional[str] = Field(default=None, description="Technical bulletin or notice reference code")
    notes: Optional[str] = Field(default=None, description="Migration notes or additional context")


# Backward compatibility alias
GeminiProductItem = AIProductItem


class AIExtractionBatch(BaseModel):
    """Universal batch extraction schema for structured responses from any AI provider."""
    model_config = ConfigDict(extra="ignore")

    vendor_name: str = Field(default="Industrial Automation", description="Identified vendor name")
    detected_language: str = Field(default="en", description="Source content language ('en', 'de', 'ja', 'sv')")
    products: List[AIProductItem] = Field(description="Product records, with exactly ONE record per status milestone")
    source_summary: Optional[str] = Field(default=None, description="Brief summary in English")


# Backward compatibility alias
GeminiExtractionBatch = AIExtractionBatch


class ScrapedDataset(BaseModel):
    """Complete dataset resulting from the crawl and AI extraction run."""
    source_url: str
    crawl_timestamp: str
    total_products: int
    ai_model_used: str
    supported_vendors: List[str] = Field(default_factory=lambda: ["Mitsubishi Electric", "Siemens", "Schneider Electric", "Rockwell Automation", "Omron"])
    products: List[ProductRecord]
