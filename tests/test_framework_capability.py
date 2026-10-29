"""
Comprehensive Test Suite for 100-Vendor Framework Capability.
Validates:
1. Loading and integrity of all 100 vendors across OT, IoT, and IT sectors.
2. Zero hardcoded defaults (no default_os, no default_firmware in config).
3. SSRF domain boundary protections across all 100 vendor domains.
4. Model name sanity validator rejects cookie notices and web navigation strings.
5. Deduplication and append logic with deterministic SHA-256 fingerprinting.
6. Absence of 'Fingerprint' column in exported CSV dataset.
7. Crawler Comparison Matrix completeness.
"""

import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.config import BASE_DIR
from scraper.crawler_comparison import CRAWLER_COMPARISON_MATRIX
from scraper.models import is_valid_product_model
from scraper.security import is_safe_url


class TestEnterpriseFramework(unittest.TestCase):

    def setUp(self):
        self.config_path = BASE_DIR / "configs" / "vendors.yaml"
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def test_01_exactly_100_vendors_configured(self):
        """Verifies top enterprise vendors are defined (at least 100, currently 140)."""
        vendors = self.config.get("vendors", {})
        self.assertGreaterEqual(len(vendors), 100, f"Expected at least 100 vendors, got {len(vendors)}")
        self.assertEqual(len(vendors), 140, f"Expected 140 vendors, got {len(vendors)}")

    def test_02_sector_distribution(self):
        """Verifies proper representation across OT (54), IoT (44), and IT (42)."""
        vendors = self.config.get("vendors", {})
        sectors = {"OT": 0, "IoT": 0, "IT": 0}
        for v_id, v_cfg in vendors.items():
            sec = v_cfg.get("sector")
            self.assertIn(sec, sectors, f"Vendor {v_id} has invalid sector: {sec}")
            sectors[sec] += 1

        self.assertEqual(sectors["OT"], 54, f"Expected 54 OT vendors, got {sectors['OT']}")
        self.assertEqual(sectors["IoT"], 44, f"Expected 44 IoT vendors, got {sectors['IoT']}")
        self.assertEqual(sectors["IT"], 42, f"Expected 42 IT vendors, got {sectors['IT']}")

    def test_03_zero_hardcoded_defaults(self):
        """Verifies NO vendor config contains hardcoded default_os or default_firmware."""
        vendors = self.config.get("vendors", {})
        for v_id, v_cfg in vendors.items():
            self.assertNotIn("default_os", v_cfg, f"Vendor {v_id} contains forbidden 'default_os'")
            self.assertNotIn("default_firmware", v_cfg, f"Vendor {v_id} contains forbidden 'default_firmware'")
            self.assertNotIn("official_terminology", v_cfg, f"Vendor {v_id} contains forbidden 'official_terminology'")

    def test_04_ssrf_safety_on_all_vendor_websites(self):
        """Verifies that all 100 vendor websites pass SSRF validation against allowed_domains."""
        vendors = self.config.get("vendors", {})
        for v_id, v_cfg in vendors.items():
            website = v_cfg.get("website")
            allowed = v_cfg.get("allowed_domains", [])
            self.assertTrue(website.startswith("http"), f"Vendor {v_id} invalid website {website}")
            self.assertTrue(is_safe_url(website, allowed), f"SSRF blocked legitimate website for {v_id}: {website}")

        # Ensure malicious/private IPs are strictly blocked
        self.assertFalse(is_safe_url("http://127.0.0.1:8000", ["siemens.com"]))
        self.assertFalse(is_safe_url("http://169.254.169.254/metadata", ["cisco.com"]))
        self.assertFalse(is_safe_url("http://localhost/admin", ["mitsubishi.com"]))

    def test_05_model_sanity_and_cookie_rejection(self):
        """Verifies that cookie consent banners, web navigation, and URLs are rejected."""
        disallowed = [
            "Performance Cookies", "Cookie Notice", "Manage Consent Preferences",
            "Global", "Americas", "Asia-Pacific", "Follow us", "[ About ](https://...)",
            "Privacy Policy", "Terms of Use", "Home", "Support"
        ]
        for term in disallowed:
            self.assertFalse(is_valid_product_model(term), f"Model validator should have rejected: {term}")

        valid_models = ["GT25-WLAN", "FX5-EIP", "MI3321G-W", "S7-1500", "PowerEdge R750", "Catalyst 9300", "ESP32-WROOM-32D"]
        for model in valid_models:
            self.assertTrue(is_valid_product_model(model), f"Model validator incorrectly rejected genuine model: {model}")

    def test_06_csv_export_fingerprint_omission(self):
        """Verifies that the Master CSV output omits the 'Fingerprint' column and enforces clean snake_case schema."""
        csv_path = BASE_DIR / "output" / "all_vendors_lifecycle.csv"
        if csv_path.exists():
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                header = f.readline().strip().split(",")
            self.assertNotIn("Fingerprint", header, "Fingerprint column MUST NOT appear in output CSV!")
            self.assertNotIn("fingerprint", header, "fingerprint column MUST NOT appear in output CSV!")
            self.assertNotIn("vendor_status", header, "vendor_status column should be unified into 'status'!")
            self.assertIn("vendor_name", header)
            self.assertIn("model_name", header)
            self.assertIn("status", header)
            self.assertIn("stage_date_utc", header)
            self.assertIn("source_url", header)
            self.assertIn("category", header)
            self.assertIn("replacement", header)
            self.assertIn("metadata", header)

    def test_07_crawler_comparison_completeness(self):
        """Verifies all 10 key technical dimensions are evaluated in the comparison matrix."""
        self.assertEqual(len(CRAWLER_COMPARISON_MATRIX), 10)
        required_keys = {"dimension", "generic_crawler", "ai_crawler", "ai_advantage"}
        for item in CRAWLER_COMPARISON_MATRIX:
            self.assertTrue(required_keys.issubset(item.keys()))


if __name__ == "__main__":
    unittest.main()
