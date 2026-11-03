"""
Base Scraping Strategy Interface and Common Sanitization Pipeline.

Defines the polymorphic contract for all scraping strategies (search portals,
DOM tables, XML sitemaps, REST APIs). Enforces uniform data validation,
quote-free symbol hygiene, SQL schema compliance, and circuit-breaker error bounds.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from dateutil import parser as date_parser

from scraper.dlq import DeadLetterQueue
from scraper.models import (
    GENERIC_PRODUCT_CATEGORY_TOKENS,
    ProductRecord,
    is_valid_product_model,
    is_valid_replacement_model,
    parse_to_utc_iso,
)
from scraper.security import clean_csv_field
from scraper.state import VendorRunState
from scraper.vendors import normalize_stage_name

logger = logging.getLogger("ai_scraper.strategies.base")

# Common marketing noise patterns to purge across all enterprise vendors
DISALLOWED_CATEGORY_PATTERNS = [
    re.compile(
        r"(?:human\s*machine|circuit[\-_]?and[\-_]?load|variable\s*frequency|cubic[\-_]?modular|programmable\s*controllers)",
        re.I,
    ),
    re.compile(
        r"(?:discontinued\s*products?|overview|hardware|software|brochure|accessories)",
        re.I,
    ),
]


_MONTH_TOKENS = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
)


def is_likely_date_str(val: Optional[str]) -> bool:
    """Return True if val looks like a calendar date rather than an alias or model name."""
    if not val:
        return False
    v = str(val).strip().lower()
    from scraper.models import parse_to_utc_iso
    if parse_to_utc_iso(v):
        return True
    if any(m in v for m in _MONTH_TOKENS) and re.search(r"\b20\d\d\b|\b19\d\d\b", v):
        return True
    if re.search(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", v) or re.search(r"^\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}", v):
        return True
    if re.search(r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{2,4}\b", v):
        return True
    if re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-]+(?:\d{1,2}[\s\-]+)?\d{2,4}\b", v):
        return True
    if re.search(r"\b(?:\d{1,2}[\s\-]+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-]+\d{2,4}\b", v):
        return True
    return False


def sanitize_alias_text(raw_text: Optional[str]) -> Optional[str]:
    """Strip all quote marks completely and replace internal commas to prevent double quotes in CSV."""
    if not raw_text:
        return None
    # Strip ASCII quotes and Unicode curly quotes
    cleaned = re.sub(r'["\'`\u201c\u201d\u2018\u2019]', "", raw_text).strip()
    # Replace internal comma sequences with dashes
    cleaned = re.sub(r",\s*", " - ", cleaned).strip(" -")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or None


def split_model_identifiers(raw_text: Optional[str]) -> List[str]:
    """
    Splits compound model strings by comma, semicolon, newline, pipe, or conjunctions ('and', '&'),
    BUT preserves delimiters inside parentheses (e.g. 'LIC-MI-L (1D, 1YR, 3YR)' stays intact),
    and strictly avoids splitting on forward slash '/' which is valid syntax for SKU options
    (e.g. 'MS22/P', 'MA-MNT-ANT-1/2/3/4', 'SFP/SFP+').
    """
    if not raw_text or not raw_text.strip():
        return []
    clean = raw_text.strip()

    # Clean trailing accessory/descriptor phrases
    clean = re.sub(
        r'\s+(?:and\s+)?(?:Antenna Mounts?|Mount Kits?|Accessories|power supplies and fans|power supplies|licenses)\b.*$',
        '',
        clean,
        flags=re.I
    ).strip()

    # Separate stuck 'and' e.g. '18 andMA-' -> '18 and MA-'
    clean = re.sub(r'(?<=\s)and(?=[A-Z])', 'and ', clean)

    # Whitespace-surrounded slash represents distinct models (e.g. 'PowerEdge R740 / R740xd')
    clean = re.sub(r'\s+/\s*', ' | ', clean)

    if not any(delim in clean for delim in (",", ";", "|", "\n", "\r")) and " and " not in clean.lower() and " & " not in clean:
        return [clean] if clean else []

    parts: List[str] = []
    current: List[str] = []
    paren_depth = 0
    i = 0
    chars = clean
    n = len(chars)
    while i < n:
        ch = chars[i]
        if ch == "(":
            paren_depth += 1
            current.append(ch)
            i += 1
        elif ch == ")":
            paren_depth = max(0, paren_depth - 1)
            current.append(ch)
            i += 1
        elif paren_depth == 0 and ch in (",", ";", "|", "\n", "\r"):
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            i += 1
        elif paren_depth == 0 and chars[i:i+5].lower() == " and ":
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            i += 5
        elif paren_depth == 0 and chars[i:i+3] == " & ":
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            i += 3
        else:
            current.append(ch)
            i += 1

    if current:
        part = "".join(current).strip()
        if part:
            parts.append(part)

    clean_parts: List[str] = []
    for p in parts:
        p_clean = p.strip()
        p_clean = re.sub(r'^(?:and|&)\s+', '', p_clean, flags=re.I).strip()
        p_clean = re.sub(
            r'\s+(?:and\s+)?(?:Antenna Mounts?|Mount Kits?|Accessories|power supplies and fans|power supplies|licenses)\b.*$',
            '',
            p_clean,
            flags=re.I
        ).strip()
        # Strip trailing wildcard glyphs and footnote symbols (e.g. CIMR-AC□ -> CIMR-AC, CVSR-□□ -> CVSR)
        p_clean = re.sub(r'[\u25a0\u25a1\u2217\*※\s]+$', '', p_clean).strip(' -_')
        if p_clean and p_clean.lower() not in (
            'accessories', 'power supplies and fans', 'power supplies',
            'mount kits', 'antenna mounts', 'licenses'
        ):
            clean_parts.append(p_clean)

    return clean_parts


class BaseScrapingStrategy(ABC):
    """Abstract base class for all pluggable scraping strategies."""

    def __init__(self, max_consecutive_errors: int = 5) -> None:
        self.max_consecutive_errors = max_consecutive_errors

    @abstractmethod
    async def execute(
        self,
        entry_point: Dict[str, Any],
        vendor_cfg: Dict[str, Any],
        crawler: Any,
        state: VendorRunState,
        dlq: Optional[DeadLetterQueue] = None,
        max_pages: int = 0,
        batch_size: Optional[int] = None,
        all_batches: bool = False,
    ) -> List[ProductRecord]:
        """Execute scraping strategy against the provided entry point configuration."""
        pass

    def create_sanitized_record(
        self,
        vendor_name: str,
        raw_model: str,
        raw_alias: Optional[str],
        raw_status: str,
        raw_date: Optional[str],
        source_url: str,
        category: str = "Industrial Automation",
        raw_replacement: Optional[str] = None,
        raw_replacement_category: Optional[str] = None,
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> Optional[ProductRecord]:
        """Uniform product record builder with strict validation and sanitization."""
        if not raw_model or not raw_model.strip():
            return None

        clean_model = sanitize_alias_text(raw_model) or ""
        # Strip trailing wildcard glyphs and footnote symbols (e.g. CIMR-AC□ -> CIMR-AC, CVSR-□□ -> CVSR)
        clean_model = re.sub(r'[\u25a0\u25a1\u2217\*※\s]+$', '', clean_model).strip(' -_')

        # Strip trailing regional qualifiers in parentheses: e.g. "GR60 (EU)" -> "GR60", "GR60 (UK)" -> "GR60"
        m_region = re.search(r'\s*\(((?:EU|UK|US|USA|APAC|EMEA|NA|JP|CN|CAN|GLOBAL|WW|RoW|ANZ|LATAM|CEE|MEA))\)\s*$', clean_model, re.I)
        if m_region:
            reg_code = m_region.group(1).upper()
            if extra_meta is None:
                extra_meta = {}
            if "region" not in extra_meta:
                extra_meta["region"] = reg_code
            clean_model = clean_model[:m_region.start()].strip()

        clean_model_upper = clean_model.upper()

        # If raw_alias was not provided and clean_model contains whitespace, attempt smart model/alias separation
        if not raw_alias and " " in clean_model:
            # First check for trailing model code: e.g. 'Data Acquisition with PID Control CX2000' -> CX2000
            m_trail = re.search(r'\b([A-Z]{1,4}\d{3,5}[A-Z0-9\-]*)$', clean_model)
            if m_trail and len(clean_model.split()) > 2 and not any(k in clean_model.lower() for k in ("mark", "series")):
                model_cand = m_trail.group(1)
                raw_alias = clean_model[:m_trail.start()].strip()
                clean_model = model_cand
                clean_model_upper = clean_model.upper()
            else:
                # Strip known generic category suffixes:
                clean_suf = re.sub(
                    r'\s+(?:Magnetic\s+Flow\s+Meters?|Two-wire\s+.*|Process\s+Gas\s+Chromatographs?|Field\s+Wireless\s+Gateways?|'
                    r'Data\s+Acquisition\s+Units?|Optical\s+Loss\s+Test\s+Sets?|Differential\s+Probes?.*|'
                    r'Confocal\s+Scanner\s+Units?|Optical\s+Spectrum\s+Analyzers?.*|Optical\s+Time\s+Domain\s+Reflectometers?.*|'
                    r'Power\s+Analyzers?.*|Digital\s+Oscilloscopes?.*|Digital\s+Multimeters?.*|'
                    r'Transmitters?/?Analyzers?.*|Personal\s+pH/ORP\s+Meters?|Thermocouple\s+.*|'
                    r'Synchronous\s+connecting\s+cables?|Rack\s+mounting\s+kits?|Soft\s+cases?.*|'
                    r'Analog\s+Voltage\s+Input\s+Modules?|High-Voltage\s+Isolation\s+Modules?)\b.*$',
                    '',
                    clean_model,
                    flags=re.I
                ).strip()
                if clean_suf and clean_suf != clean_model:
                    raw_alias = clean_model[len(clean_suf):].strip()
                    clean_model = clean_suf
                    clean_model_upper = clean_model.upper()

        # 1. Model Validation: Reject generic category noise
        if clean_model_upper.lower() in GENERIC_PRODUCT_CATEGORY_TOKENS:
            return None
        for pattern in DISALLOWED_CATEGORY_PATTERNS:
            if pattern.search(clean_model_upper):
                return None
        if not is_valid_product_model(clean_model):
            return None

        meta: Dict[str, Any] = dict(extra_meta or {})

        # 2. Alias Cleaning & Date Segregation
        clean_alias: Optional[str] = None
        if raw_alias:
            tokens = [t.strip() for t in re.split(r'[,;]+', str(raw_alias)) if t.strip()]
            valid_a = []
            for tok in tokens:
                if is_likely_date_str(tok):
                    try:
                        dt_obj = date_parser.parse(tok, fuzzy=True)
                        if "announcement_date_utc" not in meta:
                            meta["announcement_date_utc"] = dt_obj.strftime("%Y-%m-%d") + "T00:00:00Z"
                    except Exception:
                        pass
                elif tok.lower() in ("n/a", "none", "null", "nan", "-", "tbd", "unknown", "--") or tok.lower() == clean_model.lower():
                    continue
                else:
                    c_a = sanitize_alias_text(tok)
                    if c_a and is_valid_product_model(c_a) and c_a.lower() != clean_model.lower():
                        valid_a.append(c_a)
            if valid_a:
                clean_alias = ", ".join(dict.fromkeys(valid_a))

        # 3. Status Normalization
        norm_status = normalize_stage_name(raw_status or "Active")

        # 4. UTC Milestone Date Validation & ISO 8601 formatting
        clean_date: Optional[str] = parse_to_utc_iso(raw_date)
        if not clean_date and raw_date and raw_date.upper() not in (
            "N/A",
            "NONE",
            "-",
            "",
            "TBD",
            "NULL",
            "NAN",
        ):
            try:
                dt_obj = date_parser.parse(raw_date, fuzzy=False)
                if 1970 <= dt_obj.year <= 2099:
                    clean_date = dt_obj.strftime("%Y-%m-%d") + "T00:00:00Z"
            except Exception:
                clean_date = None

        # 5. Replacement Model Validation (Model name only, no boilerplate, no dates)
        clean_replacement: Optional[str] = None
        if raw_replacement:
            candidate = sanitize_alias_text(raw_replacement)
            if candidate:
                cand_lower = candidate.lower()
                if cand_lower in ("n/a", "none", "null", "nan", "-", "tbd", "unknown", "--", "contact sales", "refer to bulletin", "see bulletin", "consult representative") or is_likely_date_str(candidate):
                    clean_replacement = None
                else:
                    # Clean trailing descriptions from replacement model codes: e.g. 'SL2000 High-Speed Data Acquisition Unit' -> 'SL2000'
                    m_repl = re.match(r'^([A-Z0-9]{2,15}(?:[-/][A-Z0-9]{1,10})*)\s+(?:Series|High-Speed|Optical|Differential|Modular|Portable|ScopeCorder|Analog|Voltage|Terminator|Probe|Filter|Unit|Module|Package|Checker|Set|Cable|Kit)\b', candidate, flags=re.I)
                    if m_repl and (any(c.isdigit() for c in m_repl.group(1)) or len(m_repl.group(1)) <= 8):
                        candidate = m_repl.group(1)
                    if is_valid_replacement_model(candidate):
                        clean_replacement = candidate

        # 6. Metadata Enrichment
        if raw_replacement_category and raw_replacement_category.upper() not in (
            "N/A",
            "NONE",
            "-",
        ):
            meta["replacement_category"] = sanitize_alias_text(
                raw_replacement_category
            )
        if not clean_date:
            meta["missing_date"] = True

        return ProductRecord(
            vendor_name=vendor_name,
            model_name=clean_csv_field(clean_model, "model_name"),
            aliases=(
                clean_csv_field(clean_alias, "aliases") if clean_alias else None
            ),
            status=norm_status,
            stage=norm_status,
            vendor_status=norm_status,
            stage_date_utc=clean_date,
            source_url=source_url,
            category=category,
            replacement=(
                clean_csv_field(clean_replacement, "replacement")
                if clean_replacement
                else None
            ),
            metadata=meta,
        )
