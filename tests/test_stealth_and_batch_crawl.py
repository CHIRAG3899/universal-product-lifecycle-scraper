"""
Unit tests for anti-bot stealth bypass, accumulated batch crawling mode,
and AI-driven vendor source discovery.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.crawl_engine import UniversalAICrawler
from scraper.models import ProductRecord
from scraper.run_cache import RunCache
from scripts.discover_vendor_sources import VendorSourceDiscoverer


class TestStealthAndBatchCrawl(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_extractor = MagicMock()
        self.mock_extractor.is_configured.return_value = False
        self.mock_extractor.batch_mode = False
        self.mock_extractor.provider = "gemini"
        self.mock_extractor.extract_from_markdown.return_value = []
        self.mock_extractor.extract_batch.return_value = []
        self.mock_extractor.fallback_rule_based_extraction.return_value = []
        self.run_cache = RunCache()
        self.crawler = UniversalAICrawler(extractor=self.mock_extractor, run_cache=self.run_cache)

    def test_01_prepare_page_chunks_with_tables_and_markdown(self):
        """Verifies that prepare_page_chunks parses DOM tables and body markdown into batch chunks."""
        crawl_data = {
            "url": "https://electronics.jtekt.co.jp/en/product/discon/",
            "markdown": "## TOYOPUC Discontinued Models\nGeneral notes on PLC migrations...",
            "html": """
            <html>
            <body>
              <table>
                <tr><th>Model</th><th>Status</th></tr>
                <tr><td>PC2J</td><td>Discontinued</td></tr>
                <tr><td>PC3JG</td><td>Discontinued</td></tr>
              </table>
            </body>
            </html>
            """,
            "status_code": 200,
            "extracted_content": None,
        }
        pre_recs, chunks = self.crawler.prepare_page_chunks(
            "https://electronics.jtekt.co.jp/en/product/discon/",
            crawl_data,
            vendor="JTEKT Toyoda",
            chunk_size=10
        )
        self.assertEqual(len(pre_recs), 0)
        self.assertGreaterEqual(len(chunks), 1)
        self.assertIn("PC2J", chunks[0]["markdown_chunk"])

    def test_02_extract_accumulated_batches_deduplication_and_replacements(self):
        """Verifies that extract_accumulated_batches parses accumulated chunks and enriches replacements."""
        rec1 = ProductRecord(
            vendor_name="JTEKT Toyoda",
            model_name="PC2J",
            status="Discontinued",
            stage_date_utc="2024-03-31T00:00:00Z"
        )
        rec2 = ProductRecord(
            vendor_name="JTEKT Toyoda",
            model_name="PC2J",
            status="Discontinued",
            stage_date_utc="2024-03-31T00:00:00Z"
        )
        rec3 = ProductRecord(
            vendor_name="JTEKT Toyoda",
            model_name="PC3JG",
            status="Discontinued",
            stage_date_utc=None
        )

        self.crawler._pdf_replacement_cache["https://example.com/bulletin.pdf"] = {
            "PC2J": "TOYOPUC-Plus",
            "PC3JG": "PC10G-CPU"
        }

        chunks = [{"markdown_chunk": "- PC2J: Discontinued\n- PC3JG: Discontinued", "context": "JTEKT", "source_url": "https://example.com"}]
        self.mock_extractor.extract_from_markdown.return_value = [rec1, rec2, rec3]

        products = self.crawler.extract_accumulated_batches(chunks, default_vendor="JTEKT Toyoda")
        self.assertEqual(len(products), 2)  # rec1 and rec2 deduplicated into 1
        model_names = {p.model_name for p in products}
        self.assertIn("PC2J", model_names)
        self.assertIn("PC3JG", model_names)

        # Check replacement enrichment
        pc2j_rec = next(p for p in products if p.model_name == "PC2J")
        self.assertEqual(pc2j_rec.replacement, "TOYOPUC-Plus")

    @patch("scraper.crawl_engine.AsyncWebCrawler")
    async def test_03_crawl_with_crawl4ai_stealth_config(self, mock_crawler_cls):
        """Verifies that Crawl4AI browser and run configs enforce stealth mode and realistic headers."""
        mock_crawler_instance = AsyncMock()
        mock_crawler_cls.return_value.__aenter__.return_value = mock_crawler_instance

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.status_code = 200
        mock_result.markdown = "# Discontinued Catalog\n- Model: TRD-2E"
        mock_result.html = "<html>Discontinued Catalog</html>"
        mock_result.extracted_content = None
        mock_crawler_instance.arun.return_value = mock_result

        res = await self.crawler.crawl_with_crawl4ai("https://electronics.jtekt.co.jp/en/product/discon/")
        self.assertEqual(res["status_code"], 200)
        self.assertIn("TRD-2E", res["markdown"])

        # Check browser_config passed to AsyncWebCrawler
        call_args = mock_crawler_cls.call_args
        browser_cfg = call_args.kwargs.get("config")
        self.assertTrue(browser_cfg.enable_stealth)
        self.assertTrue(browser_cfg.ignore_https_errors)
        self.assertIn("--disable-blink-features=AutomationControlled", browser_cfg.extra_args)

        # Check run_config passed to arun
        arun_call_args = mock_crawler_instance.arun.call_args
        run_cfg = arun_call_args.kwargs.get("config")
        self.assertTrue(run_cfg.magic)
        self.assertTrue(run_cfg.simulate_user)
        self.assertTrue(run_cfg.override_navigator)
        self.assertTrue(run_cfg.scan_full_page)
        self.assertGreaterEqual(run_cfg.delay_before_return_html, 2.0)

    @patch("requests.Session.get")
    def test_04_fetch_http_fallback_resilience(self, mock_get):
        """Verifies that fetch_http_fallback parses HTML text cleanly via requests with realistic headers."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body><h1>DirectLogic 305</h1><p>Discontinued 2024</p></body></html>"
        mock_resp.content = mock_resp.text.encode("utf-8")
        mock_get.return_value = mock_resp

        res = self.crawler.fetch_http_fallback("https://electronics.jtekt.co.jp/en/support/")
        self.assertEqual(res["status_code"], 200)
        self.assertIn("DirectLogic 305", res["markdown"])
        self.assertIn("Discontinued 2024", res["markdown"])

    async def test_05_crawl_website_accumulate_batches_flow(self):
        """Verifies that crawl_website with accumulate_batches=True gathers all pages and calls batch extraction."""
        crawl_mock_data = {
            "url": "https://electronics.jtekt.co.jp",
            "markdown": "## JTEKT Discontinued Products Catalog Index\nComprehensive table of discontinued TOYOPUC controllers, sensors, and encoders for industrial automation.",
            "html": "<html><body><a href='/en/product/discon/'>Discontinued Models</a></body></html>",
            "status_code": 200
        }
        self.crawler.crawl_with_crawl4ai = AsyncMock(return_value=crawl_mock_data)

        # Return a synthetic record when extract_accumulated_batches is called
        synthetic_record = ProductRecord(
            vendor_name="JTEKT Toyoda",
            model_name="TRD-J",
            status="Discontinued",
            stage_date_utc="2025-06-30T00:00:00Z"
        )
        self.mock_extractor.extract_from_markdown.return_value = [synthetic_record]

        records = await self.crawler.crawl_website(
            base_url="https://electronics.jtekt.co.jp",
            allowed_domains=["electronics.jtekt.co.jp"],
            max_pages=2,
            enable_sitemap=False,
            accumulate_batches=True
        )
        self.assertGreaterEqual(len(records), 1)
        self.assertEqual(records[0].model_name, "TRD-J")

    @patch("requests.Session.get")
    def test_06_vendor_source_discoverer_probe_url(self, mock_get):
        """Verifies that VendorSourceDiscoverer probe_url identifies table and lifecycle markers."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = "https://electronics.jtekt.co.jp/en/product/discon/"
        mock_resp.text = """
        <html>
        <head><title>Discontinued Models</title></head>
        <body>
          <h1>Discontinued PLC and Encoders</h1>
          <table><tr><td>Model TRD-NA</td><td>Production Ended</td></tr></table>
        </body>
        </html>
        """
        mock_get.return_value = mock_resp

        discoverer = VendorSourceDiscoverer()
        probe_result = discoverer.probe_url("https://electronics.jtekt.co.jp/en/product/discon/")
        self.assertTrue(probe_result["is_valid"])
        self.assertEqual(probe_result["status_code"], 200)
        self.assertTrue(probe_result["has_tables"])
        self.assertTrue(probe_result["has_lifecycle_keywords"])


if __name__ == "__main__":
    unittest.main()
