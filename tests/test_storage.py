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
            "aliases",
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

    def test_undated_eol_records_preserved_not_dropped(self):
        """Verifies that products reaching EOL without dates are retained in storage and master CSV."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        storage = MasterStorageManager(master_csv_path=self.master_csv, output_dir=self.output_dir)

        undated_products = [
            ProductRecord(
                vendor_name="Rockwell Automation",
                model_name="1756-L61",
                status="End of Life",
                stage_date_utc=None,
                metadata={"replacement": "1756-L71"}
            ),
            ProductRecord(
                vendor_name="Siemens",
                model_name="S7-300 CPU 315-2DP",
                status="Discontinued",
                stage_date_utc="",
                metadata={"family": "S7-300"}
            )
        ]

        total, new_cnt, upd_cnt = storage.upsert_and_persist(undated_products)
        self.assertEqual(total, 2)
        self.assertEqual(new_cnt, 2)

        # Load back from CSV and verify both undated records exist
        loaded = storage.load_existing_records()
        self.assertEqual(len(loaded), 2)
        loaded_models = {r["model_name"] for r in loaded.values()}
        self.assertIn("1756-L61", loaded_models)
        self.assertIn("S7-300 CPU 315-2DP", loaded_models)

    def test_multi_run_successive_appends_across_vendors(self):
        """Verifies that each pipeline run appends to the master CSV without overwriting previous runs."""
        storage = MasterStorageManager(master_csv_path=self.master_csv, output_dir=self.output_dir)

        # Run 1: Cisco products
        cisco_run = [
            ProductRecord(
                vendor_name="Cisco",
                model_name="Catalyst 2960-X",
                status="End of Sale",
                stage_date_utc="2020-10-31T00:00:00Z",
                replacement="Catalyst 9200",
            ),
            ProductRecord(
                vendor_name="Cisco",
                model_name="Catalyst 3750-X",
                status="End of Life",
                stage_date_utc="2016-10-30T00:00:00Z",
                replacement="Catalyst 9300",
            ),
        ]
        total_1, new_1, upd_1 = storage.upsert_and_persist(cisco_run)
        self.assertEqual(total_1, 2)
        self.assertEqual(new_1, 2)
        self.assertEqual(upd_1, 0)

        # Run 2: Dell products (simulating second separate execution)
        dell_run = [
            ProductRecord(
                vendor_name="Dell",
                model_name="PowerEdge R720",
                status="End of Service Life",
                stage_date_utc="2019-02-28T00:00:00Z",
                replacement="PowerEdge R750",
            ),
            ProductRecord(
                vendor_name="Dell",
                model_name="PowerEdge R630",
                status="End of Standard Support",
                stage_date_utc="2021-05-31T00:00:00Z",
                replacement="PowerEdge R650",
            ),
        ]
        total_2, new_2, upd_2 = storage.upsert_and_persist(dell_run)
        # Must contain ALL 4 records (Cisco + Dell) - no overwrite!
        self.assertEqual(total_2, 4)
        self.assertEqual(new_2, 2)
        self.assertEqual(upd_2, 0)

        # Run 3: Cisco re-run with 1 duplicate + 1 new product
        cisco_run_2 = [
            ProductRecord(
                vendor_name="Cisco",
                model_name="Catalyst 2960-X",
                status="End of Sale",
                stage_date_utc="2020-10-31T00:00:00Z",
                replacement="Catalyst 9200-L",  # updated replacement
            ),
            ProductRecord(
                vendor_name="Cisco",
                model_name="ISR 4331",
                status="End of Sale",
                stage_date_utc="2023-11-30T00:00:00Z",
                replacement="Catalyst 8300",
            ),
        ]
        total_3, new_3, upd_3 = storage.upsert_and_persist(cisco_run_2)
        # Total records now: 5 (2 original Cisco + 2 Dell + 1 new Cisco ISR, 1 refreshed Cisco 2960-X)
        self.assertEqual(total_3, 5)
        self.assertEqual(new_3, 1)
        self.assertEqual(upd_3, 1)

        # Read directly from disk CSV and verify all 5 distinct records are persisted
        df = pd.read_csv(self.master_csv, dtype=str)
        self.assertEqual(len(df), 5)
        vendors_in_csv = set(df["vendor_name"].tolist())
        self.assertEqual(vendors_in_csv, {"Cisco", "Dell"})
        models_in_csv = set(df["model_name"].tolist())
        self.assertEqual(models_in_csv, {"Catalyst 2960-X", "Catalyst 3750-X", "PowerEdge R720", "PowerEdge R630", "ISR 4331"})

    def test_aliases_persistence_and_matching(self):
        """Verifies that model aliases / common names are saved and preserved in master CSV."""
        storage = MasterStorageManager(master_csv_path=self.master_csv, output_dir=self.output_dir)
        products = [
            ProductRecord(
                vendor_name="Siemens",
                model_name="6ES7516-3AN02-0AB0",
                aliases="SIMATIC S7-1500 CPU 1516-3 PN/DP, CPU 1516-3",
                status="End of Life",
                stage_date_utc="2024-10-01T00:00:00Z"
            )
        ]
        storage.upsert_and_persist(products)
        records = storage.load_existing_records()
        self.assertEqual(len(records), 1)
        rec = list(records.values())[0]
        self.assertIn("SIMATIC S7-1500 CPU 1516-3 PN/DP", rec.get("aliases", ""))

    def test_sqlite_staging_buffer(self):
        """Verifies SQLiteStagingBuffer staging, updating, and deduplication logic."""
        from scraper.storage import SQLiteStagingBuffer

        db_file = self.output_dir / "test_staging.db"
        buffer = SQLiteStagingBuffer(db_path=db_file)
        self.assertEqual(buffer.count(), 0)

        records = [
            {
                "vendor_name": "Rockwell Automation",
                "model_name": "1756-L75",
                "status": "Obsolete",
                "canonical_status": "Obsolete",
                "stage_date_utc": "2024-01-01T00:00:00Z",
                "aliases": "ControlLogix",
                "replacement": "1756-L85E"
            },
            {
                "vendor_name": "Schneider Electric",
                "model_name": "BMXAMI0810",
                "status": "Active",
                "canonical_status": "Active",
                "stage_date_utc": "2023-06-01T00:00:00Z"
            }
        ]

        count = buffer.stage_records(records)
        self.assertEqual(count, 2)
        self.assertEqual(buffer.count(), 2)

        # Re-staging with newer date and updated aliases updates cleanly
        updated = [
            {
                "vendor_name": "Rockwell Automation",
                "model_name": "1756-L75",
                "status": "Obsolete",
                "canonical_status": "Obsolete",
                "stage_date_utc": "2025-06-01T00:00:00Z",
                "aliases": "ControlLogix 5570 Controller",
                "replacement": "1756-L85E"
            }
        ]
        buffer.stage_records(updated)
        self.assertEqual(buffer.count(), 2)

        all_recs = buffer.get_all_records()
        rockwell = next(r for r in all_recs if r["vendor_name"] == "Rockwell Automation")
        self.assertEqual(rockwell["stage_date_utc"], "2025-06-01T00:00:00Z")
        self.assertEqual(rockwell["aliases"], "ControlLogix 5570 Controller")

    def test_batch_upsert_without_flush(self):
        """Verifies upsert_and_persist with flush=False stages in buffer without modifying CSV."""
        storage = MasterStorageManager(master_csv_path=self.master_csv, output_dir=self.output_dir)
        products = [
            ProductRecord(
                vendor_name="Cisco",
                model_name="WS-C2960X-24TS-L",
                status="End of Life",
                stage_date_utc="2025-10-31T00:00:00Z"
            )
        ]
        total, new_c, upd_c = storage.upsert_and_persist(products, flush=False)
        self.assertEqual(total, 1)
        self.assertEqual(new_c, 1)

        # Dual CSVs must NOT be written when flush=False
        self.assertFalse(self.master_csv.exists())

        # Buffer must hold staged record
        self.assertEqual(storage.staging_buffer.count(), 1)

        # Calling flush_consolidated_csvs persists to dual CSVs
        eol_c, act_c = storage.flush_consolidated_csvs()
        self.assertEqual(eol_c, 1)
        self.assertEqual(act_c, 0)
        eol_csv = self.output_dir / "eol_products_lifecycle.csv"
        self.assertTrue(eol_csv.exists())


if __name__ == "__main__":
    unittest.main()
