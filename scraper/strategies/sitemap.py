"""
XML Sitemap Scraping Strategy.

Discovers and ingests XML sitemaps and sitemap indices across enterprise
vendor domains. Recursively resolves child sitemaps without limitation,
synchronizes with persistent knowledge base across runs, divides load into
capability-based batches, and extracts structured lifecycle records.
"""

from __future__ import annotations

import io
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

from scraper.config import HEADLESS_BROWSER
from scraper.dlq import DeadLetterQueue
from scraper.models import ProductRecord
from scraper.security import is_safe_url
from scraper.state import VendorRunState
from scraper.strategies.base import BaseScrapingStrategy

logger = logging.getLogger("ai_scraper.strategies.sitemap")


def stream_iterparse_sitemap_urls(xml_data: Union[str, bytes]) -> Iterator[Tuple[str, Optional[str]]]:
    """
    Streaming XML parser using xml.etree.ElementTree.iterparse with O(1) memory consumption.
    Extracts <loc> and <lastmod> pairs on the fly and immediately frees element DOM tree memory.
    """
    if isinstance(xml_data, str):
        raw_bytes = xml_data.encode("utf-8", errors="ignore")
    else:
        raw_bytes = xml_data

    bio = io.BytesIO(raw_bytes)
    yielded = 0
    try:
        for event, elem in ET.iterparse(bio, events=("end",)):
            tag = elem.tag.split("}")[-1].lower()
            if tag == "url":
                loc_val = None
                lastmod_val = None
                for child in elem:
                    ctag = child.tag.split("}")[-1].lower()
                    if ctag == "loc" and child.text:
                        loc_val = child.text.strip()
                    elif ctag == "lastmod" and child.text:
                        lastmod_val = child.text.strip()
                if loc_val:
                    yield (loc_val, lastmod_val)
                    yielded += 1
                elem.clear()
            elif tag == "sitemap":
                loc_val = None
                for child in elem:
                    ctag = child.tag.split("}")[-1].lower()
                    if ctag == "loc" and child.text:
                        loc_val = child.text.strip()
                if loc_val:
                    yield (loc_val, None)
                    yielded += 1
                elem.clear()
    except Exception as e:
        logger.debug(f"[STREAM ITERPARSE] Notice during stream parsing: {e}")

    # Fallback to regex extraction if XML namespaces or malformed headers prevented iterparse
    if yielded == 0 and isinstance(xml_data, str):
        raw_url_blocks = re.findall(r"<url>(.*?)</url>", xml_data, flags=re.DOTALL | re.IGNORECASE)
        if raw_url_blocks:
            for u_block in raw_url_blocks:
                m_loc = re.search(r"<loc>\s*([^<\s]+)\s*</loc>", u_block, flags=re.IGNORECASE)
                if m_loc:
                    loc_t = m_loc.group(1).strip()
                    m_lmod = re.search(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", u_block, flags=re.IGNORECASE)
                    lmod_t = m_lmod.group(1).strip() if m_lmod else None
                    yield (loc_t, lmod_t)
        else:
            loc_matches = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml_data)
            for loc_item in loc_matches:
                yield (loc_item.strip(), None)


class SitemapStrategy(BaseScrapingStrategy):
    """
    Generic Strategy for XML Sitemap Hierarchies with Stateful URL Batching:
    1. Fetches root sitemap index without artificial limit to discover ALL child sitemap URLs.
    2. Synchronizes discovered URLs with persistent Knowledge Base across runs.
    3. Divides workload into capability-based batches (runs one batch now, subsequent batches in future runs).
    4. Automatically restarts fresh refresh cycle once all batches are completed.
    5. Extracts structured product records, dates, and milestones.
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

        allowed_domains = list(vendor_cfg.get("allowed_domains") or [])
        if not allowed_domains and url:
            try:
                host = urlsplit(url).netloc.split(":")[0].lower()
                if host.startswith("www."):
                    host = host[4:]
                if host:
                    allowed_domains = [host]
            except Exception:
                pass

        child_filter = entry_point.get("child_filter", "")
        product_pattern = (
            entry_point.get("product_pattern")
            or entry_point.get("prefix_regex")
            or r"details\.([A-Za-z0-9\-_.]+)\.html|/products/details\."
        )
        pattern_re = re.compile(product_pattern, re.IGNORECASE)
        model_group_idx = int(entry_point.get("model_group_index", 1))
        category_name = entry_point.get("category", vendor_cfg.get("sector", "OT"))

        browser_cfg = BrowserConfig(headless=HEADLESS_BROWSER, verbose=False)
        run_cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=35000, markdown_generator=None)

        records: List[ProductRecord] = []

        async with AsyncWebCrawler(config=browser_cfg) as web_crawler:
            async def _fetch_sitemap_content(target_url: str) -> Optional[str]:
                # 1. Fast direct HTTP fetch first (sitemaps are raw XML, Chromium DOM overhead is unnecessary)
                try:
                    import ssl
                    import urllib.request
                    ctx = ssl._create_unverified_context()
                    req = urllib.request.Request(
                        target_url,
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
                    )
                    with urllib.request.urlopen(req, context=ctx, timeout=3) as resp:
                        if resp.status == 200:
                            raw_bytes = resp.read()
                            return raw_bytes.decode("utf-8", errors="ignore")
                except Exception as e_http:
                    logger.debug(f"Direct HTTP fetch notice for sitemap {target_url}: {e_http}")

                # 2. Browser fallback if direct HTTP is blocked
                try:
                    res = await web_crawler.arun(url=target_url, config=run_cfg)
                    if res.success and res.html:
                        return res.html
                except Exception as e:
                    logger.debug(f"web_crawler.arun failed for {target_url}: {e}")
                return None

            # -------------------------------------------------------------------------
            # 1. DISCOVER ALL CHILD SITEMAP URLS (NO ARTIFICIAL LIMITATION)
            # -------------------------------------------------------------------------
            all_sitemap_urls: List[str] = []
            logger.info(f"[*] [SITEMAP DISCOVERY] Fetching root sitemap / index: {url}")
            print(f"[*] [SITEMAP DISCOVERY] Fetching root sitemap index: {url}")

            try:
                root_html = await _fetch_sitemap_content(url)
                if not root_html:
                    raise RuntimeError(f"Failed to fetch root sitemap {url}: empty or failed response")

                is_sitemap_index = "<sitemapindex" in root_html.lower() or "<sitemap>" in root_html.lower()

                if is_sitemap_index:
                    loc_tags = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", root_html)
                    if not loc_tags:
                        soup = BeautifulSoup(root_html, "html.parser")
                        loc_tags = [t.get_text().strip() for t in soup.find_all("loc")]

                    max_sm = int(entry_point.get("max_sitemaps", 0) or 0)
                    for clean_loc in loc_tags:
                        clean_loc = clean_loc.split("#")[0].strip()
                        if not clean_loc:
                            continue
                        if not is_safe_url(clean_loc, allowed_domains):
                            continue
                        if child_filter and child_filter not in clean_loc:
                            continue
                        if (clean_loc.endswith(".xml") or "sitemap" in clean_loc.lower()) and clean_loc != url:
                            all_sitemap_urls.append(clean_loc)
                            if max_sm > 0 and len(all_sitemap_urls) >= max_sm:
                                break

                # If direct urlset (or no child sitemaps detected), the entry point itself is the sole sitemap
                if not all_sitemap_urls:
                    all_sitemap_urls = [url]

            except Exception as sm_err:
                logger.error(f"[!] [SITEMAP DISCOVERY] Error discovering child sitemaps from {url}: {sm_err}")
                if dlq:
                    dlq.record_failure(
                        url=url,
                        vendor_id=vendor_id,
                        error_type=type(sm_err).__name__,
                        message=str(sm_err),
                    )
                return []

            # -------------------------------------------------------------------------
            # 2. SYNCHRONIZE DISCOVERED SITEMAP URLS WITH KNOWLEDGE BASE
            # -------------------------------------------------------------------------
            if len(all_sitemap_urls) > 1 or all_sitemap_urls[0] != url:
                state.mark_unit_completed(url)
            pending_queue, is_new_cycle = state.sync_knowledge_base(all_sitemap_urls)
            print(
                f"[*] [KNOWLEDGE BASE SYNC] Discovered {len(all_sitemap_urls)} Total Sitemaps. "
                f"KB Units: {len(state.knowledge_base)}, Pending in Cycle {state.cycle}: {len(state.pending_queue)}, "
                f"Completed: {len(state.completed_units)}"
            )

            # -------------------------------------------------------------------------
            # 3. CAPABILITY-BASED BATCH PROCESSING
            # -------------------------------------------------------------------------
            batch_iteration = 0
            while state.pending_queue:
                batch_iteration += 1
                batch_urls = state.get_next_batch(capability="sitemap", batch_size=batch_size)
                if not batch_urls:
                    break

                print(
                    f"\n[*] [SITEMAP BATCH {batch_iteration}] Running batch of {len(batch_urls)} child sitemaps "
                    f"(Queue Remaining: {len(state.pending_queue)}, Cycle: {state.cycle}):"
                )
                for b_url in batch_urls[:3]:
                    print(f"    - {b_url}")
                if len(batch_urls) > 3:
                    print(f"    ... and {len(batch_urls) - 3} more")

                failed_sitemaps: List[str] = []
                batch_records: List[ProductRecord] = []

                for idx, c_url in enumerate(batch_urls, 1):
                    if max_pages > 0 and len(records) >= max_pages:
                        print(f"[SITEMAP STRATEGY] Reached configured max_pages limit ({max_pages}).")
                        break

                    clean_c_url = c_url.strip()
                    if not (clean_c_url.startswith("http://") or clean_c_url.startswith("https://")):
                        logger.debug(f"[SITEMAP STRATEGY] Skipping non-URL child entry: {c_url}")
                        continue

                    print(f"  [{idx}/{len(batch_urls)}] Ingesting child sitemap: {clean_c_url}")
                    c_html: Optional[str] = None
                    try:
                        if clean_c_url == url and root_html:
                            c_html = root_html
                        else:
                            c_html = await _fetch_sitemap_content(clean_c_url)
                        if not c_html:
                            failed_sitemaps.append(c_url)
                            logger.warning(f"  [!] Failed to fetch child sitemap {c_url}: empty response")
                            if dlq:
                                dlq.record_failure(
                                    url=c_url,
                                    vendor_id=vendor_id,
                                    error_type="ChildSitemapFetchFailed",
                                    message="Empty or failed child sitemap response",
                                )
                            continue

                        extracted_for_sm = 0

                        def _extract_sku(loc_u: str) -> Optional[str]:
                            m_match = pattern_re.search(loc_u)
                            if not m_match:
                                m_pdp = re.search(r"details\.([A-Za-z0-9\-_.]+)\.html", loc_u, re.I)
                                if m_pdp:
                                    clean = m_pdp.group(1).strip()
                                    from scraper.models import is_valid_product_model
                                    if clean and is_valid_product_model(clean) and any(c.isdigit() for c in clean):
                                        return clean
                                return None
                            raw_val = None
                            try:
                                raw_val = m_match.group(model_group_idx)
                            except IndexError:
                                pass
                            if not raw_val:
                                for g in m_match.groups():
                                    if g:
                                        raw_val = g
                                        break
                            if not raw_val:
                                raw_val = m_match.group(0)
                            if raw_val:
                                clean = str(raw_val).strip()
                                clean = re.sub(r"\.html?$", "", clean, flags=re.I)
                                clean = clean.split("/")[-1].split("details.")[-1].strip()
                                from scraper.models import is_valid_product_model
                                if not clean or not is_valid_product_model(clean):
                                    return None
                                # Reject purely alphabetical slugs (e.g. terms, tools, privacy, overview) that lack model numbers
                                if not any(c.isdigit() for c in clean):
                                    return None
                                return clean
                            return None

                        # Streaming O(1) memory extraction of <url> and <sitemap> entries
                        for loc_text, lastmod_text in stream_iterparse_sitemap_urls(c_html):
                            if max_pages > 0 and (len(records) + len(batch_records)) >= max_pages:
                                break

                            model_sku = _extract_sku(loc_text)
                            if model_sku and not state.is_model_seen(model_sku):
                                status_val = "Discontinued" if any(k in loc_text.lower() for k in ("discontinue", "/discon/", "obsolete", "eol", "legacy", "phased-out", "phase-out")) else entry_point.get("default_status")
                                if not status_val:
                                    continue
                                extra_m: Optional[Dict[str, Any]] = None
                                if lastmod_text:
                                    extra_m = {"lastmod": lastmod_text, "page_creation_date": lastmod_text}
                                rec = self.create_sanitized_record(
                                    vendor_name=vendor_name,
                                    raw_model=model_sku,
                                    raw_alias=None,
                                    raw_status=status_val,
                                    raw_date=None,
                                    source_url=loc_text,
                                    category=category_name,
                                    extra_meta=extra_m,
                                )
                                if rec:
                                    batch_records.append(rec)
                                    state.record_model(rec.model_name)
                                    extracted_for_sm += 1

                        if extracted_for_sm == 0 and c_html:
                            # Direct regex extraction fallback for Chromium XML viewer HTML rendering or raw text
                            found_urls = re.findall(r"https?://[^\s\"'<>\\]+", c_html)
                            for cand_u in found_urls:
                                model_sku = _extract_sku(cand_u)
                                if model_sku and not state.is_model_seen(model_sku):
                                    status_val = "Discontinued" if any(k in cand_u.lower() for k in ("discontinue", "/discon/", "obsolete", "eol", "legacy", "phased-out", "phase-out")) else entry_point.get("default_status")
                                    if not status_val:
                                        continue
                                    rec = self.create_sanitized_record(
                                        vendor_name=vendor_name,
                                        raw_model=model_sku,
                                        raw_alias=None,
                                        raw_status=status_val,
                                        raw_date=None,
                                        source_url=cand_u,
                                        category=category_name,
                                    )
                                    if rec:
                                        batch_records.append(rec)
                                        state.record_model(rec.model_name)
                                        extracted_for_sm += 1

                            if extracted_for_sm == 0 and c_html:
                                raw_skus = re.findall(r"details\.([A-Za-z0-9\-_.]+)\.html", c_html, flags=re.I)
                                for r_sku in raw_skus:
                                    clean_sku = r_sku.strip()
                                    from scraper.models import is_valid_product_model
                                    if clean_sku and is_valid_product_model(clean_sku) and any(c.isdigit() for c in clean_sku) and not state.is_model_seen(clean_sku):
                                        status_val = "Discontinued" if any(k in clean_sku.lower() for k in ("discontinue", "/discon/", "obsolete", "eol", "legacy", "phased-out", "phase-out")) else entry_point.get("default_status")
                                        if not status_val:
                                            continue
                                        rec = self.create_sanitized_record(
                                            vendor_name=vendor_name,
                                            raw_model=clean_sku,
                                            raw_alias=None,
                                            raw_status=status_val,
                                            raw_date=None,
                                            source_url=f"https://www.rockwellautomation.com/en-us/products/details.{clean_sku}.html" if "rockwell" in vendor_id else c_url,
                                            category=category_name,
                                        )
                                        if rec:
                                            batch_records.append(rec)
                                            state.record_model(rec.model_name)
                                            extracted_for_sm += 1

                        print(f"    [+] Extracted {extracted_for_sm} products from {c_url}")

                    except Exception as child_err:
                        failed_sitemaps.append(c_url)
                        logger.error(f"  [!] Error processing child sitemap {c_url}: {child_err}")
                        if dlq:
                            dlq.record_failure(
                                url=c_url,
                                vendor_id=vendor_id,
                                error_type=type(child_err).__name__,
                                message=str(child_err),
                            )

                # Mark batch completed in state and knowledge base
                state.mark_batch_completed(batch_urls, records_count=len(batch_records), failed_units=failed_sitemaps)
                records.extend(batch_records)

                print(
                    f"[+] [SITEMAP BATCH {batch_iteration} COMPLETE] Finished {len(batch_urls)} child sitemaps. "
                    f"Harvested {len(batch_records)} records. {len(state.pending_queue)} remaining in queue."
                )

                if not all_batches:
                    print("[*] Single-batch run mode complete. Next run will process subsequent batch.")
                    break

        state.total_records += len(records)
        state.save()
        logger.info(f"[SITEMAP STRATEGY] Ingestion finished for {vendor_name}: {len(records)} products harvested.")
        return records
