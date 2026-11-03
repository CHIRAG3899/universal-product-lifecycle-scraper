"""
REST and JSON API Scraping Strategy.

Consumes structured JSON and REST lifecycle endpoints (e.g., Microsoft Learn
Lifecycle API, Red Hat Product Lifecycle feeds, public vendor JSON catalogs).
Provides deterministic, zero-scraping-overhead extraction with native schema validation.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any, Dict, List, Optional

from scraper.dlq import DeadLetterQueue
from scraper.models import ProductRecord
from scraper.state import VendorRunState
from scraper.strategies.base import BaseScrapingStrategy

logger = logging.getLogger("ai_scraper.strategies.rest_api")


class RestApiStrategy(BaseScrapingStrategy):
    """
    Generic Strategy for JSON / REST Endpoints:
    1. Fetches JSON payloads from authenticated or public lifecycle endpoints.
    2. Navigates JSON paths (e.g., items, products, results).
    3. Normalizes and validates records into uniform ProductRecord format.
    4. Automatically records progress in VendorRunState.
    """

    async def execute(
        self,
        entry_point: Dict[str, Any],
        vendor_cfg: Dict[str, Any],
        crawler: Any,
        state: VendorRunState,
        dlq: Optional[DeadLetterQueue] = None,
        max_pages: int = 0,
        batch_size: Optional[int] = None,
        all_batches: bool = False,
    ) -> List[ProductRecord]:
        vendor_name = vendor_cfg.get("name", "Unknown Vendor")
        vendor_id = vendor_cfg.get("id", "vendor")
        url = str(entry_point.get("url", "")).strip()
        if not url:
            return []

        if state.is_unit_completed(url):
            logger.info(f"[REST API] Skipping previously completed endpoint: {url}")
            return []

        field_map = entry_point.get("field_map", {})
        category_name = entry_point.get("category", vendor_cfg.get("sector", "IT"))
        records: List[ProductRecord] = []

        try:
            logger.info(f"[*] [REST API] Ingesting lifecycle data from {url}")
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "UniversalLifecycleScraper/2.0 (Enterprise Automation)"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            items: List[Dict[str, Any]] = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                for k in ("items", "products", "results", "data"):
                    if isinstance(data.get(k), list):
                        items = data[k]
                        break

            for item in items:
                if not isinstance(item, dict):
                    continue
                raw_m = str(item.get(field_map.get("model", "modelName")) or item.get("name") or "")
                raw_a = str(item.get(field_map.get("aliases", "productName")) or item.get("description") or "")
                raw_s = str(item.get(field_map.get("status", "lifecycleStatus")) or item.get("status") or "")
                raw_d = str(item.get(field_map.get("date", "endDate")) or item.get("eosDate") or "")
                raw_r = str(item.get(field_map.get("replacement", "replacementModel")) or "")

                if not raw_m:
                    continue

                if state.is_model_seen(raw_m):
                    continue

                rec = self.create_sanitized_record(
                    vendor_name=vendor_name,
                    raw_model=raw_m,
                    raw_alias=raw_a or None,
                    raw_status=raw_s or "Active",
                    raw_date=raw_d or None,
                    source_url=url,
                    category=category_name,
                    raw_replacement=raw_r or None,
                )
                if rec:
                    records.append(rec)
                    state.record_model(rec.model_name)

            state.mark_unit_completed(url)
            state.total_records += len(records)
            state.save()
            logger.info(f"[+] [REST API] Harvested {len(records)} products from {url}")

        except Exception as e:
            logger.error(f"[!] [REST API] Error querying {url}: {e}")
            if dlq:
                dlq.record_failure(
                    url=url,
                    vendor_id=vendor_id,
                    error_type=type(e).__name__,
                    message=str(e),
                )

        return records
