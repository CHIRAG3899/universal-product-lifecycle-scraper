"""
Unit Tests for scraper/config.py
Validates paths, default configuration parameters, and environment overrides.
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.config import BASE_DIR as CFG_BASE_DIR
from scraper.config import (
    DEFAULT_CSV_OUTPUT,
    DEFAULT_JSON_OUTPUT,
    GEMINI_MODEL,
    MITSUBISHI_EOL_URLS,
    OUTPUT_DIR,
    REQUEST_TIMEOUT_SEC,
    USER_AGENT,
)


class TestConfig(unittest.TestCase):

    def test_base_and_output_paths(self):
        self.assertTrue(CFG_BASE_DIR.exists())
        self.assertTrue(OUTPUT_DIR.exists())
        self.assertEqual(OUTPUT_DIR, CFG_BASE_DIR / "output")

    def test_default_gemini_model(self):
        self.assertIn("gemini", GEMINI_MODEL.lower())

    def test_mitsubishi_portal_urls(self):
        self.assertIsInstance(MITSUBISHI_EOL_URLS, list)
        self.assertTrue(len(MITSUBISHI_EOL_URLS) >= 1)
        for url in MITSUBISHI_EOL_URLS:
            self.assertTrue(url.startswith("https://"))
            self.assertIn("mitsubishielectric.com", url)

    def test_crawler_settings(self):
        self.assertTrue("Mozilla" in USER_AGENT)
        self.assertIsInstance(REQUEST_TIMEOUT_SEC, int)
        self.assertTrue(REQUEST_TIMEOUT_SEC > 0)

    def test_export_file_paths(self):
        self.assertTrue(str(DEFAULT_JSON_OUTPUT).endswith(".json"))
        self.assertTrue(str(DEFAULT_CSV_OUTPUT).endswith(".csv"))

    def test_vendor_yaml_key_uniqueness_and_counts(self):
        """Verifies zero duplicate YAML keys, zero duplicate vendor names, and exact 140 vendor catalog."""
        import re
        from collections import Counter

        import yaml

        vendors_yaml = CFG_BASE_DIR / "configs" / "vendors.yaml"
        self.assertTrue(vendors_yaml.exists(), "configs/vendors.yaml must exist")

        with open(vendors_yaml, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()

        raw_keys = []
        in_vendors = False
        for line in raw_lines:
            stripped = line.rstrip()
            if stripped == "vendors:":
                in_vendors = True
                continue
            if in_vendors:
                m = re.match(r"^  ([a-zA-Z0-9_]+):", stripped)
                if m:
                    raw_keys.append(m.group(1))

        key_counts = Counter(raw_keys)
        overwritten = {k: c for k, c in key_counts.items() if c > 1}
        self.assertEqual(len(overwritten), 0, f"Found duplicate raw YAML keys: {overwritten}")

        with open(vendors_yaml, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        vendors = data.get("vendors", {})
        self.assertEqual(len(vendors), 140, f"Expected exactly 140 vendors, found {len(vendors)}")

        sectors = Counter(v.get("sector") for v in vendors.values())
        self.assertEqual(sectors["OT"], 54, f"Expected 54 OT vendors, found {sectors['OT']}")
        self.assertEqual(sectors["IoT"], 44, f"Expected 44 IoT vendors, found {sectors['IoT']}")
        self.assertEqual(sectors["IT"], 42, f"Expected 42 IT vendors, found {sectors['IT']}")

        # Ensure all names are unique
        names = [v.get("name") for v in vendors.values()]
        name_counts = Counter(names)
        dup_names = {n: c for n, c in name_counts.items() if c > 1}
        self.assertEqual(len(dup_names), 0, f"Found duplicate vendor names: {dup_names}")


if __name__ == "__main__":
    unittest.main()
