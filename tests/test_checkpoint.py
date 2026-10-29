"""
Unit tests for Checkpoint & Failure Resume Engine.
"""

import tempfile
import unittest
from pathlib import Path

from scraper.checkpoint import CheckpointManager


class TestCheckpointManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cp_file = Path(self.temp_dir.name) / "test_checkpoint.json"
        self.mgr = CheckpointManager(checkpoint_path=self.cp_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_has_checkpoint_initially_false(self):
        self.assertFalse(self.mgr.has_checkpoint())
        self.assertIsNone(self.mgr.load_checkpoint())

    def test_save_and_load_checkpoint(self):
        state = self.mgr.save_checkpoint(
            vendor_id="cisco_systems",
            run_id="run_20261025_001",
            status="failed",
            failed_url="https://www.cisco.com/broken-portal",
            error_message="HTTP 504 Gateway Timeout",
            completed_urls=["https://www.cisco.com/c/en/us/products/eos-eol-listing.html"],
            pending_urls=["https://www.cisco.com/broken-portal", "https://www.cisco.com/next"],
            completed_vendors=["siemens", "rockwell"],
            pending_vendors=["cisco_systems", "mitsubishi"],
            harvested_records_count=24
        )

        self.assertEqual(state.vendor_id, "cisco_systems")
        self.assertTrue(self.mgr.has_checkpoint())
        self.assertTrue(self.mgr.has_checkpoint("cisco_systems"))
        self.assertFalse(self.mgr.has_checkpoint("omron"))

        loaded = self.mgr.load_checkpoint()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.failed_url, "https://www.cisco.com/broken-portal")
        self.assertEqual(loaded.error_message, "HTTP 504 Gateway Timeout")
        self.assertEqual(len(loaded.pending_urls), 2)
        self.assertEqual(len(loaded.completed_vendors), 2)
        self.assertEqual(loaded.harvested_records_count, 24)

    def test_clear_checkpoint(self):
        self.mgr.save_checkpoint(
            vendor_id="mitsubishi",
            run_id="run_002",
            status="interrupted"
        )
        self.assertTrue(self.mgr.has_checkpoint())
        cleaned = self.mgr.clear_checkpoint()
        self.assertTrue(cleaned)
        self.assertFalse(self.mgr.has_checkpoint())
        self.assertIsNone(self.mgr.load_checkpoint())


if __name__ == "__main__":
    unittest.main()
