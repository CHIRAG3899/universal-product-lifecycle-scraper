"""
Dead Letter Queue (DLQ) & Diagnostic Logger.
Persists unrecoverable fetch errors, HTTP status errors, and malformed documents
to `artifacts/dlq.json` for forensic auditing and offline inspection.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scraper.security import safe_atomic_replace

logger = logging.getLogger("ai_scraper.dlq")


@dataclass
class DeadLetterItem:
    """Represents a failed crawl or extraction event captured in the DLQ."""
    url: str
    vendor_id: str
    error_type: str
    message: str
    status_code: Optional[int] = None
    timestamp_utc: str = ""
    retry_count: int = 0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeadLetterItem":
        return cls(
            url=data.get("url", ""),
            vendor_id=data.get("vendor_id", ""),
            error_type=data.get("error_type", "UnknownError"),
            message=data.get("message", ""),
            status_code=data.get("status_code"),
            timestamp_utc=data.get("timestamp_utc", ""),
            retry_count=int(data.get("retry_count", 0)),
            details=dict(data.get("details", {})),
        )


class DeadLetterQueue:
    """
    Append-only Dead Letter Queue manager for tracking failed requests.
    Persists forensic items to `artifacts/dlq.json`.
    """

    def __init__(self, dlq_path: Optional[Path] = None):
        if dlq_path is None:
            base_dir = Path(__file__).resolve().parent.parent
            self.dlq_file = base_dir / "artifacts" / "dlq.json"
        else:
            self.dlq_file = Path(dlq_path)

        self.dlq_file.parent.mkdir(parents=True, exist_ok=True)

    def record_failure(
        self,
        url: str,
        vendor_id: str,
        error_type: str,
        message: str,
        status_code: Optional[int] = None,
        retry_count: int = 0,
        details: Optional[Dict[str, Any]] = None,
    ) -> DeadLetterItem:
        """Records a new failure event in the dead letter queue."""
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        item = DeadLetterItem(
            url=url,
            vendor_id=vendor_id,
            error_type=error_type,
            message=message,
            status_code=status_code,
            timestamp_utc=now_utc,
            retry_count=retry_count,
            details=details or {},
        )

        items = self.get_failures()
        items.append(item)

        temp_file = self.dlq_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump([it.to_dict() for it in items], f, indent=2, ensure_ascii=False)
            safe_atomic_replace(temp_file, self.dlq_file)
            logger.warning(
                f"[DLQ] Logged unrecoverable failure for {url} ({error_type}: {message})"
            )
        except Exception as e:
            logger.error(f"[DLQ] Error writing dead letter queue: {e}")
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

        return item

    def get_failures(self, vendor_id: Optional[str] = None) -> List[DeadLetterItem]:
        """Retrieves all dead letter queue items, optionally filtered by vendor."""
        if not self.dlq_file.exists():
            return []

        try:
            with open(self.dlq_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, list):
                return []
            items = [DeadLetterItem.from_dict(d) for d in raw]
            if vendor_id:
                return [it for it in items if it.vendor_id.lower() == vendor_id.lower()]
            return items
        except Exception as e:
            logger.warning(f"[DLQ] Error reading dead letter queue: {e}")
            return []

    def clear(self) -> bool:
        """Empties the dead letter queue file."""
        try:
            if self.dlq_file.exists():
                self.dlq_file.unlink()
                return True
            return False
        except Exception as e:
            logger.warning(f"[DLQ] Error clearing dead letter queue: {e}")
            return False
