"""
Unit & Edge Case Tests for scraper/artifacts.py
Validates RunArtifactManager, vendor trace logs, audit files, and manifest generation.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.artifacts import RunArtifactManager
from scraper.models import ProductRecord


class TestArtifacts(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_artifacts_"))

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_run_artifact_manager_init(self):
        manager = RunArtifactManager(base_artifacts_dir=self.test_dir, run_id="run_test_001")
        self.assertEqual(manager.run_id, "run_test_001")
        self.assertTrue(manager.run_dir.exists())
        self.assertTrue(manager.run_dir.is_dir())

    def test_save_vendor_trace_and_audit(self):
        manager = RunArtifactManager(base_artifacts_dir=self.test_dir, run_id="run_test_002")
        products = [
            ProductRecord(
                vendor_name="Rockwell Automation",
                model_name="1756-L83E",
                status="Active Mature",
                stage_date_utc="2027-06-30",
                metadata={"series": "ControlLogix 5580", "replacement": "1756-L85E"}
            )
        ]
        crawl_stats = {
            "pages_crawled": 1,
            "status_code": 200,
            "duration_ms": 1250
        }

        vendor_dir = manager.save_vendor_trace(
            vendor_id="rockwell_automation",
            vendor_name="Rockwell Automation",
            products=products,
            crawl_stats=crawl_stats
        )

        self.assertTrue(vendor_dir.exists())
        meta_file = vendor_dir / "metadata.json"
        audit_file = vendor_dir / "audit_trace.json"

        self.assertTrue(meta_file.exists())
        self.assertTrue(audit_file.exists())

        with open(meta_file, "r", encoding="utf-8") as f:
            meta_data = json.load(f)
        self.assertEqual(meta_data["vendor_id"], "rockwell_automation")
        self.assertEqual(meta_data["total_records"], 1)
        self.assertEqual(meta_data["records"][0]["model_name"], "1756-L83E")

        with open(audit_file, "r", encoding="utf-8") as f:
            audit_data = json.load(f)
        self.assertEqual(audit_data["stats"]["status_code"], 200)

    def test_finalize_manifest(self):
        manager = RunArtifactManager(base_artifacts_dir=self.test_dir, run_id="run_test_003")
        summary_metrics = {
            "total_vendors_processed": 5,
            "total_records_extracted": 120,
            "new_appended": 45,
            "updated": 75
        }
        manifest_path = manager.finalize_manifest(summary_metrics)
        self.assertTrue(manifest_path.exists())

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        self.assertEqual(manifest_data["run_id"], "run_test_003")
        self.assertEqual(manifest_data["metrics"]["total_vendors_processed"], 5)

    def test_cleanup_previous_runs_keeps_only_last_run(self):
        """Verifies initializing a new run deletes older run artifact directories, keeping only the latest."""
        run1 = RunArtifactManager(base_artifacts_dir=self.test_dir, run_id="run_old_001")
        self.assertTrue(run1.run_dir.exists())

        run2 = RunArtifactManager(base_artifacts_dir=self.test_dir, run_id="run_old_002")
        self.assertTrue(run2.run_dir.exists())

        # When run 3 initializes with prune_old_runs=True, run1 and run2 must be deleted
        run3 = RunArtifactManager(base_artifacts_dir=self.test_dir, run_id="run_latest_003", prune_old_runs=True)
        self.assertTrue(run3.run_dir.exists())
        self.assertFalse(run1.run_dir.exists())
        self.assertFalse(run2.run_dir.exists())

        # Verify only run 3 exists in test_dir
        subdirs = [p.name for p in self.test_dir.iterdir() if p.is_dir()]
        self.assertEqual(subdirs, ["run_latest_003"])

    def test_purge_after_review(self):
        """Verifies purge_after_review cleanly deletes the current run directory."""
        manager = RunArtifactManager(base_artifacts_dir=self.test_dir, run_id="run_to_purge")
        self.assertTrue(manager.run_dir.exists())
        res = manager.purge_after_review()
        self.assertTrue(res)
        self.assertFalse(manager.run_dir.exists())


if __name__ == "__main__":
    unittest.main()
