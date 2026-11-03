"""
Search Portal Scraping Strategy.

Executes query-driven lifecycle searches against enterprise search portals
(e.g., Rockwell Automation, Siemens Industry Mall, HP PartSurfer, Dell Support).
Supports dynamic runtime prefix discovery from sitemaps and seen models,
adaptive queue expansion from discovered replacement SKUs, CSS row extraction,
and persistent checkpointing with error-bound circuit breaking.
"""

from __future__ import annotations

import json
import logging
import re
import ssl
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Set

from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

from scraper.config import HEADLESS_BROWSER
from scraper.dlq import DeadLetterQueue
from scraper.models import ProductRecord
from scraper.state import VendorRunState
from scraper.strategies.base import BaseScrapingStrategy, sanitize_alias_text

logger = logging.getLogger("ai_scraper.strategies.search_portal")


def extract_model_family_prefix(model: str) -> Optional[str]:
    """
    Dynamically extracts a product model family prefix from a full SKU/model name.
    Examples:
      '1756-L85E' -> '1756'
      '5069-L306ER' -> '5069'
      '20-COMM-E' -> '20-'
      '22-COMM-E' -> '22-'
      '25-COMM-E2P' -> '25-'
      '2711P-T10C22D9P' -> '2711P'
      '140M-C2E-B25' -> '140M'
      '1492-SPM1D100' -> '1492'
      '194L-E20-1753' -> '194L'
      'PL-CCP153' -> 'PL-CCP'
      'MSSP-1234' -> 'MSSP'
      '1734-IB8S' -> '1734'
      '1783-EMS08T' -> '1783'
      '6ES7515-2AM01-0AB0' -> '6ES7'
      'WS-C2960X-24PS-L' -> 'WS-C2960'
    """
    if not model or not isinstance(model, str):
        return None
    clean = model.strip()
    if len(clean) < 2:
        return None

    # Compound alphanumeric prefix with dash (e.g., PL-CCP, WS-C, QS-10)
    m_alpha_dash = re.match(r"^([A-Za-z]{1,4}-[A-Za-z]{2,5})", clean)
    if m_alpha_dash:
        return m_alpha_dash.group(1).upper()

    # Number-dash prefix (e.g., 20-, 22-, 25-)
    m_hyphen = re.match(r"^([0-9]{2,3}-)", clean)
    if m_hyphen:
        return m_hyphen.group(1).upper()

    # Alphanumeric family before separator (e.g., 1756-, 140M-, MSSP-)
    m_sep = re.match(r"^([A-Za-z0-9]{2,7})[-_.]", clean)
    if m_sep:
        p = m_sep.group(1).upper()
        if p.isdigit() and len(p) >= 3:
            return p
        elif any(c.isdigit() for c in p) and len(p) >= 3:
            return p
        elif len(p) >= 2:
            return p

    # Leading digit or alpha-numeric block (e.g., 1756, 5069, 6ES7, C9300)
    m_lead = re.match(r"^([0-9]{3,5}|[A-Z]{2,5}\d{1,4})", clean, re.I)
    if m_lead:
        return m_lead.group(1).upper()

    return None


class SearchPortalStrategy(BaseScrapingStrategy):
    """
    Generic Strategy for Query-Driven Search Portals:
    1. Dynamically harvests model family prefixes on runtime from seen models and sitemaps.
    2. Adaptively enqueues new prefixes extracted from search result models & replacements.
    3. Iterates over uncompleted keywords querying url_template.
    4. Extracts structured rows with CSS selector mappings and sanitization.
    5. Deduplicates models across sessions and saves state checkpoints after each query.
    6. Stops gracefully only when consecutive errors exceed error threshold.
    """

    async def _discover_prefixes_from_sitemaps(
        self,
        crawler: Any,
        index_url: str,
        child_filter: str,
        prefix_regex: str,
        max_sitemaps: int = 0,
    ) -> Set[str]:
        """Harvests discrete model family prefixes from XML sitemap hierarchies."""
        discovered: Set[str] = set()
        run_cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=30000)

        try:
            logger.info(f"[SEARCH STRATEGY] Fetching sitemap index: {index_url}")
            res = await crawler.arun(url=index_url, config=run_cfg)
            if not res.success or not res.html:
                return discovered

            child_matches = re.findall(r"<loc>\s*([^\s<]+)\s*</loc>", res.html)
            child_urls = [u.strip() for u in child_matches if child_filter in u]
            if not child_urls:
                soup = BeautifulSoup(res.html, "html.parser")
                child_urls = [
                    t.get_text().strip()
                    for t in soup.find_all("loc")
                    if child_filter in t.get_text()
                ]

            target_children = child_urls[:max_sitemaps] if max_sitemaps > 0 else child_urls
            pattern = re.compile(prefix_regex, re.IGNORECASE)

            for c_url in target_children:
                c_res = await crawler.arun(url=c_url, config=run_cfg)
                if not c_res.success or not c_res.html:
                    continue
                loc_list = re.findall(r"<loc>\s*([^\s<]+)\s*</loc>", c_res.html)
                if not loc_list:
                    c_soup = BeautifulSoup(c_res.html, "html.parser")
                    loc_list = [loc.get_text().strip() for loc in c_soup.find_all("loc")]

                for loc_text in loc_list:
                    m = pattern.search(loc_text)
                    if m:
                        cat = m.group(1).strip()
                        dyn_p = extract_model_family_prefix(cat)
                        if dyn_p:
                            discovered.add(dyn_p)
                        parts = re.split(r"[-_.]", cat)
                        if parts and len(parts[0]) >= 2 and any(c.isdigit() for c in parts[0]):
                            discovered.add(parts[0].upper())
        except Exception as e:
            logger.warning(f"[SEARCH STRATEGY] Sitemap prefix discovery notice: {e}")

        return discovered

    async def _execute_api_search(
        self,
        entry_point: Dict[str, Any],
        vendor_cfg: Dict[str, Any],
        state: VendorRunState,
        dlq: Optional[DeadLetterQueue] = None,
        max_pages: int = 0,
        batch_size: Optional[int] = None,
        all_batches: bool = False,
    ) -> List[ProductRecord]:
        """Directly query the backend search API without headless browser overhead."""
        api_config = entry_point["api_config"]
        base_api_url = api_config.get("url", "")
        headers = dict(api_config.get("headers", {}))
        if "User-Agent" not in headers:
            headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        tab = api_config.get("tab", "lifecycle")
        page_size = int(api_config.get("page_size", 200))
        max_offset = int(api_config.get("max_offset", 10000))
        field_map = api_config.get("field_map", {})
        vendor_name = vendor_cfg.get("name", "Unknown Vendor")
        vendor_id = vendor_cfg.get("id", "vendor")
        category_name = entry_point.get("category", vendor_cfg.get("sector", "Industrial Automation"))

        from scraper.models import is_valid_replacement_model, parse_to_utc_iso
        from scraper.vendors import normalize_stage_name

        ssl_ctx = ssl._create_unverified_context()

        # Dynamic prefix collection
        keywords: Set[str] = set()
        for seen_m in state.seen_models:
            p = extract_model_family_prefix(seen_m)
            if p:
                keywords.add(p)
        for p in state.discovered_prefixes:
            if p:
                keywords.add(p)
        for k in entry_point.get("keywords", []):
            if k and isinstance(k, str) and k.strip():
                keywords.add(k.strip())

        pending_queue, _ = state.sync_knowledge_base(sorted(list(keywords)))
        print(f"[*] [API SEARCH SYNC] Total Units in KB: {len(state.knowledge_base)}, "
              f"Pending in Cycle {state.cycle}: {len(state.pending_queue)}, Completed: {len(state.completed_units)}")

        records: List[ProductRecord] = []
        consecutive_errors = 0
        batch_iteration = 0

        while state.pending_queue:
            batch_iteration += 1
            batch = state.get_next_batch(capability="search_portal", batch_size=batch_size or 50)
            if not batch:
                break

            print(f"\n[*] [API SEARCH BATCH {batch_iteration}] Running batch of {len(batch)} prefixes "
                  f"(Queue Remaining: {len(state.pending_queue)}, Cycle: {state.cycle}): {batch[:5]}...")

            failed_in_batch: List[str] = []
            batch_records: List[ProductRecord] = []
            batch_discovered_prefixes: Set[str] = set()

            for idx, kw in enumerate(batch, 1):
                if max_pages > 0 and (len(records) + len(batch_records)) >= max_pages:
                    print(f"[API SEARCH] Reached configured max_pages limit ({max_pages}).")
                    break

                clean_kw = kw.strip()
                if clean_kw.startswith("http://") or clean_kw.startswith("https://"):
                    continue

                print(f"  [{idx}/{len(batch)}] Querying API for family '{clean_kw}'...")
                offset = 0
                kw_records_count = 0

                while offset < max_offset:
                    if max_pages > 0 and (len(records) + len(batch_records)) >= max_pages:
                        break

                    params = {
                        api_config.get("query_param", "query"): clean_kw,
                        api_config.get("tab_param", "tab"): tab,
                        api_config.get("from_param", "from"): offset,
                        api_config.get("size_param", "size"): page_size,
                        "locale": api_config.get("locale", "en-US"),
                    }
                    req_url = f"{base_api_url}?{urllib.parse.urlencode(params)}"

                    try:
                        req = urllib.request.Request(req_url, headers=headers)
                        with urllib.request.urlopen(req, context=ssl_ctx, timeout=20) as resp:
                            res_data = json.loads(resp.read().decode("utf-8"))

                        docs = res_data.get("docs", [])
                        total_available = res_data.get("total", 0)

                        if not docs:
                            break

                        consecutive_errors = 0
                        for d in docs:
                            if not isinstance(d, dict):
                                continue

                            c_num = d.get(field_map.get("model", "catalogNumber"))
                            p_name = d.get(field_map.get("alias", "description")) or d.get("title")
                            st_val = d.get(field_map.get("status", "productLifeCycleStatus"))
                            dt_val = d.get(field_map.get("date", "discontinuedDate"))
                            rp_val = d.get(field_map.get("replacement", "replacementText"))
                            rc_val = d.get(field_map.get("replacement_category", "replacementCategory"))
                            pdp_url = d.get(field_map.get("url", "url")) or req_url

                            if not c_num:
                                continue

                            clean_rp = None
                            for cand in (rp_val, rc_val):
                                if cand and is_valid_replacement_model(str(cand)):
                                    clean_rp = str(cand)
                                    break

                            clean_c_num = sanitize_alias_text(str(c_num)) or ""
                            norm_st = normalize_stage_name(str(st_val or ""))
                            has_date = bool(parse_to_utc_iso(dt_val))

                            if state.is_model_seen(clean_c_num) and norm_st == "Active" and not has_date:
                                continue

                            rec = self.create_sanitized_record(
                                vendor_name=vendor_name,
                                raw_model=str(c_num),
                                raw_alias=str(p_name) if p_name else None,
                                raw_status=str(st_val or "Active"),
                                raw_date=str(dt_val) if dt_val else None,
                                source_url=str(pdp_url),
                                category=category_name,
                                raw_replacement=clean_rp,
                            )
                            if rec:
                                batch_records.append(rec)
                                state.record_model(rec.model_name)
                                kw_records_count += 1

                                for cand_prefix in (rec.model_name, rec.replacement):
                                    if cand_prefix:
                                        new_p = extract_model_family_prefix(cand_prefix)
                                        if new_p and not state.is_unit_completed(new_p):
                                            batch_discovered_prefixes.add(new_p)
                                            state.record_discovered_prefix(new_p)

                        offset += len(docs)
                        if offset >= total_available or len(docs) < page_size:
                            break

                    except Exception as err:
                        consecutive_errors += 1
                        failed_in_batch.append(kw)
                        logger.warning(f"  [!] Error querying API for family '{kw}' offset {offset}: {err}")
                        if dlq:
                            dlq.record_failure(
                                url=req_url,
                                vendor_id=vendor_id,
                                error_type=type(err).__name__,
                                message=str(err),
                                details={"keyword": kw, "offset": offset},
                            )
                        break

                logger.info(f"    [+] API Family '{kw}': Extracted {kw_records_count} records.")

            if batch_discovered_prefixes:
                state.sync_knowledge_base(sorted(list(batch_discovered_prefixes)))

            state.mark_batch_completed(batch, records_count=len(batch_records), failed_units=failed_in_batch)
            records.extend(batch_records)
            print(f"[+] [API BATCH {batch_iteration} COMPLETE] Finished {len(batch)} prefixes. "
                  f"Harvested {len(batch_records)} records. Total records so far: {len(records)}.")

            if not all_batches:
                break

        state.total_records += len(records)
        state.save()
        logger.info(f"[API SEARCH STRATEGY] Finished for {vendor_name}: {len(records)} products harvested.")
        return records

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
        if entry_point.get("api_config"):
            return await self._execute_api_search(
                entry_point=entry_point,
                vendor_cfg=vendor_cfg,
                state=state,
                dlq=dlq,
                max_pages=max_pages,
                batch_size=batch_size,
                all_batches=all_batches,
            )
        vendor_name = vendor_cfg.get("name", "Unknown Vendor")
        vendor_id = vendor_cfg.get("id", "vendor")
        url_template = entry_point.get("url_template") or entry_point.get("url", "")
        if "{keyword}" not in url_template and "{prefix}" not in url_template:
            sep = "&" if "?" in url_template else "?"
            url_template = f"{url_template}{sep}keyword={{keyword}}"

        # -------------------------------------------------------------------------
        # 1. DYNAMIC RUNTIME PREFIX DISCOVERY
        # -------------------------------------------------------------------------
        keywords: Set[str] = set()

        # A. Harvest dynamically from existing seen models in persistent memory
        for seen_m in state.seen_models:
            p = extract_model_family_prefix(seen_m)
            if p:
                keywords.add(p)

        # B. Harvest from state metadata if previously discovered
        for p in state.discovered_prefixes:
            if p:
                keywords.add(p)

        # C. Include any explicitly configured seed keywords (if any provided)
        for k in entry_point.get("keywords", []):
            if k and isinstance(k, str) and k.strip():
                keywords.add(k.strip())

        # D. Harvest from sitemaps (if configured or present in vendor entry points)
        sitemap_cfg = entry_point.get("sitemap_discovery")
        if not sitemap_cfg:
            for ep_item in vendor_cfg.get("entry_points", []):
                ep_u = ep_item.get("url", "")
                if "sitemap" in ep_u.lower() or ep_item.get("crawler_type") in ("sitemap", "sitemap_index"):
                    sitemap_cfg = {
                        "index_url": ep_u,
                        "child_filter": "sitemap",
                        "prefix_regex": r"details\.([A-Za-z0-9\-_.]+)\.html",
                    }
                    break

        selectors = entry_point.get("selectors", {})
        row_selector = selectors.get("row", ".lifecycle-row-inner, .lifecycle-row, tr")
        wait_selector = selectors.get("wait_for", row_selector)
        category_name = entry_point.get("category", vendor_cfg.get("sector", "Industrial Automation"))

        browser_cfg = BrowserConfig(headless=HEADLESS_BROWSER, verbose=False)
        delay_sec = float(entry_point.get("delay", 3.0))
        run_cfg = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            wait_for=f"css:{wait_selector}" if not wait_selector.startswith("css:") else wait_selector,
            page_timeout=35000,
            delay_before_return_html=delay_sec,
        )

        records: List[ProductRecord] = []
        consecutive_errors = 0

        async with AsyncWebCrawler(config=browser_cfg) as web_crawler:
            need_sitemap_discovery = (
                len(keywords) < 5
                or (sitemap_cfg and bool(sitemap_cfg.get("force_discovery", False)))
            )
            if sitemap_cfg and isinstance(sitemap_cfg, dict) and need_sitemap_discovery:
                sm_index = sitemap_cfg.get("index_url", "")
                sm_filter = sitemap_cfg.get("child_filter", "sitemap")
                sm_regex = sitemap_cfg.get("prefix_regex", r"([A-Za-z0-9\-_.]+)")
                max_sm = int(sitemap_cfg.get("max_sitemaps", 0))
                if sm_index:
                    sm_prefixes = await self._discover_prefixes_from_sitemaps(
                        crawler=web_crawler,
                        index_url=sm_index,
                        child_filter=sm_filter,
                        prefix_regex=sm_regex,
                        max_sitemaps=max_sm,
                    )
                    keywords.update(sm_prefixes)
                    for sm_p in sm_prefixes:
                        state.record_discovered_prefix(sm_p)

            # ---------------------------------------------------------------------
            # 2. KNOWLEDGE BASE SYNCHRONIZATION & CAPABILITY BATCHING
            # ---------------------------------------------------------------------
            pending_queue, is_new_cycle = state.sync_knowledge_base(sorted(list(keywords)))
            print(f"[*] [KNOWLEDGE BASE SYNC] Total Units in KB: {len(state.knowledge_base)}, "
                  f"Pending in Cycle {state.cycle}: {len(state.pending_queue)}, Completed: {len(state.completed_units)}")

            # Process in capability batches (run one batch now, or all if all_batches=True)
            batch_iteration = 0
            while state.pending_queue:
                batch_iteration += 1
                batch = state.get_next_batch(capability="search_portal", batch_size=batch_size)
                if not batch:
                    break

                print(f"\n[*] [SEARCH BATCH {batch_iteration}] Running batch of {len(batch)} prefixes "
                      f"(Queue Remaining: {len(state.pending_queue)}, Cycle: {state.cycle}): {batch[:5]}...")

                failed_in_batch: List[str] = []
                batch_records: List[ProductRecord] = []

                for idx, kw in enumerate(batch, 1):
                    if max_pages > 0 and len(records) >= max_pages:
                        print(f"[SEARCH STRATEGY] Reached configured max_pages limit ({max_pages}).")
                        break

                    clean_kw = kw.strip()
                    if clean_kw.startswith("http://") or clean_kw.startswith("https://"):
                        logger.debug(f"[SEARCH STRATEGY] Skipping URL entry in keyword batch: {kw}")
                        continue

                    query_url = url_template.replace("{keyword}", clean_kw).replace("{prefix}", clean_kw)
                    print(f"  [{idx}/{len(batch)}] Querying portal for family '{clean_kw}'...")

                    try:
                        res = await web_crawler.arun(url=query_url, config=run_cfg)
                        if not res.success or not res.html:
                            consecutive_errors += 1
                            failed_in_batch.append(kw)
                            logger.warning(
                                f"  [!] Fetch failed for keyword '{kw}' "
                                f"(Consecutive errors: {consecutive_errors}/{self.max_consecutive_errors})"
                            )
                            if dlq:
                                dlq.record_failure(
                                    url=query_url,
                                    vendor_id=vendor_id,
                                    error_type="FetchFailed",
                                    message=res.error_message or "Empty response",
                                    details={"keyword": kw},
                                )
                            if consecutive_errors >= self.max_consecutive_errors:
                                logger.error(
                                    f"  [CIRCUIT BREAKER] Reached {self.max_consecutive_errors} consecutive fetch errors. Halting batch."
                                )
                                break
                            continue

                        consecutive_errors = 0
                        soup = BeautifulSoup(res.html, "html.parser")
                        rows = soup.select(row_selector)
                        extracted_for_kw = 0

                        for r in rows:
                            def _sel_text(sel_key: str, default_class: str) -> str:
                                sel = selectors.get(sel_key, default_class)
                                el = r.select_one(sel) if sel else None
                                return el.get_text(strip=True) if el else ""

                            c_num = _sel_text("model_name", ".catalog-number")
                            p_name = _sel_text("aliases", ".product-name")
                            st_val = _sel_text("status", ".lifecycle-status")
                            dt_val = _sel_text("stage_date_utc", ".discontinued-date")
                            rc_val = _sel_text("replacement_category", ".replacement-category")

                            rp_el = r.select_one(selectors.get("replacement", ".replacement, .replacement-link, .replacement-category"))
                            rp_val = ""
                            if rp_el:
                                a_link = rp_el.find("a")
                                if a_link:
                                    rp_val = a_link.get_text(strip=True)
                                    href_val = str(a_link.get("href") or "")
                                    if not rp_val and href_val:
                                        m_href = re.search(r"details\.([A-Za-z0-9\-_.]+)\.html", href_val)
                                        if m_href:
                                            rp_val = m_href.group(1)
                                if not rp_val:
                                    rp_val = rp_el.get_text(strip=True)

                            # Strict replacement validation: strictly reject boilerplate phrases like
                            # 'No planned RA replacement', 'CONTACT REPAIR & REPLACEMENT', 'NOT APPLICABLE', etc.
                            from scraper.models import is_valid_replacement_model, parse_to_utc_iso
                            from scraper.vendors import normalize_stage_name
                            clean_rp = None
                            for cand in (rp_val, rc_val):
                                if cand and is_valid_replacement_model(cand):
                                    clean_rp = cand
                                    break
                            rp_val = clean_rp or ""

                            if not c_num:
                                divs = [d.get_text(strip=True) for d in r.find_all("div") if d.get_text(strip=True)]
                                if len(divs) >= 4:
                                    c_num, p_name, st_val, dt_val = divs[0], divs[1], divs[2], divs[3]
                                    if len(divs) >= 5:
                                        rc_val = divs[4]
                                    if len(divs) >= 6:
                                        if is_valid_replacement_model(divs[5]):
                                            rp_val = divs[5]

                            if not c_num:
                                continue

                            clean_c_num = sanitize_alias_text(c_num) or ""
                            norm_st = normalize_stage_name(st_val or "")
                            has_date = bool(parse_to_utc_iso(dt_val))
                            # Never skip authentic milestone or dated records even if model was seen as active
                            if state.is_model_seen(clean_c_num) and norm_st == "Active" and not has_date:
                                continue

                            rec = self.create_sanitized_record(
                                vendor_name=vendor_name,
                                raw_model=c_num,
                                raw_alias=p_name,
                                raw_status=st_val,
                                raw_date=dt_val,
                                source_url=query_url,
                                category=category_name,
                                raw_replacement=rp_val,
                                raw_replacement_category=rc_val,
                            )
                            if rec:
                                batch_records.append(rec)
                                state.record_model(rec.model_name)
                                extracted_for_kw += 1

                                # Dynamic discovery of new prefixes from models or replacements
                                for candidate in (rec.model_name, rec.replacement):
                                    if candidate:
                                        new_p = extract_model_family_prefix(candidate)
                                        if new_p and not state.is_unit_completed(new_p):
                                            state.sync_knowledge_base([new_p])
                                            state.record_discovered_prefix(new_p)

                        logger.info(f"    [+] Family '{kw}': Extracted {extracted_for_kw} records.")

                    except Exception as kw_err:
                        consecutive_errors += 1
                        failed_in_batch.append(kw)
                        logger.error(f"  [!] Error on search query '{kw}': {kw_err}")
                        if dlq:
                            dlq.record_failure(
                                url=query_url,
                                vendor_id=vendor_id,
                                error_type=type(kw_err).__name__,
                                message=str(kw_err),
                                details={"keyword": kw},
                            )
                        if consecutive_errors >= self.max_consecutive_errors:
                            logger.error(f"  [CIRCUIT BREAKER] Reached {self.max_consecutive_errors} consecutive errors. Halting batch.")
                            break

                # Mark batch completed in knowledge base & state
                state.mark_batch_completed(batch, records_count=len(batch_records), failed_units=failed_in_batch)
                records.extend(batch_records)

                print(f"[+] [BATCH {batch_iteration} COMPLETE] Finished {len(batch)} prefixes. "
                      f"Harvested {len(batch_records)} records. {len(state.pending_queue)} remaining in queue.")

                if not all_batches:
                    print("[*] Single-batch run mode complete. Next run will process the subsequent batch.")
                    break

        state.total_records += len(records)
        state.save()
        logger.info(
            f"[SEARCH STRATEGY] Execution finished for {vendor_name}: {len(records)} products harvested."
        )
        return records
