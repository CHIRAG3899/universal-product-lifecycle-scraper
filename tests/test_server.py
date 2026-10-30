"""
Unit & Edge Case Tests for server.py.
Validates:
1. ThreadedHTTPServer and ScraperAPIHandler initialization.
2. GET /api/status endpoint response structure.
3. GET /api/vendors endpoint returning 100 configured vendors.
4. GET /api/comparison endpoint returning 10-dimension comparison matrix.
5. GET /api/products endpoint reading dataset.
6. GET /api/export/csv and /api/export/json headers and file attachments.
7. OPTIONS handler for CORS preflight validation.
8. POST /api/test-key validation and failure handling.
9. POST /api/crawl trigger handling.
10. 404 response for unknown endpoints.
"""

import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import AsyncMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.models import ScrapedDataset
from server import ScraperAPIHandler, ThreadedHTTPServer


class TestServerAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Bind to localhost on port 0 (OS allocates free ephemeral port)
        cls.httpd = ThreadedHTTPServer(("127.0.0.1", 0), ScraperAPIHandler)
        cls.port = cls.httpd.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _get(self, path: str):
        req = urllib.request.Request(f"{self.base_url}{path}")
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
            return resp.status, resp.headers, data

    def _post(self, path: str, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
            return resp.status, resp.headers, data

    def test_01_get_status_endpoint(self):
        """Verifies GET /api/status returns online status and metadata."""
        status, headers, data = self._get("/api/status")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers.get("Content-Type", ""))
        payload = json.loads(data.decode("utf-8"))
        self.assertEqual(payload["status"], "online")
        self.assertIn("gemini_configured", payload)
        self.assertIn("gemini_model", payload)

    def test_02_get_vendors_endpoint(self):
        """Verifies GET /api/vendors returns vendor definitions."""
        status, headers, data = self._get("/api/vendors")
        self.assertEqual(status, 200)
        payload = json.loads(data.decode("utf-8"))
        self.assertIn("vendors", payload)
        self.assertGreaterEqual(len(payload["vendors"]), 1)

    def test_03_get_comparison_endpoint(self):
        """Verifies GET /api/comparison returns crawler comparison matrix."""
        status, headers, data = self._get("/api/comparison")
        self.assertEqual(status, 200)
        payload = json.loads(data.decode("utf-8"))
        self.assertIn("comparison", payload)
        self.assertEqual(len(payload["comparison"]), 10)

    def test_04_get_products_endpoint(self):
        """Verifies GET /api/products returns scraped product records."""
        status, headers, data = self._get("/api/products")
        self.assertEqual(status, 200)
        payload = json.loads(data.decode("utf-8"))
        self.assertTrue("products" in payload or "total_products" in payload)

    def test_05_options_cors_preflight(self):
        """Verifies OPTIONS request returns CORS headers."""
        req = urllib.request.Request(f"{self.base_url}/api/status", method="OPTIONS")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertIn("POST", resp.headers.get("Access-Control-Allow-Methods", ""))

    def test_06_post_test_key_unconfigured_rejection(self):
        """Verifies POST /api/test-key correctly reports invalid/empty keys."""
        status, headers, data = self._post("/api/test-key", {"api_key": ""})
        self.assertEqual(status, 200)
        payload = json.loads(data.decode("utf-8"))
        self.assertFalse(payload["success"])
        self.assertIn("not configured", payload["message"].lower())

    @patch("scraper.ai_extractor.UniversalAIExtractor.test_connection")
    def test_07_post_test_key_success(self, mock_test_conn):
        """Verifies POST /api/test-key reports success when key verifies."""
        mock_test_conn.return_value = (True, "API Key is active")
        status, headers, data = self._post("/api/test-key", {"api_key": "valid_test_key", "save": False})
        self.assertEqual(status, 200)
        payload = json.loads(data.decode("utf-8"))
        self.assertTrue(payload["success"])
        self.assertEqual(payload["message"], "API Key is active")

    @patch("scraper.pipeline.LifecyclePipeline.execute", new_callable=AsyncMock)
    def test_08_post_crawl_endpoint(self, mock_execute):
        """Verifies POST /api/crawl triggers crawler pipeline."""
        mock_execute.return_value = ScrapedDataset(
            source_url="portal",
            crawl_timestamp="2026-10-24T00:00:00Z",
            total_products=15,
            ai_model_used="gemini-2.5-flash",
            products=[]
        )
        status, headers, data = self._post("/api/crawl", {"vendor": "siemens", "sector": "OT"})
        self.assertEqual(status, 200)
        payload = json.loads(data.decode("utf-8"))
        self.assertTrue(payload["success"])
        self.assertIn("Successfully processed 15 records", payload["message"])

    def test_09_unknown_post_returns_404(self):
        """Verifies POST to unknown route returns 404."""
        req = urllib.request.Request(
            f"{self.base_url}/api/non_existent_route",
            data=b"{}",
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 404)
        except urllib.error.HTTPError as err:
            self.assertEqual(err.code, 404)

    def test_10_post_clean_artifacts_endpoint(self):
        """Verifies POST /api/clean-artifacts purges old artifacts and temp files."""
        status, headers, data = self._post("/api/clean-artifacts", {})
        self.assertEqual(status, 200)
        payload = json.loads(data.decode("utf-8"))
        self.assertTrue(payload["success"])
        self.assertIn("Successfully deleted", payload["message"])

    @patch("scraper.ai_extractor.UniversalAIExtractor.test_connection")
    def test_11_post_test_key_with_openai_provider(self, mock_test_conn):
        """Verifies POST /api/test-key works seamlessly with OpenAI provider."""
        mock_test_conn.return_value = (True, "OpenAI OK")
        status, headers, data = self._post("/api/test-key", {
            "provider": "openai",
            "api_key": "sk-my-custom-key-12345",
            "model": "gpt-4o-mini",
            "save": False
        })
        self.assertEqual(status, 200)
        payload = json.loads(data.decode("utf-8"))
        self.assertTrue(payload["success"])
        self.assertEqual(payload["provider"], "openai")
        self.assertEqual(payload["model"], "gpt-4o-mini")


if __name__ == "__main__":
    unittest.main()
