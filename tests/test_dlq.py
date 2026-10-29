"""
Unit tests for Dead Letter Queue (DLQ).
"""

import tempfile
import unittest
from pathlib import Path

from scraper.dlq import DeadLetterQueue


class TestDeadLetterQueue(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dlq_file = Path(self.temp_dir.name) / "test_dlq.json"
        self.dlq = DeadLetterQueue(dlq_path=self.dlq_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_record_and_get_failures(self):
        self.assertEqual(len(self.dlq.get_failures()), 0)

        item = self.dlq.record_failure(
            url="https://example.com/broken",
            vendor_id="mitsubishi",
            error_type="ConnectionError",
            message="Connection refused by remote host",
            status_code=502,
            retry_count=3,
            details={"region": "Japan"}
        )
        self.assertEqual(item.vendor_id, "mitsubishi")
        self.assertEqual(item.status_code, 502)

        failures = self.dlq.get_failures()
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].url, "https://example.com/broken")
        self.assertEqual(failures[0].error_type, "ConnectionError")

        # Add second item for another vendor
        self.dlq.record_failure(
            url="https://siemens.com/error",
            vendor_id="siemens",
            error_type="Timeout",
            message="Read timeout"
        )
        all_failures = self.dlq.get_failures()
        self.assertEqual(len(all_failures), 2)

        # Filter by vendor
        m_failures = self.dlq.get_failures(vendor_id="mitsubishi")
        self.assertEqual(len(m_failures), 1)
        self.assertEqual(m_failures[0].vendor_id, "mitsubishi")

    def test_clear_dlq(self):
        self.dlq.record_failure(
            url="https://example.com/fail",
            vendor_id="rockwell",
            error_type="HttpError",
            message="404 Not Found"
        )
        self.assertEqual(len(self.dlq.get_failures()), 1)
        cleared = self.dlq.clear()
        self.assertTrue(cleared)
        self.assertEqual(len(self.dlq.get_failures()), 0)


if __name__ == "__main__":
    unittest.main()
