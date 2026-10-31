"""
Unit and Integration Tests for Scraper Comparison and Benchmarking Engine.
"""

import csv
import tempfile
import unittest
from pathlib import Path

from scraper.crawler_comparison import (
    CRAWLER_COMPARISON_MATRIX,
    benchmark_url_head_to_head,
    compare_csv_datasets,
    format_dataset_comparison_markdown,
    get_comparison_summary,
)


class TestScraperComparison(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_matrix_and_summary(self):
        """Verifies comparison matrix has 10 core dimensions and formatted markdown is valid."""
        self.assertGreaterEqual(len(CRAWLER_COMPARISON_MATRIX), 10)
        summary = get_comparison_summary()
        self.assertIn("Dynamic SPA & Apollo GraphQL Hydration", summary)
        self.assertIn("Multi-Vendor Polymorphism", summary)
        self.assertIn("| Capability Dimension |", summary)

    def test_02_compare_csv_datasets_overlap_and_metrics(self):
        """Tests empirical CSV comparison with partial model overlap, dates, and replacements."""
        # Baseline legacy CSV (uses legacy column names)
        baseline_file = self.dir_path / "baseline_legacy.csv"
        with open(baseline_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Manufacturer", "Part_Number", "Lifecycle_Status", "EOL_Date", "Successor"])
            writer.writerow(["Siemens", "6ES7516-3AN02-0AB0", "End of Life", "2024-10-01T00:00:00Z", "6ES7516-3AN03-0AB0"])
            writer.writerow(["Siemens", "6ES7511-1AK02-0AB0", "Phase-out", "2024-05-15", "Consult sales"])
            writer.writerow(["Siemens", "6ES7512-1DK01-0AB0", "Discontinued", "", ""])

        # Candidate AI crawler CSV (uses exact 10-column schema)
        candidate_file = self.dir_path / "candidate_ai.csv"
        with open(candidate_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "vendor_name", "model_name", "aliases", "status", "stage_date_utc", "source_url",
                "os", "firmware", "category", "replacement", "metadata"
            ])
            # Overlapping model with date & replacement
            writer.writerow([
                "Siemens", "6ES7516-3AN02-0AB0", "CPU 1516-3", "End of Life", "2024-10-01T00:00:00Z",
                "https://siemens.com", "", "", "PLC", "6ES7516-3AN03-0AB0", "{}"
            ])
            # Overlapping model where candidate found actual replacement & standardized date
            writer.writerow([
                "Siemens", "6ES7511-1AK02-0AB0", "CPU 1511-1", "Phase-Out", "2024-05-15T00:00:00Z",
                "https://siemens.com", "", "", "PLC", "6ES7511-1AK03-0AB0", "{}"
            ])
            # Candidate-exclusive model discovered
            writer.writerow([
                "Siemens", "6ES7513-1AL02-0AB0", "", "End of Life", "2024-12-31T00:00:00Z",
                "https://siemens.com", "", "", "PLC", "6ES7513-1AL03-0AB0", "{}"
            ])

        summary = compare_csv_datasets(str(baseline_file), str(candidate_file))

        self.assertEqual(summary["baseline_records"], 3)
        self.assertEqual(summary["candidate_records"], 3)
        self.assertEqual(summary["baseline_unique_models"], 3)
        self.assertEqual(summary["candidate_unique_models"], 3)
        self.assertEqual(summary["overlap_models_count"], 2)
        self.assertEqual(summary["candidate_exclusive_count"], 1)
        self.assertEqual(summary["baseline_exclusive_count"], 1)
        self.assertIn("6ES7513-1AL02-0AB0", summary["candidate_exclusive_sample"])
        self.assertIn("6ES7512-1DK01-0AB0", summary["baseline_exclusive_sample"])

        # Candidate should have 100% valid ISO UTC dates and 100% replacement coverage
        self.assertEqual(summary["candidate_valid_date_pct"], 100.0)
        self.assertEqual(summary["candidate_replacement_pct"], 100.0)
        self.assertGreater(summary["candidate_quality_score"], summary["baseline_quality_score"])

        # Check markdown formatting
        md_text = format_dataset_comparison_markdown(summary)
        self.assertIn("# Scraper Empirical Comparison Report", md_text)
        self.assertIn("6ES7513-1AL02-0AB0", md_text)

    def test_03_benchmark_url_head_to_head_synthetic(self):
        """Verifies head-to-head benchmarking metrics with synthetic HTML."""
        synthetic_html = """
        <html>
        <body>
          <table>
            <tr><th>Part Number</th><th>Status</th><th>Discontinuation Date</th></tr>
            <tr><td>CJ2M-CPU33</td><td>Discontinued</td><td>2023-03-31</td></tr>
            <tr><td>CJ1W-NC413</td><td>End of Life</td><td>2022-09-30</td></tr>
          </table>
        </body>
        </html>
        """
        res = benchmark_url_head_to_head(
            target_url="https://ia.omron.co.jp/support/discontinued/",
            vendor="Omron",
            html_content=synthetic_html
        )

        self.assertIn("legacy_scraper", res)
        self.assertIn("crawl4ai_universal_ai", res)
        self.assertEqual(res["legacy_scraper"]["records_extracted"], 2)
        self.assertEqual(res["crawl4ai_universal_ai"]["records_extracted"], 2)
        self.assertEqual(res["crawl4ai_universal_ai"]["zero_token_direct_extracted"], 2)
        self.assertGreater(res["crawl4ai_universal_ai"]["approx_tokens_saved"], 0)


if __name__ == "__main__":
    unittest.main()
