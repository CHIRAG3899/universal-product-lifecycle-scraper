"""
Persistent Resumable Crawler Memory, Knowledge Base, and Batch State Management.

Maintains incremental crawl state per vendor in `artifacts/run_state/{vendor_id}_state.json`.
Tracks:
- Discovered URLs/prefixes knowledge base with synchronization across runs
- Cycle tracking and automatic refresh once all batches complete
- Capability-based batch splitting (run one batch now, subsequent batches in next runs)
- Completed units (URLs crawled, sitemaps processed, family prefixes queried)
- Seen model identifiers to eliminate cross-session duplicates
- Last run timestamps and extraction counts
Enables the crawler to pause, batch, and resume without losing progress or re-querying completed pages.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_STATE_DIR = Path("artifacts") / "run_state"

CAPABILITY_DEFAULT_BATCH_SIZES: Dict[str, int] = {
    "sitemap": 10,
    "search_portal": 20,
    "dom_table": 15,
    "rest_api": 50,
    "default": 15,
}


class VendorRunState:
    """Manages persistent execution state, knowledge base, and batching queue for a vendor crawler."""

    def __init__(
        self,
        vendor_id: str,
        state_dir: Optional[Path] = None,
        cycle: int = 1,
        knowledge_base: Optional[Dict[str, Dict[str, Any]]] = None,
        pending_queue: Optional[List[str]] = None,
        completed_units: Optional[Set[str]] = None,
        failed_units: Optional[Set[str]] = None,
        seen_models: Optional[Set[str]] = None,
        total_records: int = 0,
        last_run_utc: Optional[str] = None,
        last_batch_info: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.vendor_id = vendor_id
        self.state_dir = Path(state_dir) if state_dir else DEFAULT_STATE_DIR
        self.cycle: int = max(1, cycle)
        self.knowledge_base: Dict[str, Dict[str, Any]] = knowledge_base or {}
        self.pending_queue: List[str] = pending_queue or []
        self.completed_units: Set[str] = completed_units or set()
        self.failed_units: Set[str] = failed_units or set()
        self.seen_models: Set[str] = seen_models or set()
        self.total_records: int = total_records
        self.last_run_utc: str = (
            last_run_utc or datetime.now(timezone.utc).isoformat()
        )
        self.last_batch_info: Dict[str, Any] = last_batch_info or {}
        self.metadata: Dict[str, Any] = metadata or {}

    @property
    def file_path(self) -> Path:
        sanitized_id = "".join(
            c if c.isalnum() or c in ("-", "_") else "_"
            for c in self.vendor_id.lower()
        )
        return self.state_dir / f"{sanitized_id}_state.json"

    def is_unit_completed(self, unit: str) -> bool:
        """Check if a URL, keyword, or sub-task has already been processed in the current cycle."""
        return unit.strip().lower() in self.completed_units

    def mark_unit_completed(self, unit: str, records_count: int = 0) -> None:
        """Mark a URL, keyword, or sub-task as completed."""
        clean = unit.strip().lower()
        if clean:
            self.completed_units.add(clean)
            self.pending_queue = [u for u in self.pending_queue if u.strip().lower() != clean]
            if clean not in self.knowledge_base:
                now_str = datetime.now(timezone.utc).isoformat()
                self.knowledge_base[clean] = {
                    "original_unit": unit.strip(),
                    "first_seen_utc": now_str,
                    "last_checked_utc": now_str,
                    "status": "completed",
                    "records_count": records_count,
                }
            else:
                self.knowledge_base[clean]["status"] = "completed"
                self.knowledge_base[clean]["last_checked_utc"] = datetime.now(timezone.utc).isoformat()
                self.knowledge_base[clean]["records_count"] = (
                    self.knowledge_base[clean].get("records_count", 0) + records_count
                )

    def is_model_seen(self, model_name: str) -> bool:
        """Check if a model name has already been extracted across sessions."""
        return model_name.strip().upper() in self.seen_models

    def record_model(self, model_name: str) -> None:
        """Record a newly harvested model SKU."""
        clean = model_name.strip().upper()
        if clean:
            self.seen_models.add(clean)

    def record_discovered_prefix(self, prefix: str) -> None:
        """Record dynamically discovered family prefix in persistent metadata."""
        if "discovered_prefixes" not in self.metadata:
            self.metadata["discovered_prefixes"] = []
        clean = prefix.strip().upper()
        if clean and clean not in self.metadata["discovered_prefixes"]:
            self.metadata["discovered_prefixes"].append(clean)
            self.metadata["discovered_prefixes"].sort()

    @property
    def discovered_prefixes(self) -> Set[str]:
        """Return set of previously discovered prefixes."""
        return set(self.metadata.get("discovered_prefixes", []))

    def sync_knowledge_base(self, discovered_units: List[str]) -> Tuple[List[str], bool]:
        """
        Synchronizes discovered URLs/prefixes with the persistent knowledge base.
        - Adds newly discovered units to the knowledge base and pending queue.
        - Updates timestamps on previously known units.
        - Detects when all units in a cycle are completed, increments cycle, and refreshes the queue.
        Returns: (active_pending_queue, is_new_cycle_triggered)
        """
        now_str = datetime.now(timezone.utc).isoformat()
        new_entries_count = 0
        seen_in_this_sync: Set[str] = set()

        for raw_u in discovered_units:
            clean = raw_u.strip()
            if not clean:
                continue
            clean_key = clean.lower()
            seen_in_this_sync.add(clean)

            if clean_key not in self.knowledge_base:
                self.knowledge_base[clean_key] = {
                    "original_unit": clean,
                    "first_seen_utc": now_str,
                    "last_checked_utc": now_str,
                    "status": "pending",
                    "records_count": 0,
                }
                if clean not in self.pending_queue and clean_key not in self.completed_units:
                    self.pending_queue.append(clean)
                new_entries_count += 1
            else:
                self.knowledge_base[clean_key]["last_checked_utc"] = now_str
                # If it was never added to pending or completed, ensure it's in pending
                if clean_key not in self.completed_units and clean not in self.pending_queue:
                    self.pending_queue.append(clean)

        if new_entries_count > 0:
            logger.info(
                f"[KB SYNC] Added {new_entries_count} new entries to knowledge base for {self.vendor_id}. "
                f"Total KB entries: {len(self.knowledge_base)}"
            )

        # Check if all units have been processed in the current cycle
        is_new_cycle = False
        if not self.pending_queue and self.knowledge_base:
            self.cycle += 1
            is_new_cycle = True
            logger.info(
                f"[KB CYCLE REFRESH] All units completed for cycle {self.cycle - 1}! "
                f"Restarting fresh refresh cycle {self.cycle} with full knowledge base refresh."
            )
            self.completed_units.clear()
            self.failed_units.clear()
            # Re-enqueue all known units in original casing where possible
            for k, meta in self.knowledge_base.items():
                orig = meta.get("original_unit", k)
                self.pending_queue.append(orig)
                meta["status"] = "pending"

        self.save()
        return self.pending_queue, is_new_cycle

    def get_next_batch(
        self, capability: str = "default", batch_size: Optional[int] = None
    ) -> List[str]:
        """
        Returns the next slice of pending units to process based on capability or explicit batch size.
        """
        if not self.pending_queue:
            return []

        effective_size = (
            batch_size
            if batch_size is not None and batch_size > 0
            else CAPABILITY_DEFAULT_BATCH_SIZES.get(capability.lower(), CAPABILITY_DEFAULT_BATCH_SIZES["default"])
        )
        batch = self.pending_queue[:effective_size]
        return batch

    def mark_batch_completed(
        self,
        batch: List[str],
        records_count: int = 0,
        failed_units: Optional[List[str]] = None,
    ) -> None:
        """
        Marks units from a processed batch as completed or failed, updates the knowledge base,
        removes them from pending_queue, and persists state.
        """
        failed_set = set(u.strip().lower() for u in (failed_units or []))
        now_str = datetime.now(timezone.utc).isoformat()

        for unit in batch:
            clean = unit.strip()
            clean_key = clean.lower()
            if not clean:
                continue

            self.pending_queue = [q for q in self.pending_queue if q.strip().lower() != clean_key]

            if clean_key in failed_set:
                self.failed_units.add(clean_key)
                if clean_key in self.knowledge_base:
                    self.knowledge_base[clean_key]["status"] = "failed"
                    self.knowledge_base[clean_key]["last_checked_utc"] = now_str
            else:
                self.completed_units.add(clean_key)
                if clean_key in self.knowledge_base:
                    self.knowledge_base[clean_key]["status"] = "completed"
                    self.knowledge_base[clean_key]["last_checked_utc"] = now_str
                    self.knowledge_base[clean_key]["records_count"] = (
                        self.knowledge_base[clean_key].get("records_count", 0) + records_count
                    )

        self.last_batch_info = {
            "batch_size": len(batch),
            "completed_in_batch": len(batch) - len(failed_set),
            "failed_in_batch": len(failed_set),
            "pending_remaining": len(self.pending_queue),
            "cycle": self.cycle,
            "timestamp_utc": now_str,
        }
        self.save()

    def save(self) -> None:
        """Atomically persist state to JSON."""
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            self.last_run_utc = datetime.now(timezone.utc).isoformat()
            payload = {
                "vendor_id": self.vendor_id,
                "cycle": self.cycle,
                "last_run_utc": self.last_run_utc,
                "total_records": self.total_records,
                "knowledge_base_size": len(self.knowledge_base),
                "knowledge_base": self.knowledge_base,
                "pending_queue_count": len(self.pending_queue),
                "pending_queue": self.pending_queue,
                "completed_units_count": len(self.completed_units),
                "completed_units": sorted(list(self.completed_units)),
                "failed_units_count": len(self.failed_units),
                "failed_units": sorted(list(self.failed_units)),
                "seen_models_count": len(self.seen_models),
                "seen_models": sorted(list(self.seen_models)),
                "last_batch_info": self.last_batch_info,
                "metadata": self.metadata,
            }
            tmp_path = self.file_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            tmp_path.replace(self.file_path)
            self.update_progress_tracking()
            logger.debug(
                f"[STATE] Successfully saved state for {self.vendor_id} "
                f"(Cycle {self.cycle}, KB: {len(self.knowledge_base)}, Pending: {len(self.pending_queue)}, "
                f"Completed: {len(self.completed_units)}, Seen: {len(self.seen_models)}) to {self.file_path}"
            )
        except Exception as e:
            logger.warning(
                f"[STATE] Failed to save state file {self.file_path}: {e}"
            )

    def update_progress_tracking(self, batch_size: Optional[int] = None, status: str = "IN_PROGRESS") -> None:
        """
        Maintains persistent progress records across all vendors in:
        - `artifacts/batch_progress.json`
        - `output/batch_progress.json`
        - `artifacts/batch_progress.md` (Human-readable markdown dashboard)
        Records: cycle, discovered units, completed units, pending units, batches completed, batches remaining.
        """
        try:
            from math import ceil
            b_size = max(1, batch_size or self.last_batch_info.get("batch_size") or 1)
            total_units = len(self.knowledge_base) or (len(self.pending_queue) + len(self.completed_units))
            completed_count = len(self.completed_units)
            pending_count = len(self.pending_queue)

            batches_completed = ceil(completed_count / b_size) if completed_count > 0 else 0
            batches_remaining = ceil(pending_count / b_size) if pending_count > 0 else 0
            progress_pct = round((completed_count / total_units * 100), 2) if total_units > 0 else 100.0

            from scraper.vendors import _get_yaml_vendors
            valid_vendors = set(_get_yaml_vendors().keys())
            if self.vendor_id not in valid_vendors:
                return

            progress_dir = Path("artifacts")
            progress_dir.mkdir(parents=True, exist_ok=True)
            output_dir = Path("output")
            output_dir.mkdir(parents=True, exist_ok=True)

            # Calculate active vs EOL record breakdown for the vendor from dual CSVs
            eol_count = 0
            active_count = 0
            eol_csv = output_dir / "eol_products_lifecycle.csv"
            active_csv = output_dir / "active_products_lifecycle.csv"
            clean_vid = self.vendor_id.lower().replace("_", "").replace("-", "")

            for csv_path, is_eol_file in [(eol_csv, True), (active_csv, False)]:
                if csv_path.exists():
                    try:
                        df = pd.read_csv(csv_path, encoding="utf-8-sig", keep_default_na=False)
                        v_mask = df["vendor_name"].astype(str).apply(
                            lambda vn: clean_vid in vn.lower().replace("_", "").replace("-", "").replace(" ", "")
                            or vn.lower().replace("_", "").replace("-", "").replace(" ", "") in clean_vid
                        )
                        v_df = df[v_mask]
                        if not v_df.empty:
                            if is_eol_file:
                                eol_count += len(v_df)
                            else:
                                active_count += len(v_df)
                    except Exception:
                        pass

            has_data = bool(self.total_records > 0 or (eol_count + active_count) > 0)
            data_status = "ACTIVE_DATA" if has_data else "NO_DATA"

            json_path = progress_dir / "batch_progress.json"
            all_progress: Dict[str, Any] = {"updated_utc": datetime.now(timezone.utc).isoformat(), "vendors": {}}
            if json_path.exists():
                try:
                    with open(json_path, "r", encoding="utf-8") as jf:
                        existing = json.load(jf)
                        if isinstance(existing, dict) and "vendors" in existing:
                            all_progress["vendors"] = {
                                k: v for k, v in existing["vendors"].items()
                                if k in valid_vendors
                            }
                except Exception:
                    pass

            rec_audit_file = output_dir / "reconciliation_audit.json"
            rec_data: Dict[str, Any] = {}
            if rec_audit_file.exists():
                try:
                    with open(rec_audit_file, "r", encoding="utf-8") as rf:
                        all_rec = json.load(rf)
                        rec_data = all_rec.get(self.vendor_id, {})
                except Exception:
                    pass

            vendor_entry = {
                "vendor_id": self.vendor_id,
                "cycle": self.cycle,
                "total_discovered_units": total_units,
                "completed_units": completed_count,
                "pending_units": pending_count,
                "batch_size": b_size,
                "batches_completed": batches_completed,
                "batches_remaining": batches_remaining,
                "total_records_harvested": self.total_records,
                "eol_records_count": eol_count,
                "active_records_count": active_count,
                "cross_entrypoint_duplicates_count": rec_data.get("cross_entrypoint_duplicates_count", 0),
                "step4_purged_noise_count": rec_data.get("step4_purged_noise_count", 0),
                "llm_rejected_count": rec_data.get("llm_rejected_count", 0),
                "reconciliation_explanation": rec_data.get("reconciliation_explanation", ""),
                "has_data": has_data,
                "data_status": data_status,
                "progress_percent": progress_pct,
                "status": "CYCLE_COMPLETE" if pending_count == 0 else status,
                "last_run_utc": self.last_run_utc,
            }
            all_progress["vendors"][self.vendor_id] = vendor_entry
            all_progress["updated_utc"] = datetime.now(timezone.utc).isoformat()

            def _safe_replace(src: Path, dst: Path) -> None:
                import time
                for attempt in range(4):
                    try:
                        src.replace(dst)
                        return
                    except (PermissionError, OSError):
                        time.sleep(0.05 * (attempt + 1))
                try:
                    # Fallback direct copy if replace is locked
                    import shutil
                    shutil.copyfile(src, dst)
                    src.unlink(missing_ok=True)
                except Exception:
                    pass

            for target_p in (json_path, output_dir / "batch_progress.json"):
                tmp_p = target_p.with_suffix(".tmp")
                with open(tmp_p, "w", encoding="utf-8") as f:
                    json.dump(all_progress, f, indent=2, ensure_ascii=False)
                _safe_replace(tmp_p, target_p)

            # Persist empty_vendors.json
            zero_data_vendors = [vid for vid, vdata in all_progress["vendors"].items() if not vdata.get("has_data", True)]
            empty_payload = {
                "updated_utc": all_progress["updated_utc"],
                "zero_data_count": len(zero_data_vendors),
                "empty_vendors": [
                    all_progress["vendors"][zvid] for zvid in sorted(zero_data_vendors)
                ]
            }
            for empty_p in (output_dir / "empty_vendors.json", progress_dir / "empty_vendors.json"):
                tmp_ep = empty_p.with_suffix(".tmp")
                with open(tmp_ep, "w", encoding="utf-8") as ef:
                    json.dump(empty_payload, ef, indent=2, ensure_ascii=False)
                _safe_replace(tmp_ep, empty_p)

            lines = [
                "# Multi-Vendor Lifecycle Scraping - Batch Execution & Knowledge Base Progress",
                "",
                f"> **Last Synchronized:** `{all_progress['updated_utc']}`",
                "",
                "| Vendor ID | Cycle | Discovered | Done | Pending | Batches Left | Harvested | Duplicates | Step4 Purged | LLM Rejected | EOL CSV | Active CSV | Progress % | Status | Data Status |",
                "|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
            ]
            for vid, vdata in sorted(all_progress["vendors"].items()):
                lines.append(
                    f"| `{vid}` | {vdata.get('cycle', 1)} | {vdata.get('total_discovered_units', 0)} | "
                    f"{vdata.get('completed_units', 0)} | {vdata.get('pending_units', 0)} | "
                    f"**{vdata.get('batches_remaining', 0)}** | {vdata.get('total_records_harvested', 0)} | "
                    f"{vdata.get('cross_entrypoint_duplicates_count', 0)} | "
                    f"{vdata.get('step4_purged_noise_count', 0)} | "
                    f"{vdata.get('llm_rejected_count', 0)} | "
                    f"{vdata.get('eol_records_count', 0)} | {vdata.get('active_records_count', 0)} | "
                    f"{vdata.get('progress_percent', 0.0)}% | `{vdata.get('status', 'IN_PROGRESS')}` | "
                    f"`{vdata.get('data_status', 'ACTIVE_DATA')}` |"
                )
            if zero_data_vendors:
                lines.append("")
                lines.append("### ⚠️ Flagged Vendors with Zero Data (NO_DATA)")
                lines.append("")
                lines.append("| Vendor ID | Status | Reason | Last Run |")
                lines.append("|:---|:---:|:---|:---:|")
                for zvid in sorted(zero_data_vendors):
                    zvdata = all_progress["vendors"][zvid]
                    lines.append(f"| `{zvid}` | `{zvdata.get('status')}` | No records extracted from configured endpoints | `{zvdata.get('last_run_utc')}` |")
            lines.append("")
            for target_md in (progress_dir / "batch_progress.md", output_dir / "batch_progress.md"):
                tmp_md = target_md.with_suffix(".tmp")
                with open(tmp_md, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                _safe_replace(tmp_md, target_md)

        except Exception as prog_err:
            logger.warning(f"[STATE] Error writing batch progress file: {prog_err}")

    @classmethod
    def load(
        cls, vendor_id: str, state_dir: Optional[Path] = None
    ) -> VendorRunState:
        """Load persistent state for a vendor, or create a new empty state if none exists."""
        target_dir = Path(state_dir) if state_dir else DEFAULT_STATE_DIR
        sanitized_id = "".join(
            c if c.isalnum() or c in ("-", "_") else "_"
            for c in vendor_id.lower()
        )
        file_path = target_dir / f"{sanitized_id}_state.json"

        if not file_path.exists():
            return cls(vendor_id=vendor_id, state_dir=target_dir)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            cycle = int(data.get("cycle", 1))
            kb = data.get("knowledge_base", {})
            pending = list(data.get("pending_queue", []))
            completed = set(data.get("completed_units", []))
            failed = set(data.get("failed_units", []))
            seen = set(data.get("seen_models", []))
            total_recs = int(data.get("total_records", 0))
            last_run = data.get("last_run_utc")
            last_batch = data.get("last_batch_info", {})
            meta = data.get("metadata", {})

            logger.info(
                f"[STATE] Loaded {vendor_id} state: Cycle {cycle}, KB: {len(kb)} units, "
                f"Pending: {len(pending)}, Completed: {len(completed)}, Seen Models: {len(seen)}"
            )
            return cls(
                vendor_id=vendor_id,
                state_dir=target_dir,
                cycle=cycle,
                knowledge_base=kb,
                pending_queue=pending,
                completed_units=completed,
                failed_units=failed,
                seen_models=seen,
                total_records=total_recs,
                last_run_utc=last_run,
                last_batch_info=last_batch,
                metadata=meta,
            )
        except Exception as e:
            logger.warning(
                f"[STATE] Could not read existing state file {file_path} ({e}), initializing fresh state."
            )
            return cls(vendor_id=vendor_id, state_dir=target_dir)

    @classmethod
    def purge(cls, vendor_id: str, state_dir: Optional[Path] = None) -> None:
        """Completely purges persistent run state, queue, empty-vendor flags, and audit records for a vendor."""
        target_dir = Path(state_dir) if state_dir else DEFAULT_STATE_DIR
        sanitized_id = "".join(
            c if c.isalnum() or c in ("-", "_") else "_"
            for c in vendor_id.lower()
        )
        file_path = target_dir / f"{sanitized_id}_state.json"
        if file_path.exists():
            try:
                file_path.unlink()
                logger.info(f"[STATE PURGE] Deleted vendor state file: {file_path}")
            except Exception as e:
                logger.warning(f"[STATE PURGE] Could not delete {file_path}: {e}")

        # Purge from batch_progress.json, empty_vendors.json, reconciliation_audit.json
        for base_p in (Path("artifacts"), Path("output")):
            prog_file = base_p / "batch_progress.json"
            if prog_file.exists():
                try:
                    with open(prog_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if "vendors" in data and vendor_id in data["vendors"]:
                        del data["vendors"][vendor_id]
                        with open(prog_file, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2)
                except Exception:
                    pass

            empty_file = base_p / "empty_vendors.json"
            if empty_file.exists():
                try:
                    with open(empty_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if "empty_vendors" in data:
                        data["empty_vendors"] = [v for v in data["empty_vendors"] if v.get("vendor_id") != vendor_id]
                        data["zero_data_count"] = len(data["empty_vendors"])
                        with open(empty_file, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2)
                except Exception:
                    pass

        rec_file = Path("output") / "reconciliation_audit.json"
        if rec_file.exists():
            try:
                with open(rec_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if vendor_id in data:
                    del data[vendor_id]
                    with open(rec_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
            except Exception:
                pass

    @classmethod
    def purge_all(cls, state_dir: Optional[Path] = None) -> None:
        """Purges all persistent vendor state files, batch progress, and empty-vendor tracking."""
        target_dir = Path(state_dir) if state_dir else DEFAULT_STATE_DIR
        if target_dir.exists():
            for f in target_dir.glob("*.json"):
                try:
                    f.unlink()
                except Exception:
                    pass
        now_str = datetime.now(timezone.utc).isoformat()
        for base_p in (Path("artifacts"), Path("output")):
            prog_file = base_p / "batch_progress.json"
            if prog_file.exists():
                try:
                    with open(prog_file, "w", encoding="utf-8") as out_f:
                        json.dump({"updated_utc": now_str, "vendors": {}}, out_f, indent=2)
                except Exception:
                    pass
            empty_file = base_p / "empty_vendors.json"
            if empty_file.exists():
                try:
                    with open(empty_file, "w", encoding="utf-8") as out_f:
                        json.dump({"updated_utc": now_str, "zero_data_count": 0, "empty_vendors": []}, out_f, indent=2)
                except Exception:
                    pass
            batch_md = base_p / "batch_progress.md"
            if batch_md.exists():
                try:
                    with open(batch_md, "w", encoding="utf-8") as out_f:
                        out_f.write(f"# Multi-Vendor Lifecycle Scraping - Batch Execution & Knowledge Base Progress\n\n> **Last Synchronized:** `{now_str}`\n\n")
                except Exception:
                    pass
