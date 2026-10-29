"""
Incremental Delta Caching Engine.
Stores content hashes (SHA-256) and HTTP ETags for scraped web pages in `artifacts/cache/delta_cache.json`.
Allows the crawler to skip AI model extractions and heavy DOM parsing when vendor pages
have not changed since the last crawl.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("ai_scraper.delta_cache")


class DeltaCache:
    """
    Manages content-hash and ETag caching for incremental crawls.
    Detects whether page content has changed before triggering LLM extraction.
    """

    def __init__(self, cache_path: Optional[Path] = None):
        if cache_path is None:
            base_dir = Path(__file__).resolve().parent.parent
            self.cache_file = base_dir / "artifacts" / "cache" / "delta_cache.json"
        else:
            self.cache_file = Path(cache_path)

        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._entries: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if not self.cache_file.exists():
            return {}
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"[DELTA_CACHE] Error loading cache: {e}")
            return {}

    def _save(self) -> None:
        temp_file = self.cache_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, indent=2, ensure_ascii=False)
            temp_file.replace(self.cache_file)
        except Exception as e:
            logger.error(f"[DELTA_CACHE] Error writing delta cache: {e}")
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

    @staticmethod
    def compute_hash(content: str) -> str:
        """Computes deterministic SHA-256 hash of raw or normalized text content."""
        return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()

    def is_unchanged(self, url: str, content: str, etag: Optional[str] = None) -> bool:
        """
        Checks whether content matches previously cached SHA-256 hash or ETag.
        Returns True if content is identical (cache hit).
        """
        entry = self._entries.get(url)
        if not entry:
            return False

        current_hash = self.compute_hash(content)
        if entry.get("content_hash") == current_hash:
            return True

        if etag and entry.get("etag") and entry.get("etag") == etag:
            return True

        return False

    def update_entry(
        self,
        url: str,
        content: str,
        etag: Optional[str] = None,
        record_count: int = 0,
        vendor_id: str = "",
    ) -> None:
        """Updates or registers a URL in the delta cache."""
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        c_hash = self.compute_hash(content)
        self._entries[url] = {
            "content_hash": c_hash,
            "etag": etag,
            "record_count": record_count,
            "vendor_id": vendor_id,
            "last_scraped_utc": now_utc,
        }
        self._save()
        logger.debug(f"[DELTA_CACHE] Updated cache entry for {url} (hash={c_hash[:8]})")

    def get_entry(self, url: str) -> Optional[Dict[str, Any]]:
        """Retrieves cached metadata for a given URL."""
        return self._entries.get(url)

    def clear(self) -> bool:
        """Clears all delta cache entries."""
        self._entries = {}
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
                return True
            return False
        except Exception as e:
            logger.warning(f"[DELTA_CACHE] Error clearing cache: {e}")
            return False
