"""
Unit & Edge Case Tests for scraper/observability.py
Validates PipelineMetricsCollector, data quality health scores, urgent LTB alerts, and AlertDispatcher.
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.models import ProductRecord
from scraper.observability import AlertDispatcher, PipelineMetricsCollector


class TestObservability(unittest.TestCase):

    def test_pipeline_metrics_computation(self):
        collector = PipelineMetricsCollector(run_id="run_obs_001", alert_ltb_days=90)
        collector.record_vendor_result("Mitsubishi Electric", 10, 1.25)
        collector.record_vendor_result("Siemens", 5, 0.85)

        # Create sample products: 1 urgent LTB (in 30 days), 1 distant LTB (in 300 days), 1 EOL, 1 EOS
        now = datetime.now(timezone.utc)
        urgent_date = (now + timedelta(days=30)).strftime("%Y-%m-%dT00:00:00Z")
        distant_date = (now + timedelta(days=300)).strftime("%Y-%m-%dT00:00:00Z")

        products = [
            ProductRecord(
                vendor_name="Mitsubishi Electric",
                model_name="GT25-WLAN",
                status="Last Time Buy (LTB)",
                stage_date_utc=urgent_date,
                metadata={"replacement": "GT27", "bulletin_title": "EOL-001"}
            ),
            ProductRecord(
                vendor_name="Mitsubishi Electric",
                model_name="MI3321G-W",
                status="Last Time Buy (LTB)",
                stage_date_utc=distant_date,
                metadata={"replacement": "MI5000"}
            ),
            ProductRecord(
                vendor_name="Siemens",
                model_name="S7-300",
                status="End of Life (EOL)",
                stage_date_utc="2025-10-01T00:00:00Z"
            ),
            ProductRecord(
                vendor_name="Siemens",
                model_name="S7-200",
                status="End of Service (EOS)",
                stage_date_utc="2023-01-01T00:00:00Z"
            )
        ]

        metrics = collector.compute_metrics(products, new_appended=2, refreshed_existing=2)

        self.assertEqual(metrics["run_id"], "run_obs_001")
        self.assertEqual(metrics["pipeline_status"], "ACTION_REQUIRED")  # Has urgent LTB item
        self.assertEqual(metrics["volumes"]["total_records_ingested"], 4)
        self.assertEqual(metrics["volumes"]["new_records_appended"], 2)
        self.assertEqual(metrics["volumes"]["existing_records_refreshed"], 2)
        self.assertEqual(metrics["volumes"]["vendors_processed"], 2)

        # Check stage breakdown
        stages = metrics["stage_breakdown"]
        self.assertEqual(stages["last_time_buy_count"], 2)
        self.assertEqual(stages["end_of_life_count"], 1)
        self.assertEqual(stages["end_of_service_count"], 1)

        # Check urgent procurement alerts
        alerts = metrics["procurement_alerts"]
        self.assertEqual(alerts["urgent_ltb_count"], 1)
        self.assertEqual(alerts["urgent_items"][0]["model"], "GT25-WLAN")
        self.assertTrue(0 <= alerts["urgent_items"][0]["days_remaining"] <= 31)

        # Check data quality score (100% since all 4 have valid UTC dates)
        self.assertEqual(metrics["data_quality"]["utc_date_coverage_pct"], 100.0)

    def test_pipeline_status_degraded_on_errors(self):
        collector = PipelineMetricsCollector(run_id="run_obs_002")
        collector.record_vendor_result("Broken Vendor", 0, 5.0, error="Connection timeout 504")

        products = [
            ProductRecord(
                vendor_name="Working Vendor",
                model_name="MOD-1",
                status="Discontinued",
                stage_date_utc="2026-01-01T00:00:00Z"
            )
        ]
        metrics = collector.compute_metrics(products, new_appended=1, refreshed_existing=0)
        self.assertEqual(metrics["pipeline_status"], "DEGRADED")
        self.assertEqual(len(metrics["errors"]), 1)

    def test_alert_dispatcher_format_text(self):
        collector = PipelineMetricsCollector(run_id="run_obs_003")
        collector.record_vendor_result("Mitsubishi Electric", 1, 0.5)
        products = [
            ProductRecord(
                vendor_name="Mitsubishi Electric",
                model_name="GT25-WLAN",
                status="End of Life (EOL)",
                stage_date_utc="2025-01-01T00:00:00Z"
            )
        ]
        metrics = collector.compute_metrics(products, 1, 0)
        alert_text = AlertDispatcher.format_alert_text(metrics)

        self.assertIn("LIFECYCLE PIPELINE ALERT", alert_text)
        self.assertIn("run_obs_003", alert_text)
        self.assertIn("1 EOL", alert_text)


if __name__ == "__main__":
    unittest.main()
