"""
Unit tests for Persistent Resumable Crawler Memory and State Management (scraper.state).
"""

import tempfile
import unittest
from pathlib import Path

from scraper.state import VendorRunState


class TestVendorRunState(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_init_and_file_path(self):
        state = VendorRunState("Rockwell Automation (Allen-Bradley)", state_dir=self.state_dir)
        self.assertEqual(state.vendor_id, "Rockwell Automation (Allen-Bradley)")
        self.assertTrue(state.file_path.name.endswith(".json"))
        self.assertIn("rockwell_automation__allen-bradley_", state.file_path.name)

    def test_completed_units(self):
        state = VendorRunState("test_vendor", state_dir=self.state_dir)
        self.assertFalse(state.is_unit_completed("https://example.com/sitemap.xml"))

        state.mark_unit_completed("https://example.com/sitemap.xml")
        self.assertTrue(state.is_unit_completed("https://example.com/sitemap.xml"))
        # Case insensitive & whitespace trimmed check
        self.assertTrue(state.is_unit_completed("  HTTPS://EXAMPLE.COM/SITEMAP.XML  "))

    def test_seen_models(self):
        state = VendorRunState("test_vendor", state_dir=self.state_dir)
        self.assertFalse(state.is_model_seen("1756-L85E"))

        state.record_model("1756-L85E")
        self.assertTrue(state.is_model_seen("1756-l85e"))
        self.assertTrue(state.is_model_seen("  1756-L85E  "))

    def test_discovered_prefixes(self):
        state = VendorRunState("test_vendor", state_dir=self.state_dir)
        self.assertEqual(state.discovered_prefixes, set())

        state.record_discovered_prefix("1756")
        state.record_discovered_prefix("PL-CCP")
        state.record_discovered_prefix("20-")
        # Duplicate record should not duplicate
        state.record_discovered_prefix("1756")

        prefixes = state.discovered_prefixes
        self.assertIn("1756", prefixes)
        self.assertIn("PL-CCP", prefixes)
        self.assertIn("20-", prefixes)
        self.assertEqual(len(prefixes), 3)

    def test_save_and_load_roundtrip(self):
        state = VendorRunState("vendor_1", state_dir=self.state_dir)
        state.mark_unit_completed("https://example.com/page1")
        state.record_model("MODEL-A")
        state.record_discovered_prefix("MOD-")
        state.total_records = 42
        state.save()

        self.assertTrue(state.file_path.exists())

        loaded = VendorRunState.load("vendor_1", state_dir=self.state_dir)
        self.assertTrue(loaded.is_unit_completed("https://example.com/page1"))
        self.assertTrue(loaded.is_model_seen("MODEL-A"))
        self.assertIn("MOD-", loaded.discovered_prefixes)
        self.assertEqual(loaded.total_records, 42)

    def test_load_non_existent(self):
        loaded = VendorRunState.load("non_existent_vendor", state_dir=self.state_dir)
        self.assertEqual(loaded.vendor_id, "non_existent_vendor")
        self.assertEqual(len(loaded.completed_units), 0)
        self.assertEqual(len(loaded.seen_models), 0)
        self.assertEqual(loaded.total_records, 0)

    def test_load_corrupted_json(self):
        corrupt_file = self.state_dir / "corrupted_vendor_state.json"
        corrupt_file.write_text("{invalid json syntax", encoding="utf-8")

        loaded = VendorRunState.load("corrupted_vendor", state_dir=self.state_dir)
        self.assertEqual(loaded.vendor_id, "corrupted_vendor")
        self.assertEqual(len(loaded.completed_units), 0)


if __name__ == "__main__":
    unittest.main()
