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

    def test_categorize_http_status(self):
        from scraper.dlq import categorize_http_status
        self.assertEqual(categorize_http_status(301), "HTTP_301_REDIRECT")
        self.assertEqual(categorize_http_status(400), "HTTP_400_BAD_REQUEST")
        self.assertEqual(categorize_http_status(403), "HTTP_403_BOT_BLOCK")
        self.assertEqual(categorize_http_status(404), "HTTP_404_NOT_FOUND")
        self.assertEqual(categorize_http_status(429), "HTTP_429_RATE_LIMITED")
        self.assertEqual(categorize_http_status(500), "HTTP_500_SERVER_ERROR")
        self.assertEqual(categorize_http_status(502), "HTTP_502_BAD_GATEWAY")
        self.assertEqual(categorize_http_status(503), "HTTP_503_SERVICE_UNAVAILABLE")
        self.assertEqual(categorize_http_status(504), "HTTP_504_GATEWAY_TIMEOUT")
        self.assertEqual(categorize_http_status(None), "FETCH_ERROR")

    def test_summary_and_export_and_retryable(self):
        self.dlq.record_failure("https://a.com/404", "siemens", "HTTP_404_NOT_FOUND", "Not found", status_code=404)
        self.dlq.record_failure("https://b.com/500", "siemens", "HTTP_500_SERVER_ERROR", "Internal error", status_code=500)
        self.dlq.record_failure("https://c.com/403", "omron", "HTTP_403_BOT_BLOCK", "Cloudflare block", status_code=403)
        # Deduplication check: re-recording exact same URL and status code shouldn't duplicate
        self.dlq.record_failure("https://c.com/403", "omron", "HTTP_403_BOT_BLOCK", "Cloudflare block", status_code=403)

        summary = self.dlq.get_summary()
        self.assertEqual(summary["total_failures"], 3)
        self.assertEqual(summary["by_status_code"]["404"], 1)
        self.assertEqual(summary["by_status_code"]["500"], 1)
        self.assertEqual(summary["by_status_code"]["403"], 1)
        self.assertEqual(summary["by_vendor"]["siemens"], 2)
        self.assertEqual(summary["by_vendor"]["omron"], 1)

        retryable = self.dlq.get_retryable_failures()
        self.assertEqual(len(retryable), 2)
        retryable_codes = {it.status_code for it in retryable}
        self.assertIn(500, retryable_codes)
        self.assertIn(403, retryable_codes)

        export_target = Path(self.temp_dir.name) / "exported_failures.json"
        self.dlq.export_failures_json(export_target)
        self.assertTrue(export_target.exists())


if __name__ == "__main__":
    unittest.main()
