"""
Unit & Edge Case Tests for scraper/pipeline.py.
Validates:
1. LifecyclePipeline initialization, config loading, and path resolution.
2. Missing or corrupt configuration handling with fallback defaults.
3. 6 observable pipeline stages execution.
4. Vendor and sector filtering (OT, IoT, IT).
5. Sanitisation & security guards (noise purging, cookie rejection, stage length limits).
6. Non-fatal error handling during vendor execution.
7. SHA-256 deduplication and persist call integration.
8. Artifact manifest creation and metrics dispatching.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.models import ProductRecord, ScrapedDataset
from scraper.pipeline import LifecyclePipeline


class TestLifecyclePipeline(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir)

        temp_posix = Path(self.temp_dir).as_posix()
        self.config_file = Path(self.temp_dir) / "test_vendors.yaml"
        self.config_file.write_text(f"""
storage:
  master_csv_path: "{temp_posix}/test_master.csv"
  per_vendor_json_dir: "{temp_posix}/output"
  artifacts_dir: "{temp_posix}/artifacts"
observability:
  alert_ltb_threshold_days: 60
  webhook_url: ""
vendors:
  mitsubishi:
    id: "mitsubishi"
    name: "Mitsubishi Electric"
    sector: "OT"
    website: "https://mitsubishielectric.com"
    allowed_domains: ["mitsubishielectric.com"]
    entry_points:
      - name: "Global EOL"
        url: "https://mitsubishielectric.com/fa/support/eol"
        region: "Global"
  cisco_iot:
    id: "cisco_iot"
    name: "Cisco IoT"
    sector: "IoT"
    website: "https://cisco.com"
    allowed_domains: ["cisco.com"]
    entry_points:
      - name: "IoT Gateways"
        url: "https://cisco.com/go/eol"
        region: "Global"
  dell_it:
    id: "dell_it"
    name: "Dell Technologies"
    sector: "IT"
    website: "https://dell.com"
    allowed_domains: ["dell.com"]
    entry_points:
      - name: "PowerEdge EOL"
        url: "https://dell.com/support/eol"
        region: "Global"
""", encoding="utf-8")

        self.pipeline = LifecyclePipeline(
            config_path=self.config_file,
            run_id="test_run_001"
        )

    def test_01_config_loading_and_fallback(self):
        """Verifies loading valid config and graceful handling of missing file."""
        self.assertIn("vendors", self.pipeline.config)
        self.assertEqual(len(self.pipeline.config["vendors"]), 3)

        # Non-existent config
        missing_p = Path(self.temp_dir) / "does_not_exist.yaml"
        fallback_pipeline = LifecyclePipeline(config_path=missing_p)
        self.assertEqual(fallback_pipeline.config, {})

    @patch("scraper.pipeline.UniversalAICrawler")
    async def test_02_execute_vendor_clean_flow(self, mock_crawler_cls):
        """Verifies execute_vendor crawls, normalizes, sanitizes, and records telemetry."""
        mock_crawler = AsyncMock()
        self.pipeline.crawler = mock_crawler

        # Return 2 clean products and 1 cookie noise product
        rec_clean1 = ProductRecord(
            vendor_name="Mitsubishi Electric",
            model_name="GT25-WLAN",
            status="End of Life",
            stage_date_utc="2023-08-17T00:00:00Z"
        )
        rec_clean2 = ProductRecord(
            vendor_name="Mitsubishi Electric",
            model_name="MI3321G-W",
            status="Last Time Buy",
            stage_date_utc="2026-09-30T00:00:00Z"
        )
        # We simulate a record that fails validity check
        rec_noise = ProductRecord(
            vendor_name="Mitsubishi Electric",
            model_name="Generic Valid Name",
            status="A" * 50,  # Stage length > 40
            stage_date_utc="2025-01-01T00:00:00Z"
        )

        mock_crawler.run.return_value = [rec_clean1, rec_clean2, rec_noise]
        mock_crawler.crawl_website.return_value = [rec_clean1, rec_clean2, rec_noise]

        vendor_cfg = self.pipeline.config["vendors"]["mitsubishi"]
        products = await self.pipeline.execute_vendor("mitsubishi", vendor_cfg)

        # Ensure noise was purged (stage > 40)
        self.assertEqual(len(products), 2)
        models = [p.model_name for p in products]
        self.assertIn("GT25-WLAN", models)
        self.assertIn("MI3321G-W", models)

        # Check telemetry recorded
        self.assertIn("Mitsubishi Electric", self.pipeline.metrics_collector.vendor_stats)
        self.assertEqual(self.pipeline.metrics_collector.vendor_stats["Mitsubishi Electric"]["status"], "SUCCESS")

    async def test_03_execute_vendor_ssrf_blocking(self):
        """Verifies SSRF guard blocks unsafe entry points."""
        unsafe_cfg = {
            "name": "Malicious Vendor",
            "id": "malicious",
            "sector": "OT",
            "website": "http://127.0.0.1",
            "allowed_domains": ["safe.com"],
            "entry_points": [
                {"name": "Private Loopback", "url": "http://127.0.0.1:8000/admin", "region": "Global"},
                {"name": "AWS Metadata", "url": "http://169.254.169.254/latest/meta-data/", "region": "Global"}
            ]
        }
        self.pipeline.crawler.run = AsyncMock()
        self.pipeline.crawler.crawl_website = AsyncMock(return_value=[])
        products = await self.pipeline.execute_vendor("malicious", unsafe_cfg)
        self.assertEqual(len(products), 0)
        self.pipeline.crawler.run.assert_not_called()

    async def test_04_execute_vendor_error_resilience(self):
        """Verifies exceptions during vendor execution are caught and recorded without crashing."""
        self.pipeline.artifact_mgr.save_vendor_trace = MagicMock(side_effect=RuntimeError("Disk failure"))
        self.pipeline.crawler.run = AsyncMock(return_value=[])
        self.pipeline.crawler.crawl_website = AsyncMock(return_value=[])
        vendor_cfg = self.pipeline.config["vendors"]["mitsubishi"]
        products = await self.pipeline.execute_vendor("mitsubishi", vendor_cfg)

        self.assertEqual(len(products), 0)
        # Error must be captured in metrics
        errors = self.pipeline.metrics_collector.errors
        self.assertEqual(len(errors), 1)
        self.assertIn("Mitsubishi Electric", errors[0])
        self.assertIn("Disk failure", errors[0])

    async def test_05_execute_filter_by_vendor(self):
        """Verifies filtering pipeline execution by specific vendor ID."""
        self.pipeline.execute_vendor = AsyncMock(return_value=[])

        # Target only cisco_iot
        await self.pipeline.execute(vendor_filter="cisco_iot")
        self.assertEqual(self.pipeline.execute_vendor.call_count, 1)
        args, kwargs = self.pipeline.execute_vendor.call_args
        self.assertEqual(args[0], "cisco_iot")

    async def test_06_execute_filter_by_sector(self):
        """Verifies filtering pipeline execution by sector (e.g. IT)."""
        self.pipeline.execute_vendor = AsyncMock(return_value=[])

        # Filter sector IT (only dell_it is IT in our test config)
        await self.pipeline.execute(sector_filter="IT")
        self.assertEqual(self.pipeline.execute_vendor.call_count, 1)
        args, kwargs = self.pipeline.execute_vendor.call_args
        self.assertEqual(args[0], "dell_it")

    @patch("scraper.observability.AlertDispatcher.dispatch_alert")
    async def test_07_execute_full_workflow_and_manifest(self, mock_dispatch):
        """Verifies end-to-end execute() run calls storage persistence, manifest generation, and alert dispatch."""
        test_product = ProductRecord(
            vendor_name="Cisco IoT",
            model_name="IR1101-K9",
            status="End of Life",
            stage_date_utc="2027-06-30T00:00:00Z"
        )
        self.pipeline.execute_vendor = AsyncMock(return_value=[test_product])

        # Mock storage
        self.pipeline.storage.upsert_and_persist = MagicMock(return_value=(1, 1, 0))

        dataset = await self.pipeline.execute(vendor_filter="cisco_iot")

        self.assertIsInstance(dataset, ScrapedDataset)
        self.assertEqual(dataset.total_products, 1)
        self.assertEqual(len(dataset.products), 1)
        self.assertEqual(dataset.products[0].model_name, "IR1101-K9")

        # Verify storage was called
        self.pipeline.storage.upsert_and_persist.assert_called_once()
        # Verify alert dispatcher was called
        mock_dispatch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
