"""
Pydantic data models for Enterprise Multi-Vendor Lifecycle Scraper.
Database-ready normalization, semantic firmware cleaning, vendor-exact terminology,
UTC date normalization, and record fingerprinting for append/upsert operations.
"""

import calendar
import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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


COOKIE_AND_POLICY_SUBSTRINGS = {
    "performance cookies", "cookie notice", "manage consent preferences", "consent preferences",
    "strictly necessary cookies", "functional cookies", "targeting cookies", "cookies settings",
    "cookie policy", "cookie", "privacy policy", "terms of use", "terms and conditions",
    "all rights reserved"
}

EXACT_DISALLOWED_MODEL_TOKENS = {
    "global", "americas", "asia-pacific", "europe", "europe, cis, middle east & africa",
    "follow us", "about", "sustainability", "news", "contact us", "site map", "disclaimer", "copyright",
    "search", "home", "products", "solutions", "support", "downloads", "training",
    "main series", "complete series", "expansion units", "all models", "n/a", "none",
    "series", "model", "models", "part number", "part numbers", "product", "item", "description"
}


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
    # Reject strings that start with conversational / instructional text
    if any(c_lower.startswith(p) for p in ("consult ", "see ", "official ", "click ", "read ", "download ", "view ", "affects ")):
        return False

    # Must contain at least one alphanumeric character
    if not re.search(r'[A-Za-z0-9]', check_str):
        return False

    # Strictly enforce alphanumeric + standard sensible symbols: - / : . _ + & ( ) # space
    if not re.match(r'^[A-Za-z0-9\-_/:.+&()# ]+$', check_str):
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

    # Normalize commas in dates (e.g. "September, 2024" -> "September 2024")
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

    # Pattern: Standard YYYY-MM-DD or YYYY/MM/DD
    m_iso = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', cleaned)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        return _safe_make_utc(y, m, d)

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
    m_yr = re.search(r'\b(20\d{2}|19\d{2})\b', cleaned)
    if m_yr:
        y = int(m_yr.group(1))
        return _safe_make_utc(y, 12, 31)

    return None


def _safe_make_utc(year: int, month: int, day: int) -> str:
    """Clamps invalid days (e.g. Nov 31 -> Nov 30) and produces UTC ISO string."""
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

            # If stage_date_utc is missing or empty, attempt recovery from bulletin code or metadata
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
                    data["stage_date_utc"] = None
                    if "metadata" not in data or not isinstance(data.get("metadata"), dict):
                        data["metadata"] = {}
                    data["metadata"]["missing_date"] = True

            # Model is allowed empty ONLY for software applications or well-known OS entries (e.g. Linux, Debian, Windows)
            cat = (data.get("category") or data.get("product_category") or "").strip()
            os_val = (data.get("os") or "").strip()
            model_val = data.get("model_name")
            is_sw_or_os = is_well_known_os_or_software(category=cat, os_name=os_val, model_name=str(model_val or ""))
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
            return None
        cleaned = v.strip()
        if cleaned.endswith("Z") and "T" in cleaned:
            return cleaned
        parsed = parse_to_utc_iso(cleaned)
        if not parsed:
            # Missing or unparseable dates should not drop genuine lifecycle models
            return None
        return parsed

    @field_validator("replacement", mode="before")
    def clean_replacement(cls, v):
        if not v:
            return None
        s = str(v).strip()
        if not s or s.lower() in ("n/a", "none", "null", "-", "--", "nan", "unknown"):
            return None
        if any(kw in s.lower() for kw in ["consult", "representative", "official sales", "contact your", "sales rep"]):
            return None
        return s

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

        if candidate_repl:
            c_str = str(candidate_repl).strip()
            if c_str.lower() in ("n/a", "none", "null", "-", "--", "nan", "unknown") or any(kw in c_str.lower() for kw in ["consult", "representative", "official sales", "contact your", "sales rep"]):
                self.replacement = None
            else:
                self.replacement = c_str
        else:
            self.replacement = None

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
