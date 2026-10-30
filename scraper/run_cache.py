"""
Run-Level In-Memory & Session Cache System for Lifecycle Scraper.

Guarantees that identical web pages (HTML/DOM/Markdown) and technical files
(PDF notices, bulletins, datasheets) are never scraped, downloaded, or processed
more than once during a single execution run.

Saves network bandwidth, eliminates redundant browser headless crawls,
and prevents duplicate LLM token consumption.
"""

import copy
import logging
import threading
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from scraper.models import ProductRecord

logger = logging.getLogger("ai_scraper.run_cache")


def normalize_cache_url(url: Optional[str]) -> str:
    """
    Normalizes a URL to create a canonical cache key:
    1. Trims whitespace and strips hash fragments (#section).
    2. Lowercases scheme and netloc (domain).
    3. Sorts query parameters deterministically (?b=2&a=1 -> ?a=1&b=2).
    4. Normalizes trailing slashes for path hierarchies.
    """
    if not url or not isinstance(url, str):
        return ""

    s_url = url.strip()
    try:
        parsed = urllib.parse.urlsplit(s_url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()

        # Remove default ports
        if ":80" in netloc and scheme == "http":
            netloc = netloc.replace(":80", "")
        elif ":443" in netloc and scheme == "https":
            netloc = netloc.replace(":443", "")

        # Normalize path: remove trailing slash if path length > 1
        path = parsed.path
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]
        elif not path:
            path = "/"

        # Sort query parameters deterministically
        query_parts = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        sorted_query = urllib.parse.urlencode(sorted(query_parts)) if query_parts else ""

        # Reconstruct canonical URL (fragment is deliberately omitted)
        return urllib.parse.urlunsplit((scheme, netloc, path, sorted_query, ""))
    except Exception:
        # Fallback to trimmed URL without fragment
        return s_url.split("#")[0].strip()


class RunCache:
    """
    Session-level cache operating across the lifecycle pipeline execution.
    Maintains synchronized caches for:
    1. Crawled Pages: Raw and cleaned HTML/Markdown representations.
    2. Extracted Records: Parsed List[ProductRecord] per URL (bypasses redundant AI extractions).
    3. Downloaded Files: File bytes, extracted text, and PDF replacement maps.
    4. Visited URLs: Set of all visited endpoints to prevent redundant crawl queue loops.
    """

    def __init__(self, max_page_entries: int = 1000, max_file_entries: int = 250):
        self.max_page_entries = max_page_entries
        self.max_file_entries = max_file_entries
        self._lock = threading.RLock()

        # Page Caches
        self._page_crawl_cache: Dict[str, Dict[str, Any]] = {}
        self._page_records_cache: Dict[str, List[ProductRecord]] = {}

        # File & Document Caches
        self._file_bytes_cache: Dict[str, bytes] = {}
        self._file_text_cache: Dict[str, str] = {}
        self._pdf_replacements_cache: Dict[str, Dict[str, str]] = {}

        # Visited URL Tracker
        self._visited_urls: set = set()

        # Telemetry & Metrics
        self._page_hits = 0
        self._page_misses = 0
        self._file_hits = 0
        self._file_misses = 0
        self._extraction_hits = 0
        self._created_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # -------------------------------------------------------------------------
    # 1. URL Normalization Helper
    # -------------------------------------------------------------------------
    def normalize_url(self, url: Optional[str]) -> str:
        """Exposes canonical URL normalization."""
        return normalize_cache_url(url)

    # -------------------------------------------------------------------------
    # 2. Visited URL Tracking
    # -------------------------------------------------------------------------
    def is_visited(self, url: str) -> bool:
        """Returns True if the URL has already been visited or scraped during this run."""
        norm = self.normalize_url(url)
        with self._lock:
            return norm in self._visited_urls

    def mark_visited(self, url: str) -> None:
        """Marks a URL as visited in this run."""
        norm = self.normalize_url(url)
        if norm:
            with self._lock:
                self._visited_urls.add(norm)

    # -------------------------------------------------------------------------
    # 3. Page Crawl Cache (HTML, Markdown, Status Code)
    # -------------------------------------------------------------------------
    def has_crawled_page(self, url: str) -> bool:
        """Checks if page content was already crawled and cached during this run."""
        norm = self.normalize_url(url)
        with self._lock:
            return norm in self._page_crawl_cache

    def get_crawled_page(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves cached crawl payload for a given URL.
        Returns None on cache miss.
        """
        norm = self.normalize_url(url)
        with self._lock:
            if norm in self._page_crawl_cache:
                self._page_hits += 1
                logger.info(f"[RUN_CACHE HIT: PAGE CRAWL] Reusing cached DOM/Markdown for: {url}")
                return copy.deepcopy(self._page_crawl_cache[norm])
            self._page_misses += 1
            return None

    def set_crawled_page(self, url: str, data: Dict[str, Any]) -> None:
        """Stores crawled page output in the run cache."""
        norm = self.normalize_url(url)
        if not norm:
            return
        with self._lock:
            # FIFO eviction if exceeding capacity
            if len(self._page_crawl_cache) >= self.max_page_entries:
                first_key = next(iter(self._page_crawl_cache))
                del self._page_crawl_cache[first_key]

            self._page_crawl_cache[norm] = copy.deepcopy(data)
            self._visited_urls.add(norm)

    # -------------------------------------------------------------------------
    # 4. Page Extraction Cache (Parsed Product Records)
    # -------------------------------------------------------------------------
    def has_extracted_products(self, url: str) -> bool:
        """Checks if structured product records were already extracted for this URL."""
        norm = self.normalize_url(url)
        with self._lock:
            return norm in self._page_records_cache

    def get_extracted_products(self, url: str) -> Optional[List[ProductRecord]]:
        """
        Retrieves cached ProductRecord list for this URL.
        Bypasses redundant LLM API calls and heavy table parsing.
        """
        norm = self.normalize_url(url)
        with self._lock:
            if norm in self._page_records_cache:
                self._extraction_hits += 1
                cached = self._page_records_cache[norm]
                logger.info(
                    f"[RUN_CACHE HIT: AI EXTRACTION] Page '{url}' already extracted during this run. "
                    f"Reusing {len(cached)} cached product records (0 tokens consumed)."
                )
                return [p.model_copy(deep=True) for p in cached]
            return None

    def set_extracted_products(self, url: str, products: List[ProductRecord]) -> None:
        """Caches structured products extracted from this page URL."""
        norm = self.normalize_url(url)
        if not norm:
            return
        with self._lock:
            if len(self._page_records_cache) >= self.max_page_entries:
                first_key = next(iter(self._page_records_cache))
                del self._page_records_cache[first_key]

            self._page_records_cache[norm] = [p.model_copy(deep=True) for p in products]
            self._visited_urls.add(norm)

    # -------------------------------------------------------------------------
    # 5. File / Document Cache (PDFs, Bulletins, Datasheets)
    # -------------------------------------------------------------------------
    def has_file(self, file_url: str) -> bool:
        """Checks if a technical file or PDF has already been downloaded during this run."""
        norm = self.normalize_url(file_url)
        with self._lock:
            return norm in self._file_bytes_cache

    def get_file_bytes(self, file_url: str) -> Optional[bytes]:
        """Retrieves cached raw bytes for a file or document."""
        norm = self.normalize_url(file_url)
        with self._lock:
            if norm in self._file_bytes_cache:
                self._file_hits += 1
                logger.info(f"[RUN_CACHE HIT: FILE BYTES] Reusing downloaded file: {file_url} ({len(self._file_bytes_cache[norm])} bytes)")
                return self._file_bytes_cache[norm]
            self._file_misses += 1
            return None

    def set_file_bytes(self, file_url: str, content: bytes) -> None:
        """Stores downloaded file bytes in cache."""
        norm = self.normalize_url(file_url)
        if not norm or not content:
            return
        with self._lock:
            if len(self._file_bytes_cache) >= self.max_file_entries:
                first_key = next(iter(self._file_bytes_cache))
                del self._file_bytes_cache[first_key]
            self._file_bytes_cache[norm] = content

    def get_file_text(self, file_url: str) -> Optional[str]:
        """Retrieves cached text extracted from a file (e.g. PDF)."""
        norm = self.normalize_url(file_url)
        with self._lock:
            if norm in self._file_text_cache:
                self._file_hits += 1
                logger.info(f"[RUN_CACHE HIT: FILE TEXT] Reusing extracted text for: {file_url}")
                return self._file_text_cache[norm]
            return None

    def set_file_text(self, file_url: str, text: str) -> None:
        """Caches text extracted from a file."""
        norm = self.normalize_url(file_url)
        if not norm or not text:
            return
        with self._lock:
            if len(self._file_text_cache) >= self.max_file_entries:
                first_key = next(iter(self._file_text_cache))
                del self._file_text_cache[first_key]
            self._file_text_cache[norm] = text

    def has_pdf_replacements(self, pdf_url: str) -> bool:
        """Checks if a PDF replacement dictionary has already been computed."""
        norm = self.normalize_url(pdf_url)
        with self._lock:
            return norm in self._pdf_replacements_cache

    def get_pdf_replacements(self, pdf_url: str) -> Optional[Dict[str, str]]:
        """Retrieves cached replacement model map for a PDF notice."""
        norm = self.normalize_url(pdf_url)
        with self._lock:
            if norm in self._pdf_replacements_cache:
                self._file_hits += 1
                logger.info(f"[RUN_CACHE HIT: PDF REPLACEMENTS] Reusing replacement map for: {pdf_url}")
                return dict(self._pdf_replacements_cache[norm])
            return None

    def set_pdf_replacements(self, pdf_url: str, repl_map: Dict[str, str]) -> None:
        """Caches replacement model map for a PDF notice."""
        norm = self.normalize_url(pdf_url)
        if not norm:
            return
        with self._lock:
            if len(self._pdf_replacements_cache) >= self.max_file_entries:
                first_key = next(iter(self._pdf_replacements_cache))
                del self._pdf_replacements_cache[first_key]
            self._pdf_replacements_cache[norm] = dict(repl_map)

    # -------------------------------------------------------------------------
    # 6. Observability, Metrics & Diagnostics
    # -------------------------------------------------------------------------
    def get_stats(self) -> Dict[str, Any]:
        """Returns comprehensive telemetry on cache utilization and saved operations."""
        with self._lock:
            total_page_reqs = self._page_hits + self._page_misses
            page_hit_rate = (self._page_hits / total_page_reqs * 100.0) if total_page_reqs > 0 else 0.0

            total_file_reqs = self._file_hits + self._file_misses
            file_hit_rate = (self._file_hits / total_file_reqs * 100.0) if total_file_reqs > 0 else 0.0

            return {
                "created_at_utc": self._created_at_utc,
                "cached_pages_count": len(self._page_crawl_cache),
                "cached_extractions_count": len(self._page_records_cache),
                "cached_files_count": len(self._file_bytes_cache),
                "visited_urls_count": len(self._visited_urls),
                "page_crawl_hits": self._page_hits,
                "page_crawl_misses": self._page_misses,
                "page_hit_rate_pct": round(page_hit_rate, 1),
                "extraction_cache_hits": self._extraction_hits,
                "file_hits": self._file_hits,
                "file_misses": self._file_misses,
                "file_hit_rate_pct": round(file_hit_rate, 1),
                "total_redundant_operations_saved": self._page_hits + self._file_hits + self._extraction_hits,
            }

    def clear(self) -> None:
        """Resets all run-time caches."""
        with self._lock:
            self._page_crawl_cache.clear()
            self._page_records_cache.clear()
            self._file_bytes_cache.clear()
            self._file_text_cache.clear()
            self._pdf_replacements_cache.clear()
            self._visited_urls.clear()
            self._page_hits = 0
            self._page_misses = 0
            self._file_hits = 0
            self._file_misses = 0
            self._extraction_hits = 0
            logger.info("[RUN_CACHE] Successfully cleared run cache.")


# Global default run cache singleton
_GLOBAL_RUN_CACHE: Optional[RunCache] = None
_GLOBAL_LOCK = threading.Lock()


def get_global_run_cache() -> RunCache:
    """Returns or initializes the global run cache singleton."""
    global _GLOBAL_RUN_CACHE
    with _GLOBAL_LOCK:
        if _GLOBAL_RUN_CACHE is None:
            _GLOBAL_RUN_CACHE = RunCache()
        return _GLOBAL_RUN_CACHE


def reset_global_run_cache() -> None:
    """Resets the global run cache singleton for clean test or execution runs."""
    global _GLOBAL_RUN_CACHE
    with _GLOBAL_LOCK:
        if _GLOBAL_RUN_CACHE is not None:
            _GLOBAL_RUN_CACHE.clear()
        _GLOBAL_RUN_CACHE = None
