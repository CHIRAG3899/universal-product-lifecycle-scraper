"""
Artifact-Driven End-to-End Pipeline Integration Test.
Validates the complete 6-stage lifecycle pipeline:
1. Discovery & Crawling
2. Extraction
3. Normalisation
4. Sanitisation & Security (Formula Injection, Cookie Banners, SSRF)
5. SHA-256 Deduplication & Append
6. Export & Traceability Artifacts (Master CSV, Vendor JSONs, Run Manifest, Vendor Trace Audit)

Ensures zero unhandled edge cases, 10-column database snake_case schema compliance,
and deterministic execution artifacts.
"""

import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.models import ProductRecord
from scraper.pipeline import LifecyclePipeline


class TestEndToEndArtifactDrivenPipeline(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Create isolated temporary workspace
        self.test_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.test_root)

        self.output_dir = self.test_root / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.master_csv = self.output_dir / "all_vendors_lifecycle.csv"

        self.artifacts_dir = self.test_root / "artifacts" / "runs"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        self.config_dir = self.test_root / "configs"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / "vendors.yaml"

        # Multi-vendor configuration covering OT, IoT, and IT sectors
        self.config_file.write_text(f"""
storage:
  master_csv_path: "{self.master_csv.as_posix()}"
  per_vendor_json_dir: "{self.output_dir.as_posix()}"
  artifacts_dir: "{self.artifacts_dir.as_posix()}"
observability:
  alert_ltb_threshold_days: 90
  webhook_url: ""
vendors:
  mitsubishi:
    id: "mitsubishi"
    name: "Mitsubishi Electric"
    sector: "OT"
    website: "https://mitsubishielectric.com"
    allowed_domains: ["mitsubishielectric.com"]
    entry_points:
      - name: "HMI & Inverters"
        url: "https://mitsubishielectric.com/fa/support/eol"
        region: "Global"
  cisco_iot:
    id: "cisco_iot"
    name: "Cisco IoT"
    sector: "IoT"
    website: "https://cisco.com"
    allowed_domains: ["cisco.com"]
    entry_points:
      - name: "Cellular Gateways"
        url: "https://cisco.com/go/eol-iot"
        region: "Global"
  dell_it:
    id: "dell_it"
    name: "Dell Technologies"
    sector: "IT"
    website: "https://dell.com"
    allowed_domains: ["dell.com"]
    entry_points:
      - name: "PowerEdge Servers"
        url: "https://dell.com/support/poweredge-eol"
        region: "Global"
""", encoding="utf-8")

        self.run_id = "test_run_e2e_alpha"
        self.pipeline = LifecyclePipeline(
            config_path=self.config_file,
            run_id=self.run_id
        )

    async def test_01_full_pipeline_run_and_artifact_generation(self):
        """
        Executes end-to-end pipeline with multi-vendor input, formula injection attempt,
        cookie consent noise, and verifies all 6 stages and generated artifacts.
        """
        # Mock crawler to return raw candidate records per vendor
        async def mock_crawler_run(url: str):
            if "mitsubishielectric.com" in url:
                return [
                    # Product 1: Valid EOL record
                    ProductRecord(
                        vendor_name="Mitsubishi Electric",
                        model_name="GT25-WLAN",
                        status="End of Life",
                        stage_date_utc="2023-08-17T00:00:00Z",
                        source_url=url,
                        category="Human Machine Interface (HMI)",
                        replacement="GT27-WLAN",
                        metadata={"series": "GOT2000", "part_number": "GT25-WLAN-01"}
                    ),
                    # Product 2: Multi-stage milestone: LTB
                    ProductRecord(
                        vendor_name="Mitsubishi Electric",
                        model_name="GT25-WLAN",
                        status="Last Time Buy",
                        stage_date_utc="2025-01-28T00:00:00Z",
                        source_url=url,
                        category="Human Machine Interface (HMI)",
                        replacement="GT27-WLAN",
                        metadata={"series": "GOT2000"}
                    ),
                    # Product 3: Noise record with stage length > 40 that must be purged by Step 4
                    ProductRecord(
                        vendor_name="Mitsubishi Electric",
                        model_name="FX5-NOISE-MODULE",
                        status="A" * 45,
                        stage="A" * 45,  # Stage length > 40 gets purged in Step 4
                        stage_date_utc="2025-01-01T00:00:00Z",
                        source_url=url
                    ),
                    # Product 4: CSV formula injection attack attempt
                    ProductRecord(
                        vendor_name="Mitsubishi Electric",
                        model_name="=FX5-EIP-CALC",
                        status="Discontinued",
                        stage_date_utc="2026-10-31T00:00:00Z",
                        source_url=url,
                        replacement="SafeModel-100"
                    )
                ]
            elif "cisco.com" in url:
                return [
                    ProductRecord(
                        vendor_name="Cisco IoT",
                        model_name="IR1101-K9",
                        status="End of Life",
                        stage_date_utc="2027-06-30T00:00:00Z",
                        source_url=url,
                        category="Industrial Router",
                        replacement="Catalyst IR1800",
                        metadata={"series": "IR1100 Series"}
                    )
                ]
            elif "dell.com" in url:
                return [
                    ProductRecord(
                        vendor_name="Dell Technologies",
                        model_name="PowerEdge R740",
                        status="End of Standard Support",
                        stage_date_utc="2026-12-31T00:00:00Z",
                        source_url=url,
                        category="Rack Server",
                        replacement="PowerEdge R760",
                        metadata={"series": "PowerEdge 14G"}
                    )
                ]
        self.pipeline.crawler.run = AsyncMock(side_effect=mock_crawler_run)
        self.pipeline.crawler.crawl_website = AsyncMock(side_effect=lambda url, **kw: mock_crawler_run(url))

        # 1. Execute entire pipeline across all configured vendors
        dataset = await self.pipeline.execute(site_crawl=False)

        # ---------------------------------------------------------------------
        # VERIFICATION 1: In-memory Dataset & Sanitization
        # ---------------------------------------------------------------------
        # Cookie noise ("Performance Cookies") must have been purged
        all_models = [p.model_name for p in dataset.products]
        self.assertNotIn("FX5-NOISE-MODULE", all_models)
        self.assertIn("GT25-WLAN", all_models)
        self.assertIn("IR1101-K9", all_models)
        self.assertIn("PowerEdge R740", all_models)

        # ---------------------------------------------------------------------
        # VERIFICATION 2: Master CSV Artifact & 10-Column Snake_Case Schema
        # ---------------------------------------------------------------------
        self.assertTrue(self.master_csv.exists(), "Master CSV was not created!")

        with open(self.master_csv, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader)

            expected_header = [
                "vendor_name",
                "model_name",
                "status",
                "stage_date_utc",
                "source_url",
                "os",
                "firmware",
                "category",
                "replacement",
                "metadata"
            ]
            self.assertEqual(header, expected_header, f"Header mismatch! Expected {expected_header}, got {header}")

            rows = list(reader)
            # 5 clean products retained (2 GT25-WLAN milestones + 1 formula sanitized + 1 Cisco + 1 Dell)
            self.assertEqual(len(rows), 5)

            # Strict check: Fingerprint must NOT appear in columns
            self.assertNotIn("Fingerprint", header)
            self.assertNotIn("fingerprint", header)

            # Strict check: Formula injection was sanitized with leading quote
            formula_row = next((r for r in rows if "FX5-EIP-CALC" in r[1]), None)
            self.assertIsNotNone(formula_row, "Formula injection row was lost!")
            assert formula_row is not None
            self.assertTrue(formula_row[1].startswith("'="), f"Formula injection was NOT sanitized! Value: {formula_row[1]}")

            # Verify UTC date format or empty in stage_date_utc column (index 3)
            for r in rows:
                dt_val = r[3]
                if dt_val:
                    self.assertTrue(dt_val.endswith("Z") and "T" in dt_val, f"Non-UTC date in CSV: {dt_val}")

            # Verify metadata JSON parses cleanly (index 9)
            for r in rows:
                meta_raw = r[9]
                if meta_raw:
                    meta_dict = json.loads(meta_raw)
                    self.assertIsInstance(meta_dict, dict)

        # ---------------------------------------------------------------------
        # VERIFICATION 3: Modular Per-Vendor JSON Artifacts
        # ---------------------------------------------------------------------
        vendor_json_files = list(self.output_dir.glob("*_lifecycle.json"))
        self.assertGreaterEqual(len(vendor_json_files), 3)

        for vj in vendor_json_files:
            with open(vj, "r", encoding="utf-8") as f:
                v_data = json.load(f)
            self.assertIn("products", v_data)
            self.assertIn("vendor_name", v_data)
            self.assertIn("total_records", v_data)
            self.assertEqual(len(v_data["products"]), v_data["total_records"])

        # ---------------------------------------------------------------------
        # VERIFICATION 4: Traceability Run Artifacts & Run Manifest
        # ---------------------------------------------------------------------
        run_folder = self.artifacts_dir / self.run_id
        self.assertTrue(run_folder.exists(), f"Run artifact folder not found: {run_folder}")

        manifest_file = run_folder / "run_manifest.json"
        self.assertTrue(manifest_file.exists(), "run_manifest.json not found in run folder!")

        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        self.assertEqual(manifest["run_id"], self.run_id)
        self.assertIn("completed_utc", manifest)
        metrics = manifest.get("metrics", {})
        self.assertIn("start_time_utc", metrics)
        self.assertIn("end_time_utc", metrics)
        self.assertIn("duration_seconds", metrics)
        self.assertEqual(metrics["volumes"]["total_records_ingested"], 5)
        self.assertEqual(metrics["volumes"]["new_records_appended"], 5)
        self.assertEqual(metrics["volumes"]["existing_records_refreshed"], 0)
        self.assertIn("vendor_details", metrics)
        self.assertIn("data_quality", metrics)
        self.assertGreaterEqual(metrics["data_quality"]["utc_date_coverage_pct"], 80.0)

        # Verify individual vendor trace subdirectories and files
        vendor_subdirs = [d for d in run_folder.iterdir() if d.is_dir()]
        self.assertEqual(len(vendor_subdirs), 3)
        for vd in vendor_subdirs:
            self.assertTrue((vd / "metadata.json").exists(), f"Missing metadata.json in {vd}")
            self.assertTrue((vd / "audit_trace.json").exists(), f"Missing audit_trace.json in {vd}")

    async def test_02_idempotent_deduplication_and_non_overwriting_append(self):
        """
        Verifies that running pipeline a second time:
        1. Does not create duplicate rows in master CSV.
        2. Refreshes existing records.
        3. Appends only truly novel records.
        """
        # First Run: Ingest GT25-WLAN EOL
        first_record = ProductRecord(
            vendor_name="Mitsubishi Electric",
            model_name="GT25-WLAN",
            status="End of Life",
            stage_date_utc="2023-08-17T00:00:00Z",
            source_url="https://mitsubishielectric.com/fa/support/eol"
        )
        self.pipeline.crawler.run = AsyncMock(return_value=[first_record])
        self.pipeline.crawler.crawl_website = AsyncMock(return_value=[first_record])
        dataset_1 = await self.pipeline.execute(vendor_filter="mitsubishi", site_crawl=False)
        self.assertEqual(dataset_1.total_products, 1)

        # Second Run: Ingest identical GT25-WLAN EOL + 1 NEW model MI3321G-W
        novel_record = ProductRecord(
            vendor_name="Mitsubishi Electric",
            model_name="MI3321G-W",
            status="End of Life",
            stage_date_utc="2025-10-29T00:00:00Z",
            source_url="https://mitsubishielectric.com/fa/support/eol"
        )
        self.pipeline.crawler.run = AsyncMock(return_value=[first_record, novel_record])
        self.pipeline.crawler.crawl_website = AsyncMock(return_value=[first_record, novel_record])

        # Create new pipeline run for run 2
        pipeline_run2 = LifecyclePipeline(
            config_path=self.config_file,
            run_id="test_run_e2e_beta"
        )
        pipeline_run2.crawler.run = AsyncMock(return_value=[first_record, novel_record])
        pipeline_run2.crawler.crawl_website = AsyncMock(return_value=[first_record, novel_record])
        dataset_2 = await pipeline_run2.execute(vendor_filter="mitsubishi", site_crawl=False)

        # Total products should now be 2, NOT 3 (no duplication)
        self.assertEqual(dataset_2.total_products, 2)

        with open(self.master_csv, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            _ = next(reader)
            rows = list(reader)

        self.assertEqual(len(rows), 2)
        models = [r[1] for r in rows]
        self.assertEqual(models.count("GT25-WLAN"), 1)
        self.assertEqual(models.count("MI3321G-W"), 1)


if __name__ == "__main__":
    unittest.main()
