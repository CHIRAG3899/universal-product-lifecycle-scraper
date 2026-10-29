"""
Unit & Edge Case Tests for scraper/security.py
Validates SSRF protection, CSV formula injection defense, and secret masking.
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.security import is_safe_url, mask_secret, sanitize_csv_cell


class TestSecurity(unittest.TestCase):

    # -------------------------------------------------------------------------
    # 1. SSRF Protection Tests (is_safe_url)
    # -------------------------------------------------------------------------
    def test_safe_public_urls(self):
        safe_urls = [
            "https://se-fa.mitsubishielectric.com/fa/se_en/support/product-life-cycle-stage-eol",
            "https://mall.industry.siemens.com/mall/en/ww/Catalog/Products/1000000",
            "https://www.cisco.com/c/en/us/products/eos-eol-listing.html",
            "http://example.com/support/lifecycle"
        ]
        for url in safe_urls:
            with self.subTest(url=url):
                self.assertTrue(is_safe_url(url), f"Should allow public safe URL: {url}")

    def test_reject_private_and_loopback_ips(self):
        blocked_ips = [
            "http://127.0.0.1:8000/admin",
            "http://127.0.0.2/test",
            "http://10.0.0.1/secrets",
            "http://10.254.254.254/vault",
            "http://172.16.0.1/internal",
            "http://172.31.255.255/conf",
            "http://192.168.1.1/router",
            "http://192.168.0.100/api",
            "http://169.254.169.254/latest/meta-data/",  # Cloud Metadata Endpoint
            "http://[::1]:8080/admin",
            "http://2130706433:8000/",   # Decimal encoded loopback (127.0.0.1)
            "http://0x7f000001/admin",   # Hex encoded loopback (127.0.0.1)
            "http://0.0.0.0:8000/",       # Unspecified IPv4
            "http://[::]:8000/"          # Unspecified IPv6
        ]
        for url in blocked_ips:
            with self.subTest(url=url):
                self.assertFalse(is_safe_url(url), f"Should block private/internal IP: {url}")

    def test_reject_internal_hostnames(self):
        blocked_hostnames = [
            "http://localhost:8000/",
            "http://localhost/admin",
            "http://metadata/computeMetadata/v1/",
            "http://instance-data/latest/"
        ]
        for url in blocked_hostnames:
            with self.subTest(url=url):
                self.assertFalse(is_safe_url(url), f"Should block internal hostname: {url}")

    def test_reject_non_http_schemes(self):
        blocked_schemes = [
            "ftp://files.example.com/dump.zip",
            "file:///etc/passwd",
            "file:///c:/windows/system32/cmd.exe",
            "gopher://127.0.0.1:70/",
            "data:text/html,<script>alert(1)</script>",
            "javascript:alert(1)"
        ]
        for url in blocked_schemes:
            with self.subTest(url=url):
                self.assertFalse(is_safe_url(url), f"Should block non-http scheme: {url}")

    def test_allowed_domains_enforcement(self):
        whitelist = ["mitsubishielectric.com", "siemens.com"]
        self.assertTrue(is_safe_url("https://mitsubishielectric.com/support", allowed_domains=whitelist))
        self.assertTrue(is_safe_url("https://se-fa.mitsubishielectric.com/eol", allowed_domains=whitelist))
        self.assertTrue(is_safe_url("https://mall.industry.siemens.com/catalog", allowed_domains=whitelist))
        # Unauthorized domain outside whitelist
        self.assertFalse(is_safe_url("https://malicious-site.com/eol", allowed_domains=whitelist))
        self.assertFalse(is_safe_url("https://fake-mitsubishielectric.com.evil.com", allowed_domains=whitelist))

    def test_invalid_url_edge_cases(self):
        self.assertFalse(is_safe_url(None))
        self.assertFalse(is_safe_url(""))
        self.assertFalse(is_safe_url("   "))
        self.assertFalse(is_safe_url("not_a_valid_url"))
        self.assertFalse(is_safe_url("http:///"))  # Missing hostname

    # -------------------------------------------------------------------------
    # 2. CSV Formula Injection Defense (sanitize_csv_cell)
    # -------------------------------------------------------------------------
    def test_sanitize_csv_formula_injection(self):
        malicious_inputs = [
            "=SUM(A1:A10)",
            "+CMD('calc')",
            "-2+3*4",
            "@HYPERLINK('http://evil.com')",
            "\t=1+1",
            "\r=cmd.exe"
        ]
        for item in malicious_inputs:
            sanitized = sanitize_csv_cell(item)
            with self.subTest(item=item):
                self.assertTrue(sanitized.startswith("'"), f"Dangerous formula character should be prefixed with single quote: {sanitized}")

    def test_sanitize_csv_cell_clean_inputs(self):
        self.assertEqual(sanitize_csv_cell("Mitsubishi Electric"), "Mitsubishi Electric")
        self.assertEqual(sanitize_csv_cell("MI3321G-W"), "MI3321G-W")
        self.assertEqual(sanitize_csv_cell("End of Life (EOL)"), "End of Life (EOL)")
        self.assertEqual(sanitize_csv_cell(None), "")
        self.assertEqual(sanitize_csv_cell(""), "")
        self.assertEqual(sanitize_csv_cell(12345), "12345")

    # -------------------------------------------------------------------------
    # 3. Secret Masking Tests (mask_secret)
    # -------------------------------------------------------------------------
    def test_mask_secret(self):
        self.assertEqual(mask_secret(None), "********")
        self.assertEqual(mask_secret(""), "********")
        self.assertEqual(mask_secret("short"), "********")
        # Normal API key format: keep first 4 and last 4
        masked = mask_secret("AIzaSyAbc1234567890Xyz")
        self.assertTrue(masked.startswith("AIza****"))
        self.assertTrue(masked.endswith("0Xyz"))
        self.assertNotIn("123456789", masked)


if __name__ == "__main__":
    unittest.main()
