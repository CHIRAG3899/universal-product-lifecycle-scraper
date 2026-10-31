"""
Dead Letter Queue (DLQ), Diagnostic Logger & Crawl Failure Forensic Registry.
Persists unrecoverable fetch errors, HTTP status errors (3xx, 4xx, 5xx), timeouts,
and malformed documents to `artifacts/dlq.json` and `output/crawl_failures.json`
for deep forensic auditing, tracing, observability, and offline remediation.
"""

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from scraper.security import safe_atomic_replace

logger = logging.getLogger("ai_scraper.dlq")


def categorize_http_status(status_code: Optional[int], default: str = "FETCH_ERROR") -> str:
    """Categorizes HTTP status codes into standardized forensic error types."""
    if not status_code or not isinstance(status_code, int):
        return default
    if 300 <= status_code < 400:
        return f"HTTP_{status_code}_REDIRECT"
    if status_code == 400:
        return "HTTP_400_BAD_REQUEST"
    if status_code in (401, 403):
        return "HTTP_403_BOT_BLOCK"
    if status_code == 404:
        return "HTTP_404_NOT_FOUND"
    if status_code == 429:
        return "HTTP_429_RATE_LIMITED"
    if status_code == 500:
        return "HTTP_500_SERVER_ERROR"
    if status_code == 502:
        return "HTTP_502_BAD_GATEWAY"
    if status_code == 503:
        return "HTTP_503_SERVICE_UNAVAILABLE"
    if status_code == 504:
        return "HTTP_504_GATEWAY_TIMEOUT"
    if 400 <= status_code < 500:
        return f"HTTP_{status_code}_CLIENT_ERROR"
    if 500 <= status_code < 600:
        return f"HTTP_{status_code}_SERVER_ERROR"
    return default


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
    tier: str = "fast_http"
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
            tier=data.get("tier", "fast_http"),
            details=dict(data.get("details", {})),
        )


class DeadLetterQueue:
    """
    Thread-safe, append-only Dead Letter Queue manager for tracking failed requests,
    categorizing HTTP 3xx/4xx/5xx status codes, and exporting audit reports.
    """

    def __init__(self, dlq_path: Optional[Path] = None):
        if dlq_path is None:
            base_dir = Path(__file__).resolve().parent.parent
            self.dlq_file = base_dir / "artifacts" / "dlq.json"
        else:
            self.dlq_file = Path(dlq_path)

        self.dlq_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seen_keys: Set[Tuple[str, Optional[int]]] = set()

    def record_failure(
        self,
        url: str,
        vendor_id: str,
        error_type: str,
        message: str,
        status_code: Optional[int] = None,
        retry_count: int = 0,
        tier: str = "fast_http",
        details: Optional[Dict[str, Any]] = None,
    ) -> DeadLetterItem:
        """Records a new failure event in the dead letter queue (deduplicated by url and status code)."""
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        norm_type = error_type or categorize_http_status(status_code)

        if isinstance(url, dict):
            url_str = str(url.get("url") or url.get("website") or "unknown").strip()
        else:
            url_str = str(url or "unknown").strip()

        item = DeadLetterItem(
            url=url_str,
            vendor_id=vendor_id,
            error_type=norm_type,
            message=message,
            status_code=status_code,
            timestamp_utc=now_utc,
            retry_count=retry_count,
            tier=tier,
            details=details or {},
        )

        with self._lock:
            dedup_key = (url_str.lower(), status_code)
            if dedup_key in self._seen_keys:
                return item
            self._seen_keys.add(dedup_key)

            items = self.get_failures()
            items.append(item)

            temp_file = self.dlq_file.with_suffix(".tmp")
            try:
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump([it.to_dict() for it in items], f, indent=2, ensure_ascii=False)
                safe_atomic_replace(temp_file, self.dlq_file)
                logger.warning(
                    f"[DLQ] Logged crawl failure for {url} ({norm_type} [HTTP {status_code or 'N/A'}]: {message})"
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

    def get_summary(self) -> Dict[str, Any]:
        """Calculates structured forensic summary across all failed pages."""
        items = self.get_failures()
        by_status: Dict[str, int] = {}
        by_category: Dict[str, int] = {}
        by_vendor: Dict[str, int] = {}

        for it in items:
            code_key = str(it.status_code) if it.status_code is not None else "no_status"
            by_status[code_key] = by_status.get(code_key, 0) + 1

            cat_key = it.error_type or "UNKNOWN"
            by_category[cat_key] = by_category.get(cat_key, 0) + 1

            v_key = it.vendor_id or "unknown"
            by_vendor[v_key] = by_vendor.get(v_key, 0) + 1

        return {
            "total_failures": len(items),
            "by_status_code": by_status,
            "by_category": by_category,
            "by_vendor": by_vendor,
            "failures": [it.to_dict() for it in items]
        }

    def get_retryable_failures(self) -> List[DeadLetterItem]:
        """Filters failed items for transient / retryable issues (e.g. 429, 500, 502, 503, 504, 403, timeouts)."""
        items = self.get_failures()
        retryable_codes = {401, 403, 429, 500, 502, 503, 504}
        retryable_items = []
        for it in items:
            if it.status_code in retryable_codes:
                retryable_items.append(it)
            elif any(kw in it.error_type.lower() for kw in ("timeout", "connection", "rate_limit", "bot_block")):
                retryable_items.append(it)
        return retryable_items

    def export_failures_json(self, filepath: Path) -> Path:
        """Exports structured failure forensic map and summary to JSON file."""
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        summary = self.get_summary()
        payload = {
            "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "summary": {
                "total_failures": summary["total_failures"],
                "by_status_code": summary["by_status_code"],
                "by_category": summary["by_category"],
                "by_vendor": summary["by_vendor"]
            },
            "failures": summary["failures"]
        }
        temp_file = filepath.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        safe_atomic_replace(temp_file, filepath)
        return filepath

    def clear(self) -> bool:
        """Empties the dead letter queue file and clears in-memory state."""
        with self._lock:
            self._seen_keys.clear()
            try:
                if self.dlq_file.exists():
                    self.dlq_file.unlink()
                    return True
                return False
            except Exception as e:
                logger.warning(f"[DLQ] Error clearing dead letter queue: {e}")
                return False


_GLOBAL_DLQ: Optional[DeadLetterQueue] = None
_GLOBAL_DLQ_LOCK = threading.Lock()


def get_global_dlq() -> DeadLetterQueue:
    """Returns the process-wide DeadLetterQueue singleton for crawl failure forensic tracking."""
    global _GLOBAL_DLQ
    with _GLOBAL_DLQ_LOCK:
        if _GLOBAL_DLQ is None:
            _GLOBAL_DLQ = DeadLetterQueue()
        return _GLOBAL_DLQ
