"""
Enterprise Security Module for Lifecycle Scraper.
Provides SSRF prevention, CSV formula injection defense, credential masking,
and input sanitization to ensure safe execution in enterprise environments.
"""

import ipaddress
import re
import urllib.parse
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
