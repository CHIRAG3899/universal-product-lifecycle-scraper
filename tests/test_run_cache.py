"""
Comprehensive Unit Tests for the RunCache System.
Verifies that web pages and technical files are never scraped, downloaded, or processed twice.
"""

import threading
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from scraper.ai_extractor import UniversalAIExtractor
from scraper.models import ProductRecord
from scraper.run_cache import (
    RunCache,
    get_global_run_cache,
    normalize_cache_url,
    reset_global_run_cache,
)


class TestRunCache(unittest.TestCase):
    def setUp(self):
        reset_global_run_cache()
        self.cache = RunCache(max_page_entries=10, max_file_entries=5)

    def tearDown(self):
        self.cache.clear()
        reset_global_run_cache()

    # -------------------------------------------------------------------------
    # 1. Canonical URL Normalization
    # -------------------------------------------------------------------------
    def test_normalize_cache_url_fragment_stripping(self):
        u1 = "https://example.com/products/controller#specs"
        u2 = "https://example.com/products/controller#downloads"
        u3 = "https://example.com/products/controller"
        self.assertEqual(normalize_cache_url(u1), normalize_cache_url(u2))
        self.assertEqual(normalize_cache_url(u1), normalize_cache_url(u3))

    def test_normalize_cache_url_query_param_sorting(self):
        u1 = "https://example.com/search?vendor=cisco&category=switch&page=2"
        u2 = "https://example.com/search?page=2&category=switch&vendor=cisco"
        self.assertEqual(normalize_cache_url(u1), normalize_cache_url(u2))

    def test_normalize_cache_url_lowercasing_and_default_ports(self):
        u1 = "HTTPS://WWW.EXAMPLE.COM:443/products/switches"
        u2 = "https://www.example.com/products/switches"
        self.assertEqual(normalize_cache_url(u1), u2)

        http_url = "HTTP://EXAMPLE.COM:80/docs"
        self.assertEqual(normalize_cache_url(http_url), "http://example.com/docs")

    def test_normalize_cache_url_trailing_slash(self):
        u1 = "https://example.com/catalog/industrial/"
        u2 = "https://example.com/catalog/industrial"
        self.assertEqual(normalize_cache_url(u1), normalize_cache_url(u2))

    def test_normalize_cache_url_empty_or_invalid(self):
        self.assertEqual(normalize_cache_url(""), "")
        self.assertEqual(normalize_cache_url(None), "")

    # -------------------------------------------------------------------------
    # 2. Page Crawl Caching
    # -------------------------------------------------------------------------
    def test_page_crawl_cache_lifecycle(self):
        url = "https://example.com/lifecycle/switches"
        self.assertFalse(self.cache.has_crawled_page(url))
        self.assertIsNone(self.cache.get_crawled_page(url))

        payload = {
            "url": url,
            "markdown": "# Lifecycle Table\nModel A: Discontinued",
            "html": "<html><body>Table</body></html>",
            "status_code": 200,
        }
        self.cache.set_crawled_page(url, payload)

        self.assertTrue(self.cache.has_crawled_page(url))
        retrieved = self.cache.get_crawled_page(url)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["status_code"], 200)
        self.assertEqual(retrieved["markdown"], payload["markdown"])

        # Deep copy isolation test: modifying retrieved object must not mutate internal cache
        retrieved["status_code"] = 500
        fresh = self.cache.get_crawled_page(url)
        self.assertEqual(fresh["status_code"], 200)

    # -------------------------------------------------------------------------
    # 3. Product Extraction Caching (0-Token Redundancy Bypass)
    # -------------------------------------------------------------------------
    def test_page_records_cache_lifecycle_and_deep_copy_isolation(self):
        url = "https://example.com/eol/models"
        self.assertFalse(self.cache.has_extracted_products(url))
        self.assertIsNone(self.cache.get_extracted_products(url))

        rec = ProductRecord(
            vendor_name="Cisco",
            model_name="Catalyst 2960",
            stage="End of Life",
            stage_date_utc="2026-10-31T00:00:00Z",
            metadata={"series": "Catalyst"},
        )
        self.cache.set_extracted_products(url, [rec])

        self.assertTrue(self.cache.has_extracted_products(url))
        results = self.cache.get_extracted_products(url)
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].model_name, "Catalyst 2960")

        # Mutate the retrieved copy
        results[0].vendor_name = "Mutated Vendor"
        results[0].metadata["series"] = "Mutated"

        # Check that cache remains unaltered
        fresh_results = self.cache.get_extracted_products(url)
        self.assertEqual(fresh_results[0].vendor_name, "Cisco")
        self.assertEqual(fresh_results[0].metadata["series"], "Catalyst")

    # -------------------------------------------------------------------------
    # 4. File Caching (Bytes, Text, PDF Replacements)
    # -------------------------------------------------------------------------
    def test_file_cache_lifecycle(self):
        file_url = "https://example.com/bulletins/notice_2026.pdf"
        self.assertFalse(self.cache.has_file(file_url))
        self.assertIsNone(self.cache.get_file_bytes(file_url))

        fake_pdf = b"%PDF-1.4 Fake PDF Content for Bulletin"
        self.cache.set_file_bytes(file_url, fake_pdf)

        self.assertTrue(self.cache.has_file(file_url))
        self.assertEqual(self.cache.get_file_bytes(file_url), fake_pdf)

        # File text
        self.assertIsNone(self.cache.get_file_text(file_url))
        self.cache.set_file_text(file_url, "Extracted text from PDF")
        self.assertEqual(self.cache.get_file_text(file_url), "Extracted text from PDF")

        # PDF replacement maps
        self.assertFalse(self.cache.has_pdf_replacements(file_url))
        self.assertIsNone(self.cache.get_pdf_replacements(file_url))
        replacements = {"FX2N-16MR": "FX3U-16MR", "Q02HCPU": "Q03UDECPU"}
        self.cache.set_pdf_replacements(file_url, replacements)
        self.assertTrue(self.cache.has_pdf_replacements(file_url))
        self.assertEqual(self.cache.get_pdf_replacements(file_url), replacements)

    # -------------------------------------------------------------------------
    # 5. Visited URL Tracking
    # -------------------------------------------------------------------------
    def test_visited_urls_tracking(self):
        url = "https://example.com/devices/plc"
        self.assertFalse(self.cache.is_visited(url))
        self.cache.mark_visited(url)
        self.assertTrue(self.cache.is_visited(url))
        # Equivalent URL with anchor fragment should also evaluate to visited
        self.assertTrue(self.cache.is_visited("https://example.com/devices/plc#hardware"))

    # -------------------------------------------------------------------------
    # 6. Capacity Bounding & FIFO Eviction
    # -------------------------------------------------------------------------
    def test_fifo_eviction_limits(self):
        small_cache = RunCache(max_page_entries=3, max_file_entries=2)

        # Insert 3 page crawls
        small_cache.set_crawled_page("https://example.com/1", {"html": "1"})
        small_cache.set_crawled_page("https://example.com/2", {"html": "2"})
        small_cache.set_crawled_page("https://example.com/3", {"html": "3"})

        self.assertTrue(small_cache.has_crawled_page("https://example.com/1"))

        # Insert 4th -> 1st should be evicted
        small_cache.set_crawled_page("https://example.com/4", {"html": "4"})
        self.assertFalse(small_cache.has_crawled_page("https://example.com/1"))
        self.assertTrue(small_cache.has_crawled_page("https://example.com/4"))

        # File cache eviction
        small_cache.set_file_bytes("https://example.com/f1.pdf", b"1")
        small_cache.set_file_bytes("https://example.com/f2.pdf", b"2")
        self.assertTrue(small_cache.has_file("https://example.com/f1.pdf"))
        small_cache.set_file_bytes("https://example.com/f3.pdf", b"3")
        self.assertFalse(small_cache.has_file("https://example.com/f1.pdf"))
        self.assertTrue(small_cache.has_file("https://example.com/f3.pdf"))

    # -------------------------------------------------------------------------
    # 7. Telemetry & Metrics
    # -------------------------------------------------------------------------
    def test_cache_telemetry_stats(self):
        url = "https://example.com/test_page"
        self.cache.get_crawled_page(url)  # 1 page miss
        self.cache.set_crawled_page(url, {"html": "text"})
        self.cache.get_crawled_page(url)  # 1 page hit

        file_url = "https://example.com/test.pdf"
        self.cache.get_file_bytes(file_url)  # 1 file miss
        self.cache.set_file_bytes(file_url, b"bytes")
        self.cache.get_file_bytes(file_url)  # 1 file hit

        stats = self.cache.get_stats()
        self.assertEqual(stats["page_crawl_hits"], 1)
        self.assertEqual(stats["page_crawl_misses"], 1)
        self.assertEqual(stats["file_hits"], 1)
        self.assertEqual(stats["file_misses"], 1)
        self.assertGreaterEqual(stats["total_redundant_operations_saved"], 2)

    # -------------------------------------------------------------------------
    # 8. Thread-Safety Under Concurrency
    # -------------------------------------------------------------------------
    def test_thread_safety(self):
        cache = RunCache(max_page_entries=500, max_file_entries=500)
        errors = []

        def worker(thread_idx: int):
            try:
                for i in range(50):
                    url = f"https://example.com/page_{thread_idx}_{i}"
                    cache.set_crawled_page(url, {"idx": i})
                    _ = cache.get_crawled_page(url)
                    cache.mark_visited(url)
                    _ = cache.is_visited(url)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Thread errors: {errors}")
        self.assertGreaterEqual(len(cache._visited_urls), 200)

    # -------------------------------------------------------------------------
    # 9. Global Singleton Reset
    # -------------------------------------------------------------------------
    def test_global_singleton_access(self):
        g1 = get_global_run_cache()
        g2 = get_global_run_cache()
        self.assertIs(g1, g2)
        reset_global_run_cache()
        g3 = get_global_run_cache()
        self.assertIsNot(g1, g3)


class TestRunCacheIntegration(unittest.TestCase):
    def setUp(self):
        reset_global_run_cache()

    def tearDown(self):
        reset_global_run_cache()

    def test_crawler_avoids_scraping_same_page_twice(self):
        """Verifies UniversalAICrawler.run only crawls and extracts once for the same URL."""
        import asyncio

        from scraper.crawl_engine import UniversalAICrawler

        async def _test():
            mock_extractor = MagicMock(spec=UniversalAIExtractor)
            mock_extractor.is_configured.return_value = False
            mock_extractor.model_name = "gemini-2.5-flash"
            mock_extractor.batch_mode = False

            crawler = UniversalAICrawler(gemini_extractor=mock_extractor)
            target_url = "https://example.com/lifecycle/catalog"

            sample_product = ProductRecord(
                vendor_name="Rockwell Automation",
                model_name="1756-L71",
                stage="End of Life",
                stage_date_utc="2026-12-31T00:00:00Z",
            )

            # Mock crawl_with_crawl4ai to return payload
            crawler.crawl_with_crawl4ai = AsyncMock(return_value={
                "url": target_url,
                "markdown": ("1756-L71 ControlLogix End of Life\n" * 10),
                "html": "<html><body>1756-L71</body></html>",
                "status_code": 200,
            })
            crawler.gemini.extract_from_markdown = MagicMock(return_value=[sample_product])
            crawler.extractor.extract_from_markdown = crawler.gemini.extract_from_markdown

            # 1st call: fresh run
            results_1 = await crawler.run(target_url)
            self.assertEqual(len(results_1), 1)
            self.assertEqual(results_1[0].model_name, "1756-L71")
            self.assertEqual(crawler.crawl_with_crawl4ai.call_count, 1)

            # 2nd call: identical URL
            results_2 = await crawler.run(target_url)
            self.assertEqual(len(results_2), 1)
            self.assertEqual(results_2[0].model_name, "1756-L71")

            # crawl_with_crawl4ai must NOT have been called a second time!
            self.assertEqual(crawler.crawl_with_crawl4ai.call_count, 1)

            # 3rd call with anchor fragment (should also hit cache!)
            results_3 = await crawler.run(f"{target_url}#section2")
            self.assertEqual(len(results_3), 1)
            self.assertEqual(crawler.crawl_with_crawl4ai.call_count, 1)

        asyncio.run(_test())

    def test_extractor_avoids_downloading_same_pdf_twice(self):
        """Verifies UniversalAIExtractor.extract_from_pdf_url only downloads PDF once."""
        extractor = UniversalAIExtractor()
        pdf_url = "https://example.com/bulletins/eol_2026.pdf"

        sample_rec = ProductRecord(
            vendor_name="Omron",
            model_name="CJ1W-PA202",
            stage="Discontinued",
            stage_date_utc="2026-03-31T00:00:00Z",
        )

        with patch("requests.get") as mock_get, \
             patch("scraper.ai_extractor.extract_text_from_pdf_bytes", return_value="CJ1W-PA202 Discontinued"):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.content = b"%PDF-1.4 Sample PDF content"
            mock_get.return_value = mock_resp

            extractor.extract_from_markdown = MagicMock(return_value=[sample_rec])

            # 1st extraction
            res_1 = extractor.extract_from_pdf_url(pdf_url)
            self.assertEqual(len(res_1), 1)
            self.assertEqual(mock_get.call_count, 1)

            # 2nd extraction on same URL
            res_2 = extractor.extract_from_pdf_url(pdf_url)
            self.assertEqual(len(res_2), 1)
            # requests.get must NOT have been called again!
            self.assertEqual(mock_get.call_count, 1)


if __name__ == "__main__":
    unittest.main()
