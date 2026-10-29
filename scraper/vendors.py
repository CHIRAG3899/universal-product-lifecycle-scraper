"""
Multi-Vendor Registry & Internationalization (i18n) Normalization Module.
Enables the AI scraper to handle diverse industrial automation vendors
and automatically translate regional/local language product notices into English.
"""

import re
from typing import Any, Dict, Optional

# Multi-lingual stage mapping dictionary (maps localized & vendor terms to clean English Stages)
# Vendors do NOT follow a single fixed status list; vendor-specific lifecycle phases are preserved as-is.
STAGE_TRANSLATIONS: Dict[str, str] = {
    # Vendor-Specific English Stages (Preserved Exactly)
    "end of sales announcement": "End of Life (EOL)",  # Legacy sentence mapping for backward compatibility
    "end of sale": "End of Sale",
    "end of sales": "End of Sale",
    "last date of support": "Last Date of Support",
    "ldos": "Last Date of Support (LDoS)",
    "end of sw maintenance": "End of SW Maintenance",
    "end of software maintenance": "End of SW Maintenance",
    "end of new service": "End of New Service",
    "delivery release": "Delivery Release",
    "announced discontinuation": "Announced Discontinuation",
    "product cancellation": "Product Cancellation",
    "product discontinuation": "Product Discontinuation",
    "phase-out product": "Phase-Out Product",
    "phase-out announced": "Phase-Out Announced",
    "phase out": "Phase-Out Announced",
    "phase-out": "Phase-Out",
    "classic": "Classic",
    "limited": "Limited",
    "obsolete": "Obsolete",
    "active mature": "Active Mature",
    "active": "Active",
    "stop shipment": "Stop Shipment",
    "repair termination": "Repair Termination",
    "production termination": "Production Termination",
    "maintenance only": "Maintenance Only",
    "extended maintenance": "Extended Maintenance",

    # Standard EOL / LTB / EOS Terms
    "end of life": "End of Life (EOL)",
    "eol": "End of Life (EOL)",
    "last time buy": "Last Time Buy (LTB)",
    "ltb": "Last Time Buy (LTB)",
    "end of service": "End of Service (EOS)",
    "eos": "End of Service (EOS)",
    "discontinued": "Discontinued",
    "withdrawal": "Production Withdrawal",
    "final order": "Last Time Buy (LTB)",
    "repair end": "End of Service (EOS)",

    # German (Siemens, Phoenix Contact, Beckhoff)
    "produktabkündigung": "End of Life (EOL)",
    "abkündigung": "End of Life (EOL)",
    "auslauftyp": "Phase-Out Announced",
    "auslaufphase": "Phase-Out Announced",
    "letzte bestellmöglichkeit": "Last Time Buy (LTB)",
    "einstellung der reparatur": "End of Service (EOS)",
    "ersatzteilende": "End of Service (EOS)",
    "lieferstopp": "Discontinued",

    # Japanese (Mitsubishi, Omron, Keyence, Fanuc, Yaskawa)
    "生産終了": "End of Life (EOL)",
    "販売終了": "End of Life (EOL)",
    "製造中止": "Discontinued",
    "最終受注": "Last Time Buy (LTB)",
    "最終注文": "Last Time Buy (LTB)",
    "保守終了": "End of Service (EOS)",
    "修理対応終了": "End of Service (EOS)",
    "補修部品供給終了": "End of Service (EOS)",

    # Swedish / Nordic (Mitsubishi Scandinavian branch, ABB)
    "utgående produkt": "End of Life (EOL)",
    "avveckling": "End of Life (EOL)",
    "sista orderdatum": "Last Time Buy (LTB)",
    "sista beställning": "Last Time Buy (LTB)",
    "service upphör": "End of Service (EOS)",
    "support upphör": "End of Service (EOS)",

    # French (Schneider Electric)
    "fin de vie": "End of Life (EOL)",
    "arrêt de commercialisation": "End of Life (EOL)",
    "dernière commande": "Last Time Buy (LTB)",
    "fin de support": "End of Service (EOS)",
    "fin de maintenance": "End of Service (EOS)",
    "obsolescence": "End of Life (EOL)",

    # Spanish / Italian
    "fine vita": "End of Life (EOL)",
    "fine servizio": "End of Service (EOS)",
    "fin de vida": "End of Life (EOL)",
    "última compra": "Last Time Buy (LTB)",
    "fin de soporte": "End of Service (EOS)"
}

# Known Major Industrial Vendors (Defaults removed per specification: OS and Firmware must be dynamically found)
VENDOR_PROFILES: Dict[str, Dict[str, Any]] = {
    "mitsubishi": {
        "display_name": "Mitsubishi Electric",
        "domains": ["mitsubishielectric.com", "mitsubishielectricfa.com"],
        "sector": "OT"
    },
    "siemens": {
        "display_name": "Siemens",
        "domains": ["siemens.com", "sieportal.siemens.com", "industry.siemens.com"],
        "sector": "OT"
    },
    "schneider_electric": {
        "display_name": "Schneider Electric",
        "domains": ["se.com", "schneider-electric.com"],
        "sector": "OT"
    },
    "rockwell_automation": {
        "display_name": "Rockwell Automation (Allen-Bradley)",
        "domains": ["rockwellautomation.com", "ab.com"],
        "sector": "OT"
    },
    "omron": {
        "display_name": "Omron Corporation",
        "domains": ["omron.com", "ia.omron.com"],
        "sector": "OT"
    },
    "abb": {
        "display_name": "ABB",
        "domains": ["abb.com"],
        "sector": "OT"
    },
    "cisco_systems": {
        "display_name": "Cisco Systems",
        "domains": ["cisco.com"],
        "sector": "IT"
    },
    "hpe": {
        "display_name": "Hewlett Packard Enterprise",
        "domains": ["hpe.com", "arubanetworks.com"],
        "sector": "IT"
    },
    "dell": {
        "display_name": "Dell Technologies",
        "domains": ["dell.com"],
        "sector": "IT"
    },
    "intel_iot": {
        "display_name": "Intel Edge & Embedded",
        "domains": ["intel.com"],
        "sector": "IoT"
    },
    "digi_international": {
        "display_name": "Digi International",
        "domains": ["digi.com"],
        "sector": "IoT"
    }
}


_LOADED_YAML_VENDORS: Optional[Dict[str, Any]] = None


def _get_yaml_vendors() -> Dict[str, Any]:
    """Dynamically loads and caches the 100 enterprise vendors from configs/vendors.yaml."""
    global _LOADED_YAML_VENDORS
    if _LOADED_YAML_VENDORS is None:
        _LOADED_YAML_VENDORS = {}
        try:
            from pathlib import Path

            import yaml
            cfg_path = Path(__file__).resolve().parent.parent / "configs" / "vendors.yaml"
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                    _LOADED_YAML_VENDORS = data.get("vendors", {})
        except Exception:
            _LOADED_YAML_VENDORS = {}
    return _LOADED_YAML_VENDORS


def detect_vendor_from_url_or_text(url: str, text: Optional[str] = None) -> str:
    """Identifies the vendor name based on URL domain or page text dynamically without assuming static defaults."""
    url_lower = (url or "").lower()

    # 1. Check primary profiles
    for v_key, profile in VENDOR_PROFILES.items():
        if any(dom in url_lower for dom in profile.get("domains", [])):
            return profile.get("display_name", v_key.title())

    # 2. Check 100 enterprise vendors loaded from vendors.yaml
    yaml_vendors = _get_yaml_vendors()
    for vk, vcfg in yaml_vendors.items():
        v_doms = vcfg.get("allowed_domains", [])
        v_site = (vcfg.get("website") or "").lower()
        if any(dom.lower() in url_lower for dom in v_doms if dom) or (v_site and v_site in url_lower):
            return vcfg.get("name", vk.replace("_", " ").title())

    if text:
        text_lower = text[:5000].lower()
        if "mitsubishi" in text_lower:
            return "Mitsubishi Electric"
        elif "siemens" in text_lower:
            return "Siemens"
        elif "schneider" in text_lower:
            return "Schneider Electric"
        elif "rockwell" in text_lower or "allen-bradley" in text_lower:
            return "Rockwell Automation (Allen-Bradley)"
        elif "omron" in text_lower:
            return "Omron Corporation"
        elif "cisco" in text_lower:
            return "Cisco Systems"
        elif "dell" in text_lower:
            return "Dell Technologies"
        elif "hpe" in text_lower or "hewlett packard" in text_lower:
            return "Hewlett Packard Enterprise"

        # Check YAML vendor names in text
        for vk, vcfg in yaml_vendors.items():
            v_name = vcfg.get("name", "").lower()
            if v_name and v_name in text_lower:
                return vcfg.get("name", vk.title())

    # Derive from domain if possible
    m = re.search(r'https?://(?:www\.)?([^/]+)', url or "")
    if m:
        domain = m.group(1).split(".")[0].title()
        return domain

    return "Industrial Automation"


def normalize_stage_name(raw_stage: Optional[str]) -> str:
    """
    Normalizes any local language, regional term, or vendor-specific lifecycle phase into clean English.
    Places ZERO arbitrary limitations on vendor status: preserves exact vendor-specific lifecycle
    milestones (e.g. 'Phase-Out Product', 'Delivery Release', 'Classic', 'Limited', 'Obsolete',
    'Active Mature', 'End of Sale', 'Last Date of Support', 'Product Cancellation', 'Stop Shipment').
    """
    if not raw_stage or not isinstance(raw_stage, str):
        return "Discontinued"

    # Strip markdown and HTML noise
    cleaned = raw_stage.strip()
    cleaned = re.sub(r'[\*\_\#\`]', '', cleaned).strip()
    cleaned = re.sub(r':$', '', cleaned).strip()
    c_lower = cleaned.lower()

    if not c_lower:
        return "Discontinued"

    # 1. Exact or substring match in STAGE_TRANSLATIONS dictionary (longest pattern first)
    for pattern in sorted(STAGE_TRANSLATIONS.keys(), key=len, reverse=True):
        if pattern in c_lower:
            return STAGE_TRANSLATIONS[pattern]

    # 2. Check for common vendor status phrases
    if "last date of support" in c_lower or "ldos" in c_lower:
        return "Last Date of Support"
    if "end of sale" in c_lower or "eos" == c_lower or "end of sales" in c_lower:
        return "End of Sale"
    if "ltb" in c_lower or ("last" in c_lower and "buy" in c_lower):
        return "Last Time Buy (LTB)"
    if "eol" in c_lower or "end of life" in c_lower:
        return "End of Life (EOL)"
    if "eos" in c_lower or "end of service" in c_lower or "repair end" in c_lower:
        return "End of Service (EOS)"
    if "phase-out" in c_lower or "phase out" in c_lower:
        return "Phase-Out"
    if "discontinu" in c_lower:
        return "Discontinued"
    if "obsolete" in c_lower:
        return "Obsolete"
    if "classic" in c_lower:
        return "Classic"
    if "limited" in c_lower:
        return "Limited"
    if "active mature" in c_lower:
        return "Active Mature"

    # 3. Preserve the exact vendor status cleanly title-cased or preserved (up to 100 chars, no truncation)
    clean_title = cleaned[:100].strip()
    if clean_title.isupper() or clean_title.islower():
        clean_title = clean_title.title()
    return clean_title or "Discontinued"

