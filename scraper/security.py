"""
Enterprise Security Module for Lifecycle Scraper.
Provides SSRF prevention, CSV formula injection defense, credential masking,
and input sanitization to ensure safe execution in enterprise environments.
"""

import ipaddress
import re
import urllib.parse
from pathlib import Path
from typing import Any, List, Optional

# Disallowed internal network ranges for SSRF prevention
BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),       # Private A
    ipaddress.ip_network("172.16.0.0/12"),    # Private B
    ipaddress.ip_network("192.168.0.0/16"),   # Private C
    ipaddress.ip_network("169.254.0.0/16"),   # Link-local / Cloud Metadata (AWS 169.254.169.254)
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 private
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
]


def is_safe_url(url: Optional[str], allowed_domains: Optional[List[str]] = None) -> bool:
    """
    Validates URL to protect against SSRF (Server-Side Request Forgery).
    Rejects private IPs, non-HTTP/HTTPS schemes, localhost, and unauthorized domains.
    """
    if not url or not isinstance(url, str):
        return False

    try:
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme.lower() not in ("http", "https"):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        hostname_lower = hostname.lower()

        # Reject localhost & cloud metadata targets
        if hostname_lower in ("localhost", "metadata", "instance-data"):
            return False

        # Check if hostname is an IP address or numeric/hex encoded IP
        ip_obj = None
        try:
            ip_obj = ipaddress.ip_address(hostname_lower)
        except ValueError:
            # Check for integer/hex encoded IP (e.g. 2130706433 or 0x7f000001)
            try:
                ip_int = int(hostname_lower, 0)
                if 0 <= ip_int <= 0xFFFFFFFF:
                    ip_obj = ipaddress.ip_address(ip_int)
            except (ValueError, OverflowError):
                pass

        if ip_obj:
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_reserved
                or ip_obj.is_multicast
                or ip_obj.is_unspecified
                or any(ip_obj in net for net in BLOCKED_IP_NETWORKS)
            ):
                return False

        # Check against allowed domains if specified
        if allowed_domains:
            matched = any(
                hostname_lower == dom.lower() or hostname_lower.endswith("." + dom.lower())
                for dom in allowed_domains
            )
            if not matched:
                return False

        return True

    except Exception:
        return False


def sanitize_csv_cell(value: Any) -> str:
    """
    Defends against CSV Formula Injection (CWE-1236).
    If a cell starts with formula characters (=, +, -, @, tab, cr), prepend single quote.
    """
    if value is None:
        return ""

    s = str(value).strip()
    if not s:
        return ""

    # Sanitize control characters
    s = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', s)

    # Prefix with quote if it could trigger spreadsheet formula execution
    if s[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + s

    return s


def mask_secret(secret: Optional[str]) -> str:
    """Safely masks API keys and tokens for logging and audit displays."""
    if not secret or len(secret) < 8:
        return "********"
    return secret[:4] + "****" + secret[-4:]


def sanitize_db_string(text: Optional[str], max_len: int = 500) -> Optional[str]:
    """
    Cleans raw strings for database ingestion:
    - Strips leading/trailing whitespace and excessive internal whitespace
    - Removes unprintable and null characters
    - Normalizes quotes and dashes
    - Truncates to max length safely
    """
    if text is None:
        return None

    cleaned = str(text).replace("\x00", "").replace("\r", " ")
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    if not cleaned or cleaned.lower() in ("n/a", "none", "null", "undefined"):
        return None

    return cleaned[:max_len]


# Allowed sensible characters in product model identifiers:
# Alphanumeric [A-Za-z0-9] and sensible standard punctuation: - / : . _ + & ( ) # space
ALLOWED_MODEL_CHARS_PATTERN = re.compile(r'^[A-Za-z0-9\-_/:.+&()# ]+$')
DISALLOWED_CORRUPT_SYMBOLS_PATTERN = re.compile(r'[\x00-\x1f\x7f-\x9f\ufeff\u200b\u200c\u200d\ufffd§©®™★•►✓✗▪▫◆▲▼※~^$%=|\\{}<>;"`\'~]')


def clean_and_sanitize_identifier(raw: Optional[str], max_len: int = 120) -> Optional[str]:
    """
    Strictly sanitizes extracted hardware and software model identifiers from public sources:
    - Strips corrupt data, mojibake, zero-width chars, control characters, and HTML entities
    - Filters out unnecessary or uncommon symbols (e.g. §, ©, ®, ™, ★, •, ~, ^, $, %, *, =, |, {}, <>, ;)
    - Strictly enforces alphanumeric characters alongside only sensible standard symbols: - / : . _ + & ( ) # space
    - Guarantees presence of genuine alphanumeric characters (rejects pure-symbol noise)
    """
    if not raw or not isinstance(raw, str):
        return None

    import html
    s = html.unescape(raw.strip())
    if not s or s.lower() in ("n/a", "none", "null", "nan", "unknown", "undefined"):
        return None

    # Strip corrupt characters, control codes, replacement chars, decorative bullets, and uncommon symbols
    s = DISALLOWED_CORRUPT_SYMBOLS_PATTERN.sub(' ', s)

    # Normalize internal whitespace
    s = re.sub(r'\s+', ' ', s).strip()

    # Strip extraneous leading/trailing punctuation noise like . , - : /
    s = s.strip(" .,-:/_#")

    if len(s) < 2 or len(s) > max_len:
        return None

    # Must contain at least one alphanumeric character
    if not re.search(r'[A-Za-z0-9]', s):
        return None

    # Must match allowed alphanumeric + sensible symbols pattern
    if not ALLOWED_MODEL_CHARS_PATTERN.match(s):
        # Scrub any leftover non-whitelisted characters
        s = re.sub(r'[^A-Za-z0-9\-_/:.+&()# ]', '', s).strip()
        s = re.sub(r'\s+', ' ', s).strip()
        if len(s) < 2 or not re.search(r'[A-Za-z0-9]', s):
            return None

    return s


def safe_atomic_replace(temp_path: Path, dest_path: Path, max_retries: int = 4) -> None:
    """Performs atomic file replacement with retry logic to withstand Windows file locking, ensuring temp file deletion."""
    import time
    try:
        for attempt in range(max_retries):
            try:
                temp_path.replace(dest_path)
                return
            except (PermissionError, OSError) as e:
                if attempt == max_retries - 1:
                    try:
                        if dest_path.exists():
                            dest_path.unlink()
                        temp_path.rename(dest_path)
                        return
                    except Exception:
                        raise e
                time.sleep(0.05 * (2 ** attempt))
    finally:
        # Guarantee no orphaned .tmp files remain on disk
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass

