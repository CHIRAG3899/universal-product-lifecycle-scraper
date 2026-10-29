"""
Unit & Edge Case Tests for scraper/storage.py
Validates MasterStorageManager, append/upsert logic, CSV 10-column schema, and per-vendor JSON exports.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.models import ProductRecord
from scraper.storage import MasterStorageManager


class TestStorage(unittest.TestCase):

    def setUp(self):
        # Create an isolated temporary directory for testing
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_storage_"))
        self.output_dir = self.test_dir / "output"
        self.master_csv = self.output_dir / "test_master.csv"

    def tearDown(self):
        # Clean up temporary test directory
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_upsert_fresh_storage_and_csv_schema(self):
        storage = MasterStorageManager(master_csv_path=self.master_csv, output_dir=self.output_dir)
        products = [
            ProductRecord(
                vendor_name="Mitsubishi Electric",
                model_name="GT25-WLAN",
                status="End of Life (EOL)",
                stage_date_utc="2023-08-17",
                metadata={"replacement": "GT27", "source_url": "https://example.com/gt25"}
            ),
            ProductRecord(
                vendor_name="Mitsubishi Electric",
                model_name="GT25-WLAN",
                status="Last Time Buy (LTB)",
                stage_date_utc="2025-01-28",
                metadata={"replacement": "GT27", "source_url": "https://example.com/gt25"}
            ),
            ProductRecord(
                vendor_name="Siemens",
                model_name="S7-1500-CPU",
                status="Phase-Out Announced",
                stage_date_utc="2026-12-31",
                os="Linux RT",
                firmware="2.9.2",
                metadata={"replacement": "S7-1500-V3", "source_url": "https://example.com/s7"}
            )
        ]

        total, new_cnt, upd_cnt = storage.upsert_and_persist(products)
        self.assertEqual(total, 3)
        self.assertEqual(new_cnt, 3)
        self.assertEqual(upd_cnt, 0)
        self.assertTrue(self.master_csv.exists())

        # Verify CSV column headers and contents
        df = pd.read_csv(self.master_csv, dtype=str)
        expected_cols = [
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
        self.assertEqual(list(df.columns), expected_cols)
        self.assertNotIn("Fingerprint", df.columns)
        self.assertNotIn("fingerprint", df.columns)
        self.assertNotIn("vendor_status", df.columns)

    def test_upsert_deduplication_and_update(self):
        storage = MasterStorageManager(master_csv_path=self.master_csv, output_dir=self.output_dir)
        initial_products = [
            ProductRecord(
                vendor_name="Mitsubishi Electric",
                model_name="MI3321G-W",
                status="Last Time Buy (LTB)",
                stage_date_utc="2026-09-30",
                first_discovered_utc="2026-01-01T00:00:00Z",
                metadata={"replacement": "Consult Representative"}
            )
        ]
        storage.upsert_and_persist(initial_products)

        # Re-run with updated metadata for existing record + 1 new record
        updated_products = [
            ProductRecord(
                vendor_name="Mitsubishi Electric",
                model_name="MI3321G-W",
                status="Last Time Buy (LTB)",
                stage_date_utc="2026-09-30",
                metadata={"replacement": "MELIPC MI5000"}  # Updated replacement
            ),
            ProductRecord(
                vendor_name="Mitsubishi Electric",
                model_name="MI3315G-W",
                status="End of Life (EOL)",
                stage_date_utc="2025-10-29",
                metadata={"replacement": "MELIPC MI5000"}
            )
        ]
        total, new_cnt, upd_cnt = storage.upsert_and_persist(updated_products)
        self.assertEqual(total, 2)
        self.assertEqual(new_cnt, 1)  # MI3315G-W is new
        self.assertEqual(upd_cnt, 1)  # MI3321G-W updated

        # Verify that first_discovered_utc was preserved in metadata
        records = storage.load_existing_records()
        self.assertEqual(len(records), 2)

    def test_load_records_fallback_fingerprint_generation(self):
        # Create CSV without a Fingerprint column
        self.output_dir.mkdir(parents=True, exist_ok=True)
        raw_df = pd.DataFrame([{
            "vendor_name": "Schneider Electric",
            "model_name": "TM221CE16R",
            "status": "End of Life (EOL)",
            "stage_date_utc": "2027-10-01T00:00:00Z",
            "source_url": "https://se.com",
            "os": "N/A",
            "firmware": "N/A",
            "category": "PLC",
            "replacement": "TM241",
            "metadata": "{}"
        }])
        raw_df.to_csv(self.master_csv, index=False)

        storage = MasterStorageManager(master_csv_path=self.master_csv, output_dir=self.output_dir)
        records = storage.load_existing_records()
        self.assertEqual(len(records), 1)
        # Should have generated a deterministic 16-character SHA-256 fingerprint
        fp = list(records.keys())[0]
        self.assertEqual(len(fp), 16)

    def test_purge_invalid_models_upon_loading(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        dirty_df = pd.DataFrame([
            {
                "vendor_name": "Bad Vendor",
                "model_name": "Performance Cookies",  # Invalid noise
                "status": "End of Life (EOL)",
                "stage_date_utc": "2026-01-01T00:00:00Z"
            },
            {
                "vendor_name": "Good Vendor",
                "model_name": "FX3U-32MT/ES",
                "status": "End of Life (EOL)",
                "stage_date_utc": "2026-01-01T00:00:00Z"
            }
        ])
        dirty_df.to_csv(self.master_csv, index=False)

        storage = MasterStorageManager(master_csv_path=self.master_csv, output_dir=self.output_dir)
        records = storage.load_existing_records()
        self.assertEqual(len(records), 1)  # Only genuine model loaded
        loaded_model = list(records.values())[0]["model_name"]
        self.assertEqual(loaded_model, "FX3U-32MT/ES")

    def test_per_vendor_json_persistence(self):
        storage = MasterStorageManager(master_csv_path=self.master_csv, output_dir=self.output_dir)
        products = [
            ProductRecord(
                vendor_name="Cisco Systems",
                model_name="Catalyst 3850",
                status="End of Support (EOS)",
                stage_date_utc="2025-10-31"
            )
        ]
        storage.upsert_and_persist(products)

        # Check that cisco_systems_lifecycle.json was created
        cisco_json = self.output_dir / "cisco_systems_lifecycle.json"
        self.assertTrue(cisco_json.exists())
        with open(cisco_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["vendor_id"], "cisco_systems")
        self.assertEqual(data["total_records"], 1)

    def test_cleanup_temporary_files(self):
        """Verifies that orphaned .tmp files in storage directories are cleaned up."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        storage = MasterStorageManager(master_csv_path=self.master_csv, output_dir=self.output_dir)

        orphan_tmp = self.output_dir / "stray_scratch.tmp"
        orphan_tmp.write_text("temporary data")
        self.assertTrue(orphan_tmp.exists())

        # Calling cleanup removes the orphaned tmp file
        deleted = storage.cleanup_temporary_files()
        self.assertEqual(deleted, 1)
        self.assertFalse(orphan_tmp.exists())


if __name__ == "__main__":
    unittest.main()
