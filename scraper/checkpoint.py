"""
Checkpoint & Resume Engine for Enterprise Multi-Vendor Lifecycle Scraper.
Records failed fetches, interruption states, completed/pending URL queues,
and harvested record counts so interrupted or failed crawls can resume seamlessly.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ai_scraper.checkpoint")


@dataclass
class CheckpointState:
    """Represents the execution state of an interrupted or failed crawl."""
    run_id: str
    vendor_id: str
    timestamp_utc: str
    status: str = "failed"  # 'failed', 'interrupted', 'in_progress', 'completed'
    failed_url: Optional[str] = None
    error_message: Optional[str] = None
    completed_urls: List[str] = field(default_factory=list)
    pending_urls: List[str] = field(default_factory=list)
    completed_vendors: List[str] = field(default_factory=list)
    pending_vendors: List[str] = field(default_factory=list)
    harvested_records_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointState":
        return cls(
            run_id=data.get("run_id", ""),
            vendor_id=data.get("vendor_id", ""),
            timestamp_utc=data.get("timestamp_utc", ""),
            status=data.get("status", "failed"),
            failed_url=data.get("failed_url"),
            error_message=data.get("error_message"),
            completed_urls=list(data.get("completed_urls", [])),
            pending_urls=list(data.get("pending_urls", [])),
            completed_vendors=list(data.get("completed_vendors", [])),
            pending_vendors=list(data.get("pending_vendors", [])),
            harvested_records_count=int(data.get("harvested_records_count", 0)),
            metadata=dict(data.get("metadata", {})),
        )


class CheckpointManager:
    """
    Manages atomic persistence and retrieval of crawler checkpoints.
    Persists state in JSON format to enable resuming after network timeouts,
    HTTP 5xx server errors, rate limits, or process interruptions.
    """

    def __init__(self, checkpoint_path: Optional[Path] = None):
        if checkpoint_path is None:
            base_dir = Path(__file__).resolve().parent.parent
            self.checkpoint_file = base_dir / "artifacts" / "checkpoint.json"
        else:
            self.checkpoint_file = Path(checkpoint_path)

        self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(
        self,
        vendor_id: str,
        run_id: str,
        status: str = "failed",
        failed_url: Optional[str] = None,
        error_message: Optional[str] = None,
        completed_urls: Optional[List[str]] = None,
        pending_urls: Optional[List[str]] = None,
        completed_vendors: Optional[List[str]] = None,
        pending_vendors: Optional[List[str]] = None,
        harvested_records_count: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CheckpointState:
        """Atomically saves checkpoint state to disk."""
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        state = CheckpointState(
            run_id=run_id,
            vendor_id=vendor_id,
            timestamp_utc=now_utc,
            status=status,
            failed_url=failed_url,
            error_message=error_message,
            completed_urls=completed_urls or [],
            pending_urls=pending_urls or [],
            completed_vendors=completed_vendors or [],
            pending_vendors=pending_vendors or [],
            harvested_records_count=harvested_records_count,
            metadata=metadata or {},
        )

        temp_file = self.checkpoint_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
            temp_file.replace(self.checkpoint_file)
            logger.info(
                f"[CHECKPOINT] Saved checkpoint for vendor '{vendor_id}' (status={status}, "
                f"failed_url={failed_url}, pending={len(state.pending_urls)})"
            )
        except Exception as e:
            logger.error(f"[CHECKPOINT] Failed to write checkpoint: {e}")
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
            raise e

        return state

    def load_checkpoint(self, vendor_id: Optional[str] = None) -> Optional[CheckpointState]:
        """
        Loads the latest checkpoint from disk.
        If vendor_id is specified, returns the checkpoint only if it matches the vendor.
        """
        if not self.checkpoint_file.exists():
            return None

        try:
            with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            state = CheckpointState.from_dict(data)
            if vendor_id and state.vendor_id.lower() != vendor_id.lower():
                return None
            return state
        except Exception as e:
            logger.warning(f"[CHECKPOINT] Error loading checkpoint: {e}")
            return None

    def has_checkpoint(self, vendor_id: Optional[str] = None) -> bool:
        """Returns True if an active (non-completed) checkpoint exists."""
        state = self.load_checkpoint(vendor_id)
        if not state:
            return False
        return state.status in ("failed", "interrupted", "in_progress")

    def clear_checkpoint(self) -> bool:
        """Deletes active checkpoint once a run completes cleanly."""
        try:
            if self.checkpoint_file.exists():
                self.checkpoint_file.unlink()
                logger.info("[CHECKPOINT] Cleaned active checkpoint file.")
                return True
            return False
        except Exception as e:
            logger.warning(f"[CHECKPOINT] Could not remove checkpoint: {e}")
            return False
