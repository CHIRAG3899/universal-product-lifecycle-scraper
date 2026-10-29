"""
Unit & Edge Case Tests for scraper/crawl_engine.py.
Validates:
1. UniversalAICrawler initialization and backwards-compatibility alias.
2. Next.js __NEXT_DATA__ Apollo GraphQL cache table extraction (valid, malformed, empty).
3. Markdown block rendering from Apollo table structures.
4. Crawl4AI browser run config, non-200 status code, and error handling.
5. Record extraction, de-duplication by (vendor, model, stage), and preference for UTC dates.
6. Site-level crawling, SSRF boundary checking against allowed_domains, and lifecycle link discovery.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.crawl_engine import MitsubishiAICrawler, UniversalAICrawler
from scraper.gemini_extractor import GeminiExtractor
from scraper.models import ProductRecord


class TestCrawlEngine(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_gemini = MagicMock(spec=GeminiExtractor)
        self.mock_gemini.is_configured.return_value = False
        self.mock_gemini.model_name = "gemini-2.5-flash"
        self.mock_gemini.api_key = ""
        self.crawler = UniversalAICrawler(gemini_extractor=self.mock_gemini)

    def test_01_alias_and_initialization(self):
        """Verifies UniversalAICrawler init and MitsubishiAICrawler alias."""
        self.assertIs(MitsubishiAICrawler, UniversalAICrawler)
        crawler_default = UniversalAICrawler()
        self.assertIsNotNone(crawler_default.gemini)

    def test_02_extract_apollo_state_tables_valid(self):
        """Verifies parsing of Next.js __NEXT_DATA__ Apollo state with TableBlocks."""
        sample_html = """
        <html>
        <head>
          <script id="__NEXT_DATA__" type="application/json">
          {
            "props": {
              "pageProps": {
                "__APOLLO_STATE__": {
                  "Block1": {
                    "__typename": "TableBlock",
                    "rows": [
                      [{"text": "FX5-EIP", "url": ""}, {"text": "Ethernet Module", "url": ""}],
                      [{"text": "End of Life", "url": ""}, {"text": "2026-03-31", "url": "https://example.com/eol.pdf"}]
                    ]
                  }
                }
              }
            }
          }
          </script>
        </head>
        <body></body>
        </html>
        """
        tables = self.crawler.extract_apollo_state_tables(sample_html)
        self.assertEqual(len(tables), 1)
        self.assertEqual(len(tables[0]["rows"]), 2)
        self.assertEqual(tables[0]["rows"][0][0]["text"], "FX5-EIP")
        self.assertEqual(tables[0]["rows"][1][1]["url"], "https://example.com/eol.pdf")

    def test_03_extract_apollo_state_tables_edge_cases(self):
        """Verifies handling of empty, missing, or malformed Apollo state."""
        # Empty string
        self.assertEqual(self.crawler.extract_apollo_state_tables(""), [])

        # Missing script tag
        self.assertEqual(self.crawler.extract_apollo_state_tables("<div>Hello World</div>"), [])

        # Corrupted JSON inside script tag
        corrupted = '<script id="__NEXT_DATA__" type="application/json">{invalid_json</script>'
        self.assertEqual(self.crawler.extract_apollo_state_tables(corrupted), [])

        # Missing pageProps or __APOLLO_STATE__
        missing_state = '<script id="__NEXT_DATA__" type="application/json">{"props": {}}</script>'
        self.assertEqual(self.crawler.extract_apollo_state_tables(missing_state), [])

    def test_04_apollo_tables_to_markdown_blocks(self):
        """Verifies converting Apollo table structures into structured Markdown."""
        tables = [
            {
                "rows": [
                    [{"text": "GT25-WLAN", "url": ""}, {"text": "Scope: GT25 Series", "url": ""}],
                    [{"text": "End of Life", "url": ""}, {"text": "2023-08-17", "url": "https://example.com/doc.pdf"}],
                    [{"text": "Last Time Buy", "url": ""}, {"text": "2025-01-28", "url": ""}]
                ]
            }
        ]
        blocks = self.crawler.apollo_tables_to_markdown_blocks(tables)
        self.assertEqual(len(blocks), 1)
        md = blocks[0]
        self.assertIn("## GT25-WLAN", md)
        self.assertIn("Scope: Scope: GT25 Series", md)
        self.assertIn("- **End of Life**: [2023-08-17](https://example.com/doc.pdf)", md)
        self.assertIn("- **Last Time Buy**: 2025-01-28", md)

        # Empty table case
        self.assertEqual(self.crawler.apollo_tables_to_markdown_blocks([{"rows": []}]), [])

    @patch("scraper.crawl_engine.AsyncWebCrawler")
    async def test_05_crawl_with_crawl4ai_success_and_error_codes(self, mock_crawler_cls):
        """Verifies Crawl4AI run success and HTTP >= 400 error status codes."""
        # Setup mock crawler context manager
        mock_crawler_instance = AsyncMock()
        mock_crawler_cls.return_value.__aenter__.return_value = mock_crawler_instance

        # Test HTTP 200 success
        mock_result_ok = MagicMock()
        mock_result_ok.success = True
        mock_result_ok.status_code = 200
        mock_result_ok.markdown = "# Discontinued Catalog\n- Model: GT25"
        mock_result_ok.html = "<html>...</html>"
        mock_result_ok.extracted_content = None
        mock_crawler_instance.arun.return_value = mock_result_ok

        res_ok = await self.crawler.crawl_with_crawl4ai("https://example.com/lifecycle")
        self.assertEqual(res_ok["status_code"], 200)
        self.assertIn("GT25", res_ok["markdown"])

        # Test HTTP 404 error code
        mock_result_404 = MagicMock()
        mock_result_404.success = True
        mock_result_404.status_code = 404
        mock_result_404.markdown = "Not Found"
        mock_result_404.html = "<html>404</html>"
        mock_crawler_instance.arun.return_value = mock_result_404

        res_404 = await self.crawler.crawl_with_crawl4ai("https://example.com/missing")
        self.assertEqual(res_404["status_code"], 404)
        self.assertEqual(res_404["markdown"], "")

        # Test Crawl4AI engine failure (success=False)
        mock_result_fail = MagicMock()
        mock_result_fail.success = False
        mock_result_fail.error_message = "Browser crashed"
        mock_crawler_instance.arun.return_value = mock_result_fail

        with self.assertRaises(RuntimeError):
            await self.crawler.crawl_with_crawl4ai("https://example.com/fail")

    async def test_06_run_deduplication_and_date_preference(self):
        """Verifies run() de-duplicates by (vendor, model, stage) and prefers records with dates."""
        # Mock crawl_with_crawl4ai
        crawl_mock_data = {
            "url": "https://se-fa.mitsubishielectric.com/fa/se_en/support/eol",
            "markdown": "## Test Catalog Discontinued Product Lines\nDetailed descriptions and part numbers for legacy controllers...",
            "html": "<html></html>",
            "status_code": 200,
            "extracted_content": None
        }
        self.crawler.crawl_with_crawl4ai = AsyncMock(return_value=crawl_mock_data)

        # Mock Gemini extracting two duplicate records with mandatory dates
        rec_1 = ProductRecord(
            vendor_name="Mitsubishi Electric",
            model_name="GT25-WLAN",
            status="End of Life",
            stage_date_utc="2023-08-17T00:00:00Z"
        )
        rec_2 = ProductRecord(
            vendor_name="Mitsubishi Electric",
            model_name="GT25-WLAN",
            status="End of Life",
            stage_date_utc="2023-08-17T00:00:00Z"
        )
        self.mock_gemini.extract_from_markdown.return_value = [rec_1, rec_2]

        products = await self.crawler.run("https://se-fa.mitsubishielectric.com/fa/se_en/support/eol")
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].model_name, "GT25-WLAN")
        self.assertEqual(products[0].stage_date_utc, "2023-08-17T00:00:00Z")

    async def test_07_crawl_website_ssrf_and_link_discovery(self):
        """Verifies site-level crawling extracts lifecycle links and respects allowed_domains."""
        html_content = """
        <html>
        <body>
          <a href="/support/eol-products">EOL Support Page</a>
          <a href="https://other-domain.com/lifecycle">External Untrusted Link</a>
          <a href="/products/active-catalog">Active Catalog (Not lifecycle)</a>
          <a href="https://mitsubishielectric.com/support/product-status">Product Status Page</a>
        </body>
        </html>
        """
        crawl_mock_data = {
            "url": "https://mitsubishielectric.com",
            "markdown": "Base home page",
            "html": html_content,
            "status_code": 200
        }
        self.crawler.crawl_with_crawl4ai = AsyncMock(return_value=crawl_mock_data)

        # Mock self.run for discovered pages
        dummy_record = ProductRecord(
            vendor_name="Mitsubishi Electric",
            model_name="MI3321G-W",
            status="End of Life",
            stage_date_utc="2025-10-29T00:00:00Z"
        )
        self.crawler.run = AsyncMock(return_value=[dummy_record])

        records = await self.crawler.crawl_website(
            base_url="https://mitsubishielectric.com",
            allowed_domains=["mitsubishielectric.com"],
            max_pages=2,
            enable_sitemap=False
        )

        self.assertTrue(len(records) > 0)
        # Ensure crawl_with_crawl4ai was called for base domain
        self.crawler.crawl_with_crawl4ai.assert_any_call("https://mitsubishielectric.com")
        # Ensure run was invoked only on allowed domain links
        for call in self.crawler.run.call_args_list:
            arg_url = call[0][0]
            self.assertTrue("mitsubishielectric.com" in arg_url)
            self.assertFalse("other-domain.com" in arg_url)

    def test_08_discover_pagination_urls(self):
        """Verifies discover_pagination_urls discovers ?page=, rel='next', and pagination links."""
        from bs4 import BeautifulSoup
        html = """
        <html>
        <body>
          <a href="/support/eol?page=2" class="pagination-link">Page 2</a>
          <a href="/support/eol?page=3" rel="next">Next ›</a>
          <a href="https://other.com/page=2">External Page</a>
          <a href="/support/eol#top">Back to Top</a>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        discovered = self.crawler.discover_pagination_urls(
            soup=soup,
            current_url="https://mitsubishielectric.com/support/eol",
            allowed_domains=["mitsubishielectric.com"]
        )
        self.assertEqual(len(discovered), 2)
        self.assertIn("https://mitsubishielectric.com/support/eol?page=2", discovered)
        self.assertIn("https://mitsubishielectric.com/support/eol?page=3", discovered)

    def test_09_extract_dom_tables_single_table_per_html_element(self):
        """Verifies that an N-row HTML table produces exactly ONE table object with all N rows (no premature appending)."""
        html = """
        <html>
        <body>
          <table id="lifecycle-table">
            <thead>
              <tr><th>Model</th><th>Status</th><th>Date</th></tr>
            </thead>
            <tbody>
              <tr><td>6ES7315-2EH14-0AB0</td><td>Phase-Out</td><td>2025-10-01</td></tr>
              <tr><td>6ES7317-2EK14-0AB0</td><td>End of Life</td><td>2026-10-01</td></tr>
              <tr><td>6ES7318-3EL01-0AB0</td><td>Discontinued</td><td>2027-10-01</td></tr>
            </tbody>
          </table>
        </body>
        </html>
        """
        tables = self.crawler.extract_dom_tables(html)
        self.assertEqual(len(tables), 1, "Must produce exactly 1 table dictionary for 1 HTML <table> element")
        rows = tables[0].get("rows", [])
        self.assertEqual(len(rows), 4, "Must contain header row + 3 data rows")
        self.assertEqual(rows[1][0]["text"], "6ES7315-2EH14-0AB0")
        self.assertEqual(rows[3][0]["text"], "6ES7318-3EL01-0AB0")

    def test_10_discover_sitemap_urls_xml_parsing(self):
        """Verifies discover_sitemap_urls parses robots.txt and sitemap.xml to discover product/lifecycle URLs."""
        robots_txt = "User-agent: *\nSitemap: https://mitsubishielectric.com/sitemap.xml\n"
        sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url>
            <loc>https://mitsubishielectric.com/fa/support/product-lifecycle</loc>
          </url>
          <url>
            <loc>https://mitsubishielectric.com/fa/products/controllers/plc</loc>
          </url>
          <url>
            <loc>https://mitsubishielectric.com/fa/products/drives/inverters</loc>
          </url>
          <url>
            <loc>https://external-domain.com/untrusted</loc>
          </url>
        </urlset>
        """
        from unittest.mock import MagicMock

        def mock_urlopen(req, timeout=5):
            url_str = req.full_url if hasattr(req, "full_url") else str(req)
            resp = MagicMock()
            resp.__enter__.return_value = resp
            if "robots.txt" in url_str:
                resp.status = 200
                resp.read.return_value = robots_txt.encode("utf-8")
                resp.headers = {}
                return resp
            elif "sitemap.xml" in url_str:
                resp.status = 200
                resp.read.return_value = sitemap_xml.encode("utf-8")
                resp.headers = {}
                return resp
            resp.status = 404
            resp.read.return_value = b""
            resp.headers = {}
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            urls = self.crawler.discover_sitemap_urls(
                base_url="https://mitsubishielectric.com",
                allowed_domains=["mitsubishielectric.com"],
                max_urls=10
            )

        self.assertTrue(len(urls) >= 3)
        self.assertIn("https://mitsubishielectric.com/fa/support/product-lifecycle", urls)
        self.assertIn("https://mitsubishielectric.com/fa/products/controllers/plc", urls)
        self.assertIn("https://mitsubishielectric.com/fa/products/drives/inverters", urls)
        # SSRF boundary: untrusted domain must be excluded
        self.assertNotIn("https://external-domain.com/untrusted", urls)

    async def test_11_crawl_website_unrestricted_product_categories(self):
        """Verifies site crawl discovers product catalog hubs across all categories without category restriction."""
        html_content = """
        <html>
        <body>
          <a href="/products/controllers/plc">Controllers & PLCs</a>
          <a href="/products/drives/servos">Drives & Servos</a>
          <a href="/products/networking/switches">Industrial Ethernet Switches</a>
          <a href="/products/sensors/vision">Vision Sensors & Optics</a>
          <a href="/support/discontinued">Discontinued Notice Hub</a>
        </body>
        </html>
        """
        crawl_mock_data = {
            "url": "https://mitsubishielectric.com",
            "markdown": "Base Catalog",
            "html": html_content,
            "status_code": 200
        }
        self.crawler.crawl_with_crawl4ai = AsyncMock(return_value=crawl_mock_data)

        dummy_record = ProductRecord(
            vendor_name="Mitsubishi Electric",
            model_name="MELSEC-iQ-R",
            status="Active Mature",
            stage_date_utc="2026-01-01T00:00:00Z"
        )
        self.crawler.run = AsyncMock(return_value=[dummy_record])

        # Execute crawl_website with sitemap disabled in test to isolate link extraction
        records = await self.crawler.crawl_website(
            base_url="https://mitsubishielectric.com",
            allowed_domains=["mitsubishielectric.com"],
            max_pages=5,
            enable_sitemap=False
        )

        self.assertTrue(len(records) > 0)
        crawled_urls = [call[0][0] for call in self.crawler.run.call_args_list]
        # Verify both lifecycle hub and product category URLs were queued and crawled
        has_category_link = any("/products/" in u for u in crawled_urls)
        self.assertTrue(has_category_link, "Crawler must discover and crawl general product category trees")


if __name__ == "__main__":
    unittest.main()
