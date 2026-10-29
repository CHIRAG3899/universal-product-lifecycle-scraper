"""
Temporary Artifacts & Traceability Module for Lifecycle Scraper.
Creates an isolated run directory for each execution and saves per-vendor
metadata files, audit logs, and extraction traces for compliance review.
"""

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scraper.models import ProductRecord

logger = logging.getLogger("ai_scraper.artifacts")


class RunArtifactManager:
    """
    Manages per-run, per-vendor temporary artifact directories.
    Automatically purges older run directories on each execution so ONLY
    the artifact of the last/current run is retained on disk.
    Provides complete traceability and clean post-review lifecycle deletion.
    """

    def __init__(self, base_artifacts_dir: Path, run_id: Optional[str] = None, prune_old_runs: bool = True):
        self.base_dir = Path(base_artifacts_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.run_id = run_id or f"run_{now_str}"
        self.run_dir = self.base_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

        if prune_old_runs:
            self.cleanup_previous_runs()

        logger.info(f"Initialized temporary run artifacts directory (retaining only latest run): {self.run_dir}")

    def cleanup_previous_runs(self) -> int:
        """
        Deletes all previous run artifact directories in base_dir, keeping ONLY the current/last run.
        Returns the number of deleted directories.
        """
        deleted_count = 0
        if not self.base_dir.exists():
            return 0

        for item in self.base_dir.iterdir():
            if item.is_dir() and item.resolve() != self.run_dir.resolve():
                try:
                    shutil.rmtree(item, ignore_errors=True)
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Could not delete old run artifact directory {item}: {e}")

        if deleted_count > 0:
            logger.info(f"Purged {deleted_count} older run directories. Retaining only current run: {self.run_dir}")
        return deleted_count

    def purge_after_review(self) -> bool:
        """
        Deletes the current run artifact directory after review is complete.
        Returns True if successfully deleted.
        """
        if self.run_dir.exists():
            try:
                shutil.rmtree(self.run_dir, ignore_errors=True)
                logger.info(f"Purged temporary review artifacts for run: {self.run_id}")
                return True
            except Exception as e:
                logger.warning(f"Could not purge review artifacts directory {self.run_dir}: {e}")
                return False
        return False

    def save_vendor_trace(
        self,
        vendor_id: str,
        vendor_name: str,
        products: List[ProductRecord],
        crawl_stats: Dict[str, Any]
    ) -> Path:
        """
        Saves metadata and traceability files for a specific vendor in its dedicated subfolder.
        """
        vendor_dir = self.run_dir / vendor_id
        vendor_dir.mkdir(parents=True, exist_ok=True)

        # 1. Metadata Trace File (stores metadata for all models)
        metadata_records = []
        for p in products:
            metadata_records.append({
                "fingerprint": p.fingerprint,
                "model_name": p.model_name,
                "stage": p.stage,
                "vendor_status": p.vendor_status,
                "stage_date_utc": p.stage_date_utc,
                "metadata": p.metadata
            })

        meta_file = vendor_dir / "metadata.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump({
                "vendor_id": vendor_id,
                "vendor_name": vendor_name,
                "run_id": self.run_id,
                "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "total_records": len(metadata_records),
                "records": metadata_records
            }, f, indent=2, ensure_ascii=False)

        # 2. Audit Trace File (records crawl execution stats, URLs, and errors)
        audit_file = vendor_dir / "audit_trace.json"
        with open(audit_file, "w", encoding="utf-8") as f:
            json.dump({
                "vendor_id": vendor_id,
                "vendor_name": vendor_name,
                "run_id": self.run_id,
                "stats": crawl_stats,
                "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            }, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved artifacts for vendor '{vendor_name}' in: {vendor_dir}")
        return vendor_dir

    def finalize_manifest(self, summary_metrics: Dict[str, Any]) -> Path:
        """Saves top-level run manifest summarizing all vendor traces in this execution."""
        manifest_file = self.run_dir / "run_manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump({
                "run_id": self.run_id,
                "completed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "metrics": summary_metrics
            }, f, indent=2, ensure_ascii=False)
        logger.info(f"Finalized run manifest at: {manifest_file}")
        return manifest_file
