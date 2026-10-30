"""
Unit Tests for scraper/crawler_comparison.py
Validates completeness, structure, and text summary formatting of the 10-dimension comparison matrix.
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.crawler_comparison import CRAWLER_COMPARISON_MATRIX, get_comparison_summary


class TestCrawlerComparison(unittest.TestCase):

    def test_matrix_dimensions_count_and_keys(self):
        self.assertEqual(len(CRAWLER_COMPARISON_MATRIX), 10, "Comparison matrix must evaluate exactly 10 dimensions")
        required_keys = {"dimension", "generic_crawler", "ai_crawler", "ai_advantage"}
        for item in CRAWLER_COMPARISON_MATRIX:
            self.assertTrue(required_keys.issubset(item.keys()), f"Missing keys in dimension: {item.get('dimension')}")
            # Ensure text is non-empty
            for k in required_keys:
                self.assertTrue(bool(item[k].strip()))

    def test_specific_dimensions_present(self):
        dimensions = [item["dimension"] for item in CRAWLER_COMPARISON_MATRIX]
        expected_subset = [
            "Dynamic SPA & Apollo GraphQL Hydration",
            "Multi-Vendor Polymorphism (100+ Vendors)",
            "Site Redesign Resilience",
            "Multi-Lingual Translation (Global Portals)",
            "Bundled Model Disambiguation",
            "Multi-Milestone Stage Explosion",
            "Noise, Modals & Cookie Banner Filtering",
            "Maintenance Overhead (Cost of Ownership)"
        ]
        for exp in expected_subset:
            self.assertIn(exp, dimensions)

    def test_get_comparison_summary_output(self):
        summary = get_comparison_summary()
        self.assertIsInstance(summary, str)
        self.assertIn("Generic / Traditional IDE Crawler", summary)
        self.assertIn("Universal AI Crawler (Crawl4AI + Multi-Provider AI)", summary)
        self.assertIn("AI Advantage", summary)


if __name__ == "__main__":
    unittest.main()
