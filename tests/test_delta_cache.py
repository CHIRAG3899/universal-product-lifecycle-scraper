"""
Unit tests for Incremental Delta Cache.
"""

import tempfile
import unittest
from pathlib import Path

from scraper.delta_cache import DeltaCache


class TestDeltaCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_file = Path(self.temp_dir.name) / "test_delta_cache.json"
        self.cache = DeltaCache(cache_path=self.cache_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_content_hashing_and_unchanged_detection(self):
        url = "https://example.com/lifecycle"
        content_v1 = "<html><body><h1>Product A EOL 2026</h1></body></html>"
        content_v2 = "<html><body><h1>Product A EOL 2027</h1></body></html>"

        # Initially unchanged check returns False (cache miss)
        self.assertFalse(self.cache.is_unchanged(url, content_v1))

        # Register v1
        self.cache.update_entry(url, content_v1, vendor_id="test_vendor", record_count=1)

        # Checking identical content returns True (cache hit)
        self.assertTrue(self.cache.is_unchanged(url, content_v1))

        # Modified content returns False (cache miss / needs re-extraction)
        self.assertFalse(self.cache.is_unchanged(url, content_v2))

    def test_etag_support(self):
        url = "https://example.com/api/lifecycle.json"
        content = '{"products": []}'
        etag = '"33a64df551425fcc3e5b3"'

        self.cache.update_entry(url, content, etag=etag)
        self.assertTrue(self.cache.is_unchanged(url, content, etag=etag))

    def test_clear_cache(self):
        self.cache.update_entry("https://example.com", "sample data")
        self.assertIsNotNone(self.cache.get_entry("https://example.com"))
        cleared = self.cache.clear()
        self.assertTrue(cleared)
        self.assertIsNone(self.cache.get_entry("https://example.com"))


if __name__ == "__main__":
    unittest.main()
