"""
Unit Tests for scraper/__init__.py package exports.
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import scraper


class TestPackageInit(unittest.TestCase):

    def test_package_exports(self):
        """Verifies all symbols in __all__ are properly exported by the scraper package."""
        expected_exports = [
            "ProductRecord",
            "ScrapedDataset",
            "parse_to_utc_iso",
            "AIExtractor",
            "UniversalAIExtractor",
            "LLMExtractor",
            "GeminiExtractor",
            "UniversalAICrawler",
            "MitsubishiAICrawler",
            "LifecyclePipeline",
            "detect_vendor_from_url_or_text",
            "normalize_stage_name",
            "VENDOR_PROFILES"
        ]
        for exp in expected_exports:
            self.assertTrue(hasattr(scraper, exp), f"Package missing export: {exp}")
            self.assertIn(exp, scraper.__all__)


if __name__ == "__main__":
    unittest.main()
