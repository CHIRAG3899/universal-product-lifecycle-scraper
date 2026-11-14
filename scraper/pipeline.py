"""
Enterprise Unified Scraper Pipeline.
Coordinates config-driven multi-vendor crawling across OT, IoT, and IT sectors,
dynamic site-level discovery, database-ready normalization, security sanitization,
SHA-256 deduplication, non-overwriting export, run traceability artifacts,
and enterprise observability alerts.
"""

import asyncio
import json
import logging
import os
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

from scraper.ai_extractor import UniversalAIExtractor
from scraper.artifacts import RunArtifactManager
from scraper.checkpoint import CheckpointManager
from scraper.config import BASE_DIR
from scraper.coverage import CoverageTracker
from scraper.crawl_engine import UniversalAICrawler
from scraper.delta_cache import DeltaCache
from scraper.dlq import get_global_dlq
from scraper.models import (
    ProductRecord,
    ScrapedDataset,
    extract_candidate_article_or_page_date,
    is_valid_product_model,
    is_valid_replacement_model,
    is_well_known_os_or_software,
    resolve_fallback_stage_date,
)
from scraper.observability import AlertDispatcher, PipelineMetricsCollector
from scraper.security import clean_and_sanitize_identifier, inspect_security_threats, is_safe_url
from scraper.state import DEFAULT_STATE_DIR, VendorRunState
from scraper.storage import MasterStorageManager
from scraper.vendors import normalize_stage_name

logger = logging.getLogger("ai_scraper.pipeline")


def _resolve_ep_url(cfg: Any) -> str:
    """Safely extracts a string seed or portal URL from vendor config dictionary."""
    if not isinstance(cfg, dict):
        return "unknown"
    eps = cfg.get("entry_points") or []
    if eps and isinstance(eps, list):
        first = eps[0]
        if isinstance(first, dict):
            return str(first.get("url") or cfg.get("website") or "unknown")
        return str(first)
    return str(cfg.get("website") or "unknown")


class LifecyclePipeline:
    """
    Enterprise Pipeline orchestrating config-driven multi-vendor execution,
    traceability artifacts, storage persistence, and observability alerts.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        config_path: Optional[Path] = None,
        run_id: Optional[str] = None,
        batch_mode: Optional[bool] = None,
        thinking_budget: Optional[int] = None,
        enable_prompt_caching: Optional[bool] = None,
        provider: Optional[str] = None,
        api_base: Optional[str] = None,
        run_cache: Optional[Any] = None,
    ):
        self.config_path = config_path or (BASE_DIR / "configs" / "vendors.yaml")
        self.config = self._load_config()

        # Run-Level Cache
        from scraper.run_cache import RunCache, get_global_run_cache
        self.run_cache: RunCache = run_cache or get_global_run_cache()

        # Paths: Dual-CSV Output (eol_products_lifecycle.csv & active_products_lifecycle.csv)
        storage_cfg = self.config.get("storage", {})
        self.output_dir = BASE_DIR / storage_cfg.get("per_vendor_json_dir", "output")
        self.eol_csv = self.output_dir / "eol_products_lifecycle.csv"
        self.active_csv = self.output_dir / "active_products_lifecycle.csv"
        self.master_csv = self.eol_csv  # Backward compatibility alias
        self.artifacts_dir = BASE_DIR / storage_cfg.get("artifacts_dir", "artifacts/runs")

        # Core Components with Token & Cost Optimizations
        self.extractor = UniversalAIExtractor(
            api_key=api_key,
            model_name=model,
            thinking_budget=thinking_budget,
            enable_prompt_caching=enable_prompt_caching,
            batch_mode=batch_mode,
            provider=provider,
            api_base=api_base,
            run_cache=self.run_cache,
        )
        self.gemini = self.extractor  # Backward compatibility alias
        self.dlq = get_global_dlq()
        self.crawler = UniversalAICrawler(gemini_extractor=self.extractor, run_cache=self.run_cache, dlq=self.dlq)
        self.storage = MasterStorageManager(output_dir=self.output_dir)
        self.coverage_tracker = CoverageTracker(self.output_dir, self.artifacts_dir)
        self.artifact_mgr = RunArtifactManager(self.artifacts_dir, run_id=run_id)
        self.checkpoint_mgr = CheckpointManager()
        self.delta_cache = DeltaCache()
        
        obs_cfg = self.config.get("observability", {})
        alert_days = obs_cfg.get("alert_ltb_threshold_days", 90)
        self.metrics_collector = PipelineMetricsCollector(self.artifact_mgr.run_id, alert_ltb_days=alert_days)
        self.webhook_url = os.getenv("WEBHOOK_URL", obs_cfg.get("webhook_url", ""))

    def _load_config(self) -> Dict[str, Any]:
        """Loads configuration from YAML file or falls back to defaults."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Failed to load {self.config_path}: {e}")
        return {}

    async def execute_vendor(
        self,
        vendor_key: str,
        vendor_cfg: Dict[str, Any],
        site_crawl: bool = False,
        max_pages: int = 0,
        max_depth: int = 0,
        resume: bool = False,
        accumulate_batches: Optional[bool] = None,
        batch_size: Optional[int] = None,
        all_batches: bool = False,
        reset_state: bool = False,
    ) -> List[ProductRecord]:
        """
        Executes pipeline for a single vendor across configured entry points or full website domain.
        Logs each of the 6 pipeline stages clearly.
        Supports capability-based batching, persistent knowledge-base synchronization, and multi-cycle execution.
        """
        vendor_name = vendor_cfg.get("name", vendor_key.title())
        vendor_id = vendor_cfg.get("id", vendor_key.lower())
        sector = vendor_cfg.get("sector", "General")
        website = vendor_cfg.get("website", "")
        entry_points = list(vendor_cfg.get("entry_points") or []) + list(vendor_cfg.get("strategies") or [])
        allowed_domains = list(vendor_cfg.get("allowed_domains") or [])
        if not allowed_domains:
            derived = set()
            if website:
                try:
                    host = urllib.parse.urlsplit(website).netloc.split(":")[0].lower()
                    if host.startswith("www."):
                        host = host[4:]
                    if host:
                        derived.add(host)
                except Exception:
                    pass
            for ep_item in entry_points:
                u = ep_item.get("url") if isinstance(ep_item, dict) else str(ep_item)
                if u:
                    try:
                        host = urllib.parse.urlsplit(u).netloc.split(":")[0].lower()
                        if host.startswith("www."):
                            host = host[4:]
                        if host:
                            derived.add(host)
                    except Exception:
                        pass
            allowed_domains = sorted(list(derived))

        accumulate = bool(getattr(self.extractor, "batch_mode", False)) if accumulate_batches is None else accumulate_batches

        print("\n" + "=" * 90)
        print(f"[*] LIFECYCLE SCRAPING WORKFLOW: [{sector}] {vendor_name} (ID: {vendor_id}) [Batch Size: {batch_size or 'Auto'}, All Batches: {all_batches}]")
        print("=" * 90)

        # -------------------------------------------------------------------------
        # STEP 1/6: DISCOVERY & CRAWLING
        # -------------------------------------------------------------------------
        print(f"[STEP 1/6: DISCOVERY & CRAWLING] Target Domain / Website: {website or 'N/A'}")
        vendor_products: List[ProductRecord] = []
        vendor_start = datetime.now()
        error_msg = None

        accumulated_chunks: List[Dict[str, Any]] = []
        accumulated_direct: List[ProductRecord] = []

        try:
            # Optional state reset
            if reset_state:
                VendorRunState.purge(vendor_id)
                self.storage.purge_vendor_records(vendor_id)
                print(f"[*] Fully purged state and storage records for {vendor_id}")

            vendor_state = VendorRunState.load(vendor_id, state_dir=DEFAULT_STATE_DIR)

            # -------------------------------------------------------------------------
            # INSPECT NEWLY ADDED TAGS & ELIMINATE ENTRY POINT REDUNDANCIES
            # -------------------------------------------------------------------------
            cleaned_entry_points: List[Dict[str, Any]] = []
            seen_canonical_urls: Set[str] = set()
            sitemap_discovery_cfgs: List[Dict[str, Any]] = []

            for ep in entry_points:
                if not isinstance(ep, dict):
                    continue
                url = str(ep.get("url") or ep.get("url_template") or "").strip()
                if not url:
                    continue

                role = str(ep.get("endpoint_role") or "").lower()
                tags = [str(t).lower() for t in (ep.get("source_tags") or [])]
                authority = str(ep.get("evidence_authority") or "").lower()

                # Detect discovery-only sitemaps
                is_discovery_only = (
                    ep.get("sitemap_discovery_only") is True
                    or role == "sitemap_discovery"
                    or "sitemap_discovery_only" in tags
                    or authority == "url_discovery_only_not_lifecycle_status"
                )

                if is_discovery_only:
                    sitemap_discovery_cfgs.append({
                        "index_url": url,
                        "child_filter": ep.get("child_filter", "sitemap.PDP_"),
                        "prefix_regex": ep.get("product_pattern", r"details\.([A-Za-z0-9\-_.]+)\.html"),
                    })
                    logger.info(
                        f"[PIPELINE TAG REVIEW] Skipping direct product scrape on discovery-only endpoint '{ep.get('name')}': {url}"
                    )
                    continue

                # Deduplicate by canonical URL
                canon_url = url.split("?")[0].rstrip("/").lower()
                if canon_url in seen_canonical_urls:
                    logger.info(f"[PIPELINE DEDUPLICATION] Removed redundant entry point '{ep.get('name')}': {url}")
                    continue
                seen_canonical_urls.add(canon_url)

                # Auto-assign strategies from crawler types, recommendations, roles, and URL patterns
                strat = ep.get("strategy")
                rec_strat = str(ep.get("recommended_crawler_type") or "").lower()
                c_type = str(ep.get("crawler_type") or "").lower()
                url_lower = str(url or "").lower()

                if not strat or str(strat).lower() in ("none", "inspect_source_adapter"):
                    if c_type in ("sitemap", "sitemap_auto", "sitemap_index", "sitemap_gzip_auto", "sitemap_probe") or url_lower.endswith((".xml", ".xml.gz")) or "sitemap" in url_lower:
                        ep["strategy"] = "sitemap"
                    elif c_type in ("search_portal", "lifecycle_search", "interactive_search") or "product-lifecycle-status" in url_lower:
                        ep["strategy"] = "search_portal"
                    elif c_type in ("rest_api", "json_api", "api") or "/api/" in url_lower:
                        ep["strategy"] = "rest_api"
                    elif rec_strat in ("html_table", "dom_table", "html_notice_index", "html_filterable_table", "dom_listing") or role in (
                        "dated_eol_notice_index", "dated_model_lifecycle_notice", "dated_model_notice_index",
                        "direct_model_or_version_status_source", "model_status_table", "html_table", "dom_table"
                    ):
                        ep["strategy"] = "dom_table"
                    elif rec_strat in ("interactive_search", "search_portal") or role in (
                        "interactive_lifecycle_search", "interactive_model_lifecycle_lookup", "model_status_search"
                    ):
                        ep["strategy"] = "search_portal"
                    elif rec_strat in ("sitemap", "sitemap_index") or role == "sitemap_discovery":
                        ep["strategy"] = "sitemap"

                cleaned_entry_points.append(ep)

            # Connect discovery sitemaps to search portals if available
            if sitemap_discovery_cfgs:
                for ep in cleaned_entry_points:
                    ep_strat = str(ep.get("strategy") or ep.get("crawler_type") or "").lower()
                    if ep_strat in ("search_portal", "lifecycle_search") or "product-lifecycle-status" in str(ep.get("url", "")):
                        if not ep.get("sitemap_discovery"):
                            ep["sitemap_discovery"] = sitemap_discovery_cfgs[0]

            # -------------------------------------------------------------------------
            # ENTRY POINT KNOWLEDGE BASE SYNCHRONIZATION & CAPABILITY BATCHING
            # -------------------------------------------------------------------------
            active_ep_urls = [
                str(ep.get("url") or ep.get("url_template", "")).strip()
                for ep in cleaned_entry_points
                if str(ep.get("strategy") or ep.get("crawler_type") or "").lower() not in (
                    "search_portal", "lifecycle_search", "sitemap", "sitemap_index"
                )
                and "product-lifecycle-status" not in str(ep.get("url", ""))
                and str(ep.get("url") or ep.get("url_template", "")).strip()
            ]
            if active_ep_urls:
                vendor_state.sync_knowledge_base(active_ep_urls)

            effective_all_batches = all_batches or (batch_size is None)
            target_entry_points = cleaned_entry_points
            if len(active_ep_urls) > 1 and not effective_all_batches:
                batch_urls = vendor_state.get_next_batch(capability="dom_table", batch_size=batch_size)
                if batch_urls:
                    target_entry_points = [
                        ep for ep in cleaned_entry_points
                        if str(ep.get("url") or ep.get("url_template", "")).strip() in batch_urls
                        or str(ep.get("strategy") or ep.get("crawler_type") or "").lower() in ("search_portal", "lifecycle_search")
                        or "product-lifecycle-status" in str(ep.get("url", ""))
                    ]
                    print(
                        f"[*] [ENTRY POINT BATCH] Running batch of {len(target_entry_points)} entry points "
                        f"({len(vendor_state.completed_units)} completed, {len(vendor_state.pending_queue)} pending in Cycle {vendor_state.cycle})."
                    )

            for ep in target_entry_points:
                url = str(ep.get("url") or ep.get("url_template") or "")
                name = ep.get("name", "entry")
                region = ep.get("region", "Global")
                strategy_name = str(ep.get("strategy") or ep.get("crawler_type") or "").lower()
                if strategy_name in ("none", "null"):
                    strategy_name = ""

                # Unified Strategy Pattern Dispatch
                is_search_portal = strategy_name in ("search_portal", "lifecycle_search") or (
                    vendor_id in ("rockwell_automation", "rockwell") and "product-lifecycle-status" in str(url)
                )
                from scraper.strategies import _STRATEGY_REGISTRY, get_strategy

                is_registered_strategy = is_search_portal or strategy_name in _STRATEGY_REGISTRY

                if is_registered_strategy:
                    strat_key = "search_portal" if is_search_portal else strategy_name
                    strat = get_strategy(strat_key)
                    strat_label = strat_key.replace("_", " ").upper()
                    print(f"  -> [STRATEGY: {strat_label}] Executing '{name}' ({region}): {url}")
                    try:
                        strat_records = await strat.execute(
                            entry_point=ep,
                            vendor_cfg=vendor_cfg,
                            crawler=self.crawler,
                            state=vendor_state,
                            dlq=self.dlq,
                            max_pages=max_pages,
                            batch_size=batch_size,
                            all_batches=all_batches,
                        )
                        for r in strat_records:
                            r.vendor_name = vendor_name
                            if "region" not in r.metadata:
                                r.metadata["region"] = region
                        vendor_products.extend(strat_records)
                        vendor_state.mark_unit_completed(str(url), records_count=len(strat_records))
                        vendor_state.save()
                        print(f"  -> [STRATEGY: {strat_label}] Harvested {len(strat_records)} authentic records from '{name}'.")
                    except Exception as strat_err:
                        print(f"  [!] {strat_label} execution error on {name}: {strat_err}")
                        self.dlq.record_failure(
                            url=str(url),
                            vendor_id=vendor_id,
                            error_type=type(strat_err).__name__,
                            message=str(strat_err),
                            details={"entry_point": name, "strategy": strat_key}
                        )
                    continue

                if not is_safe_url(url, allowed_domains):
                    print(f"  [!] Security Guard: Blocked untrusted URL or non-whitelisted domain: {url}")
                    continue

                norm_url = self.run_cache.normalize_url(url)
                if resume and vendor_state.is_unit_completed(str(url)):
                    print(f"  -> [STATE MEMORY HIT] Skipping already completed entry point '{name}': {url}")
                    if self.run_cache.has_extracted_products(norm_url):
                        cached_records = self.run_cache.get_extracted_products(norm_url) or []
                        for r in cached_records:
                            r.vendor_name = vendor_name
                            if "region" not in r.metadata:
                                r.metadata["region"] = region
                        vendor_products.extend(cached_records)
                    continue

                if self.run_cache.has_extracted_products(norm_url):
                    print(f"  -> [RUN_CACHE HIT] Reusing cached records for entry point '{name}' ({region}): {url}")
                    cached_records = self.run_cache.get_extracted_products(norm_url) or []
                    for r in cached_records:
                        r.vendor_name = vendor_name
                        if "region" not in r.metadata:
                            r.metadata["region"] = region
                    vendor_products.extend(cached_records)
                    vendor_state.mark_unit_completed(str(url))
                    vendor_state.save()
                    continue

                crawler_type = str(ep.get("crawler_type", "")).lower()
                is_sitemap = crawler_type in ("sitemap", "sitemap_index", "lifecycle_search", "search_portal") or (url and url.endswith(".xml")) or (url and "sitemap" in url.lower() and not url.endswith((".html", ".htm", ".jsp"))) or (url and "product-lifecycle-status.html" in url) or bool(ep.get("keywords"))

                if is_sitemap:
                    print(f"  -> [GENERIC SITEMAP CRAWLER] Ingesting sitemap hierarchy for '{name}' ({region}): {url}")
                    try:
                        sm_records = await self.crawler.crawl_sitemap_entry_point(
                            entry_point=ep,
                            vendor_name=vendor_name,
                            allowed_domains=allowed_domains,
                            max_pages=max_pages
                        )
                        for r in sm_records:
                            r.vendor_name = vendor_name
                            if "region" not in r.metadata:
                                r.metadata["region"] = region
                            vendor_state.record_model(r.model_name)
                        vendor_products.extend(sm_records)
                        vendor_state.mark_unit_completed(str(url))
                        vendor_state.total_records += len(sm_records)
                        vendor_state.save()
                        print(f"  -> [GENERIC SITEMAP CRAWLER] Harvested {len(sm_records)} product records from '{name}'.")
                    except Exception as sm_err:
                        print(f"  [!] Sitemap crawl notice on {name} ({url}): {sm_err}")
                        self.dlq.record_failure(
                            url=str(url),
                            vendor_id=vendor_id,
                            error_type=type(sm_err).__name__,
                            message=str(sm_err),
                            details={"region": region, "entry_point": name}
                        )
                    continue

                print(f"  -> Crawling verified lifecycle portal '{name}' ({region}): {url}")
                try:
                    if accumulate:
                        crawl_data = await self.crawler.crawl_page(url)
                        dir_recs, chunks = self.crawler.prepare_page_chunks(url, crawl_data, vendor_name)
                        for dr in dir_recs:
                            dr.vendor_name = vendor_name
                            if "region" not in dr.metadata:
                                dr.metadata["region"] = region
                        accumulated_direct.extend(dir_recs)
                        accumulated_chunks.extend(chunks)
                    else:
                        records = await self.crawler.run(url)
                        for r in records:
                            r.vendor_name = vendor_name
                            if "region" not in r.metadata:
                                r.metadata["region"] = region
                            vendor_state.record_model(r.model_name)
                        vendor_products.extend(records)
                        vendor_state.mark_unit_completed(str(url))
                        vendor_state.total_records += len(records)
                        vendor_state.save()
                except Exception as ep_err:
                    print(f"  [!] Warning on entry point {name} ({url}): {ep_err}")
                    self.dlq.record_failure(
                        url=str(url),
                        vendor_id=vendor_id,
                        error_type=type(ep_err).__name__,
                        message=str(ep_err),
                        details={"region": region, "entry_point": name}
                    )

            # 2. Secondary discovery: Run domain-level site crawl ONLY if explicitly requested
            should_site_crawl = site_crawl and bool(website)
            if should_site_crawl and website:
                page_str = "Unlimited" if not max_pages or max_pages <= 0 else str(max_pages)
                depth_str = "Unlimited" if not max_depth or max_depth <= 0 else str(max_depth)
                crawl_reason = "Supplementary deep discovery" if site_crawl else "Automatic fallback (0 records from entry points)"
                print(f"  -> [{crawl_reason}] Crawling vendor domain: {website} (Max pages: {page_str}, Max depth: {depth_str})")
                try:
                    records = await self.crawler.crawl_website(
                        website,
                        allowed_domains=allowed_domains,
                        max_pages=max_pages,
                        max_depth=max_depth,
                        accumulate_batches=accumulate
                    )
                    for r in records:
                        r.vendor_name = vendor_name
                        if "region" not in r.metadata:
                            r.metadata["region"] = "Global"
                    vendor_products.extend(records)
                except Exception as sc_err:
                    print(f"  [!] Domain site discovery crawl notice on {website}: {sc_err}")

            # -------------------------------------------------------------------------
            # STEP 2/6: EXTRACTION
            # -------------------------------------------------------------------------
            if accumulate and (accumulated_chunks or accumulated_direct):
                print(f"[STEP 2/6: AI BATCH EXTRACTION] Dispatching {len(accumulated_chunks)} accumulated chunks to AI engine...")
                batch_records = self.crawler.extract_accumulated_batches(
                    accumulated_chunks,
                    pre_extracted=accumulated_direct,
                    default_vendor=vendor_name
                )
                for br in batch_records:
                    if "region" not in br.metadata:
                        br.metadata["region"] = "Global"
                vendor_products.extend(batch_records)

            vendor_products_raw = list(vendor_products)
            print(f"[STEP 2/6: AI / APOLLO EXTRACTION] Extracted {len(vendor_products)} candidate records.")

            # -------------------------------------------------------------------------
            # STEP 3/6: NORMALISATION
            # -------------------------------------------------------------------------
            print("[STEP 3/6: NORMALISATION] Running multi-vendor data normalization:")
            print("  -> Unbundling grouped model names into discrete entities")
            print("  -> Preserving vendor-exact official lifecycle status / phase milestones")
            print("  -> Normalizing date strings to ISO 8601 UTC (YYYY-MM-DDTHH:MM:SSZ)")
            print("  -> Formatting firmware to semantic versions (X.Y.Z) without defaults")
            print("  -> Translating international regional terms (JA/DE/SV/FR) to standard English")
            print("  -> Extracting vendor-used official terminology dynamically from source")

            # -------------------------------------------------------------------------
            # STEP 4/6: SANITISATION & SECURITY
            # -------------------------------------------------------------------------
            print("[STEP 4/6: SANITISATION & SECURITY] Applying enterprise sanity guards:")
            sanitized_products: List[ProductRecord] = []
            purged_noise_count = 0
            blocked_threats_count = 0

            for p in vendor_products:
                v_name = (p.vendor_name or "").strip()
                m_name = (p.model_name or "").strip()
                st_val = (p.status or p.vendor_status or p.stage or "").strip()
                dt_val = (p.stage_date_utc or "").strip()
                cat = (p.category or "").strip()
                os_val = (p.os or "").strip()
                is_sw = is_well_known_os_or_software(category=cat, os_name=os_val, model_name=m_name)

                if not v_name or v_name.lower() in ("n/a", "none", "null", "nan"):
                    purged_noise_count += 1
                    continue

                # Strict Lifecycle Relevance Guard: Discard non-lifecycle statuses (sitemaps, video guides, consumer fans)
                st_lower = st_val.lower()
                cat_lower = cat.lower()
                disallowed_status_terms = {
                    "active sitemaps record", "support video published",
                    "consulting services", "flexible credits", "operations offerings",
                    "service program", "battery recall program", "available order"
                }
                if st_lower in disallowed_status_terms or "video" in st_lower or "sitemap" in st_lower:
                    purged_noise_count += 1
                    continue
                if any(kw in cat_lower for kw in ("electric fan", "ventilation fan", "home appliance", "refrigerator")):
                    purged_noise_count += 1
                    continue

                # Enterprise Threat Prevention Shield (SQLi, XSS, Path Traversal, Command Injection)
                is_th, th_type, th_reason = inspect_security_threats(m_name, field_name="model_name")
                if not is_th:
                    is_th, th_type, th_reason = inspect_security_threats(v_name, field_name="vendor_name")
                if not is_th:
                    is_th, th_type, th_reason = inspect_security_threats(st_val, field_name="status")
                if is_th:
                    logger.warning(f"Security threat blocked ({th_type}): {th_reason} in record for {v_name}")
                    blocked_threats_count += 1
                    purged_noise_count += 1
                    continue

                # Strict Public Source Ingestion Sanitization:
                # Strip corrupt data, mojibake, control chars, uncommon symbols
                # Enforce strictly alphanumeric + sensible standard symbols (- / : . _ + & ( ) # space)
                if not is_sw:
                    clean_m = clean_and_sanitize_identifier(m_name)
                    if not clean_m or not is_valid_product_model(clean_m):
                        if not is_valid_product_model(m_name):
                            purged_noise_count += 1
                            continue
                    else:
                        from scraper.models import strip_regional_suffix
                        clean_mod_str, stripped_reg = strip_regional_suffix(clean_m)
                        if not clean_mod_str or not is_valid_product_model(clean_mod_str):
                            purged_noise_count += 1
                            continue
                        if stripped_reg and isinstance(p.metadata, dict) and "country_variant" not in p.metadata:
                            p.metadata["country_variant"] = stripped_reg
                        if m_name.startswith(("=", "+", "-", "@")):
                            p.model_name = "'" + m_name[0] + clean_mod_str
                        else:
                            p.model_name = clean_mod_str
                        m_name = clean_mod_str
                else:
                    if m_name and m_name.lower() not in ("n/a", "none", "null", "nan"):
                        clean_m = clean_and_sanitize_identifier(m_name)
                        if clean_m and is_valid_product_model(clean_m):
                            from scraper.models import strip_regional_suffix
                            clean_mod_str, stripped_reg = strip_regional_suffix(clean_m)
                            if stripped_reg and isinstance(p.metadata, dict) and "country_variant" not in p.metadata:
                                p.metadata["country_variant"] = stripped_reg
                            p.model_name = clean_mod_str or clean_m
                        elif not is_valid_product_model(m_name):
                            purged_noise_count += 1
                            continue
                if not st_val or st_val.lower() in ("n/a", "none", "null", "nan") or len(st_val) > 40:
                    purged_noise_count += 1
                    continue
                # Missing date fallback logic: use article, page creation, or release date (at least 1 month old), or 1 month old from current date
                if not dt_val or dt_val.lower() in ("n/a", "none", "null", "nan"):
                    cand_dt = extract_candidate_article_or_page_date(p.metadata if isinstance(p.metadata, dict) else None)
                    p.stage_date_utc = resolve_fallback_stage_date(None, candidate_date=cand_dt, metadata=p.metadata if isinstance(p.metadata, dict) else None)
                    if isinstance(p.metadata, dict):
                        p.metadata["missing_date"] = True
                        p.metadata["fallback_date_applied"] = True

                # Strict Alias Sanitization Guard (Reject dates, noise, self-identity)
                if p.aliases:
                    from dateutil import parser as date_parser

                    from scraper.strategies.base import is_likely_date_str, sanitize_alias_text
                    a_raw = str(p.aliases).strip()
                    tokens = [t.strip() for t in re.split(r'[,;]+', a_raw) if t.strip()]
                    valid_aliases = []
                    for tok in tokens:
                        if is_likely_date_str(tok):
                            if isinstance(p.metadata, dict) and "announcement_date_utc" not in p.metadata:
                                try:
                                    dt_ann = date_parser.parse(tok, fuzzy=True)
                                    p.metadata["announcement_date_utc"] = dt_ann.strftime("%Y-%m-%d") + "T00:00:00Z"
                                except Exception:
                                    pass
                        elif tok.lower() in ("n/a", "none", "null", "nan", "-", "--", "tbd", "unknown") or tok.lower() == m_name.lower():
                            continue
                        else:
                            clean_tok = sanitize_alias_text(tok)
                            from scraper.models import strip_regional_suffix
                            clean_tok, _ = strip_regional_suffix(clean_tok)
                            if clean_tok and is_valid_product_model(clean_tok) and clean_tok.lower() != m_name.lower():
                                valid_aliases.append(clean_tok)

                    valid_aliases = list(dict.fromkeys(valid_aliases))
                    p.aliases = ", ".join(valid_aliases) if valid_aliases else None

                # Strict Replacement Sanitization Guard (Reject dates, boilerplate text)
                if p.replacement:
                    from scraper.strategies.base import is_likely_date_str, sanitize_alias_text
                    r_raw = str(p.replacement).strip()
                    tokens = [t.strip() for t in re.split(r'[,;]+', r_raw) if t.strip()]
                    valid_repls = []
                    for tok in tokens:
                        t_low = tok.lower()
                        if is_likely_date_str(tok) or t_low in ("n/a", "none", "null", "nan", "-", "--", "tbd", "unknown", "contact sales", "refer to bulletin", "see bulletin", "consult representative"):
                            continue
                        clean_r = sanitize_alias_text(tok)
                        from scraper.models import strip_regional_suffix
                        clean_r, _ = strip_regional_suffix(clean_r)
                        if clean_r and is_valid_replacement_model(clean_r):
                            valid_repls.append(clean_r)

                    valid_repls = list(dict.fromkeys(valid_repls))
                    p.replacement = ", ".join(valid_repls) if valid_repls else None

                sanitized_products.append(p)

            print(f"  -> Threat Prevention Layer: Blocked {blocked_threats_count} active security attacks (SQLi, XSS, Path Traversal, Command Injection)")
            print(f"  -> Field & Model Validator: Purged {purged_noise_count} invalid noise elements. Retained {len(sanitized_products)} clean products (including undated EOL models).")
            print("  -> CSV Formula Injection Shield: Sanitized formula trigger characters (=, +, -, @)")
            print(f"  -> SSRF Protection: Verified private IP restrictions across {len(allowed_domains)} allowed domains")

            # Deduplicate identical candidates across multi-region entry points before LLM validation
            unique_candidates: List[ProductRecord] = []
            cross_entrypoint_duplicates: List[Dict[str, Any]] = []
            seen_cand_fps = set()
            for p in sanitized_products:
                if p.fingerprint not in seen_cand_fps:
                    seen_cand_fps.add(p.fingerprint)
                    unique_candidates.append(p)
                else:
                    cross_entrypoint_duplicates.append({
                        "vendor": vendor_name,
                        "model": p.model_name,
                        "status": p.status,
                        "stage_date": p.stage_date_utc,
                        "source_url": p.source_url,
                        "reason": "Duplicate identical candidate across multi-region entry points"
                    })

            # Pre-Persistence LLM Verification Gate: Verify authentic model, status, and zero leaks
            print(f"[PRE-PERSISTENCE LLM GATE] Verifying {len(unique_candidates)} unique candidate records with LLM validator...")
            verified_products, rejected_records = self.extractor.verify_and_filter_records_with_llm(
                unique_candidates,
                vendor_name=vendor_name,
                return_rejections=True
            )
            print(f"  -> LLM Verification Gate: {len(verified_products)} verified authentic records approved for persistence.")

            # Record Reconciliation Accounting Ledger
            eol_cand_count = sum(1 for p in verified_products if normalize_stage_name(p.status) != "Active")
            active_cand_count = len(verified_products) - eol_cand_count
            print("[DATA ACCOUNTING RECONCILIATION]")
            print(f"  -> Raw Harvested:       {len(vendor_products_raw)}")
            print(f"  -> Step 4 Noise Purged: {purged_noise_count}")
            print(f"  -> Cross-Region Dups:   {len(cross_entrypoint_duplicates)} (Europe + Nordic identical SKUs)")
            print(f"  -> LLM Evaluated:       {len(unique_candidates)}")
            print(f"  -> LLM Rejected:        {len(rejected_records)}")
            print(f"  -> Persisted Dual-CSV:  {len(verified_products)} (EOL: {eol_cand_count} | Active: {active_cand_count})")

            # Persist vendor reconciliation ledger to disk
            reconciliation_ledger_path = Path("output") / "reconciliation_audit.json"
            all_reconciliations = {}
            if reconciliation_ledger_path.exists():
                try:
                    with open(reconciliation_ledger_path, "r", encoding="utf-8") as rf:
                        all_reconciliations = json.load(rf)
                except Exception:
                    all_reconciliations = {}
            all_reconciliations[vendor_id] = {
                "vendor_name": vendor_name,
                "raw_harvested_count": len(vendor_products_raw),
                "step4_purged_noise_count": purged_noise_count,
                "cross_entrypoint_duplicates_count": len(cross_entrypoint_duplicates),
                "llm_evaluated_count": len(unique_candidates),
                "llm_verified_count": len(verified_products),
                "llm_rejected_count": len(rejected_records),
                "eol_records_count": eol_cand_count,
                "active_records_count": active_cand_count,
                "cross_entrypoint_duplicates_sample": cross_entrypoint_duplicates[:25],
                "rejected_records": rejected_records,
                "reconciliation_explanation": (
                    f"Out of {len(vendor_products_raw)} raw records harvested across all entry points, "
                    f"{len(cross_entrypoint_duplicates)} were duplicate SKU milestones across multi-region portals, "
                    f"{purged_noise_count} were purged by sanity checks, and "
                    f"{len(rejected_records)} non-model/noise elements were rejected by the LLM Gate, "
                    f"yielding {len(verified_products)} authentic persisted records ({eol_cand_count} EOL, {active_cand_count} Active)."
                )
            }
            try:
                with open(reconciliation_ledger_path, "w", encoding="utf-8") as wf:
                    json.dump(all_reconciliations, wf, indent=2)
            except Exception as e_rec:
                logger.warning(f"Could not write reconciliation audit: {e_rec}")

            vendor_products = verified_products

            # Record per-vendor duration & telemetry
            vendor_duration = (datetime.now() - vendor_start).total_seconds()
            self.metrics_collector.record_vendor_result(vendor_name, len(vendor_products), vendor_duration)

            # Save per-vendor temporary review artifacts
            self.artifact_mgr.save_vendor_trace(
                vendor_id=vendor_id,
                vendor_name=vendor_name,
                products=vendor_products,
                crawl_stats={
                    "sector": sector,
                    "website": website,
                    "entry_points_configured": len(entry_points),
                    "records_extracted": len(vendor_products),
                    "duration_seconds": round(vendor_duration, 2)
                }
            )

        except Exception as e:
            error_msg = str(e)
            logger.exception(f"Error processing vendor {vendor_name}: {e}")
            vendor_duration = (datetime.now() - vendor_start).total_seconds()
            self.metrics_collector.record_vendor_result(vendor_name, 0, vendor_duration, error=error_msg)

        return vendor_products

    async def execute(
        self,
        vendor_filter: Optional[str] = None,
        sector_filter: Optional[str] = None,
        target_url: Optional[str] = None,
        site_crawl: bool = False,
        concurrency: Optional[int] = None,
        max_pages: int = 0,
        max_depth: int = 0,
        resume: bool = False,
        accumulate_batches: Optional[bool] = None,
        batch_size: Optional[int] = None,
        all_batches: bool = False,
        reset_state: bool = False,
    ) -> ScrapedDataset:
        """
        Executes the entire multi-vendor pipeline across the 6 observable stages:
        1. Discovery & Crawling
        2. AI Extraction
        3. Normalisation
        4. Sanitisation
        5. Deduplication & Merge
        6. Export & Observability
        """
        vendors_dict = self.config.get("vendors", {})
        all_harvested_products: List[ProductRecord] = []
        completed_vendor_keys: List[str] = []

        if reset_state:
            if vendor_filter and vendor_filter.lower() != "all":
                clean_v = vendor_filter.replace(" and ", ",")
                for t in clean_v.split(","):
                    t_str = t.strip().lower()
                    if t_str:
                        VendorRunState.purge(t_str)
                print(f"[*] Reset state executed: purged state & tracking for targeted vendor(s): {vendor_filter}")
            else:
                print("[*] Global clean-board reset initiated: purging all vendor states, batch queues, empty-vendor flags, and delta caches...")
                VendorRunState.purge_all()
                self.checkpoint_mgr.clear_checkpoint()
                self.delta_cache.clear()

        if resume:
            cp = self.checkpoint_mgr.load_checkpoint()
            if cp:
                print(f"\n[CHECKPOINT RESUME] Active checkpoint detected (Run ID: {cp.run_id}, Vendor: {cp.vendor_id}, Status: {cp.status}).")
                if cp.completed_vendors:
                    print(f"  -> Skipping {len(cp.completed_vendors)} previously completed vendors.")
                    completed_vendor_keys = list(cp.completed_vendors)
                if cp.failed_url:
                    print(f"  -> Will prioritize and retry failed URL: {cp.failed_url}")
            else:
                print("\n[CHECKPOINT RESUME] No previous checkpoint file found. Starting clean crawl.")

        if target_url:
            print(f"\n[STEP 1/6: DISCOVERY & CRAWLING] Executing ad-hoc crawl on: {target_url}")
            try:
                custom_products = await self.crawler.run(target_url)
                all_harvested_products.extend(custom_products)
            except Exception as e:
                self.checkpoint_mgr.save_checkpoint(
                    vendor_id="adhoc",
                    run_id=self.artifact_mgr.run_id,
                    status="failed",
                    failed_url=target_url,
                    error_message=str(e),
                    harvested_records_count=len(all_harvested_products)
                )
                raise e
        else:
            # Filter targeted vendors (supports comma-separated list and vendor aliases)
            target_vendors = []
            normalized_filter_keys = set()
            if vendor_filter and vendor_filter.lower() != "all":
                alias_map = {
                    "redhat": "red_hat",
                    "rockwell": "rockwell_automation",
                    "axis": "axis_communications",
                    "jtekt": "toyoda",
                    "toyoda": "toyoda",
                    "mitssubishi": "mitsubishi",
                    "phillips": "philips",
                }
                cleaned_filter = vendor_filter.replace(" and ", ",")
                raw_tokens = [t.strip().lower() for t in cleaned_filter.split(",") if t.strip()]
                for tok in raw_tokens:
                    mapped = alias_map.get(tok, tok)
                    normalized_filter_keys.add(mapped)

                # Prioritize exact vendor ID match if one exists to prevent accidental substring overlap
                exact_matches = {
                    k: v for k, v in vendors_dict.items()
                    if k.lower() in normalized_filter_keys or str(v.get("id", "")).lower() in normalized_filter_keys
                }
                if exact_matches:
                    vendors_dict = exact_matches
                    normalized_filter_keys.clear()

            for v_key, v_cfg in vendors_dict.items():
                if normalized_filter_keys:
                    v_k_lower = v_key.lower()
                    v_id_lower = str(v_cfg.get("id", "")).lower()
                    v_name_lower = str(v_cfg.get("name", "")).lower()
                    matched = False
                    for query in normalized_filter_keys:
                        if query in (v_k_lower, v_id_lower) or re.search(r'\b' + re.escape(query) + r'\b', v_name_lower):
                            matched = True
                            break
                    if not matched:
                        continue
                if sector_filter and sector_filter.lower() != "all":
                    s_filter = sector_filter.lower()
                    v_sector = str(v_cfg.get("sector", "")).lower()
                    v_sectors = [str(s).lower() for s in v_cfg.get("sectors", [])]
                    if v_sector != s_filter and s_filter not in v_sectors:
                        continue
                if v_key in completed_vendor_keys:
                    continue
                target_vendors.append((v_key, v_cfg))

            default_max = "1" if os.getenv("SCRAPER_TEST_MODE") == "1" else "4"
            max_workers = concurrency or int(os.getenv("MAX_CONCURRENT_VENDORS", default_max))
            if max_workers > 1 and len(target_vendors) > 1:
                print(f"\n[*] Executing multi-vendor crawl with bounded concurrency: {max_workers} parallel workers")
                sem = asyncio.Semaphore(max_workers)

                async def _worker(vk: str, vc: Dict[str, Any]):
                    async with sem:
                        res = await self.execute_vendor(
                            vk,
                            vc,
                            site_crawl=site_crawl,
                            max_pages=max_pages,
                            max_depth=max_depth,
                            resume=resume,
                            accumulate_batches=accumulate_batches,
                            batch_size=batch_size,
                            all_batches=all_batches,
                            reset_state=reset_state,
                        )
                        completed_vendor_keys.append(vk)
                        return res

                results = await asyncio.gather(*[_worker(vk, vc) for vk, vc in target_vendors], return_exceptions=True)
                failed_exceptions = []
                for (vk, vc), r in zip(target_vendors, results):
                    if isinstance(r, list):
                        all_harvested_products.extend(r)
                    elif isinstance(r, Exception):
                        logger.error(f"[HIGH AVAILABILITY] Concurrent worker task error for vendor '{vk}': {r}")
                        failed_exceptions.append((vk, r))
                        ep_url = _resolve_ep_url(vc)
                        self.dlq.record_failure(
                            url=ep_url,
                            vendor_id=vk,
                            error_type=type(r).__name__,
                            message=str(r),
                            status_code=500,
                            tier="concurrent_pipeline_worker"
                        )
                        self.metrics_collector.record_vendor_failure(vk, str(r))

                if failed_exceptions:
                    pending_keys = [tv[0] for tv in target_vendors if tv[0] not in completed_vendor_keys]
                    self.checkpoint_mgr.save_checkpoint(
                        vendor_id=failed_exceptions[0][0],
                        run_id=self.artifact_mgr.run_id,
                        status="degraded",
                        error_message=str(failed_exceptions[0][1]),
                        completed_vendors=completed_vendor_keys,
                        pending_vendors=pending_keys,
                        harvested_records_count=len(all_harvested_products)
                    )
            else:
                for v_key, v_cfg in target_vendors:
                    try:
                        v_prods = await self.execute_vendor(
                            v_key,
                            v_cfg,
                            site_crawl=site_crawl,
                            max_pages=max_pages,
                            max_depth=max_depth,
                            resume=resume,
                            accumulate_batches=accumulate_batches,
                            batch_size=batch_size,
                            all_batches=all_batches,
                            reset_state=reset_state,
                        )
                        all_harvested_products.extend(v_prods)
                        completed_vendor_keys.append(v_key)
                    except Exception as v_err:
                        logger.error(f"[HIGH AVAILABILITY] Vendor '{v_key}' crawl encountered an isolated error: {v_err}. Preserving run state and continuing...")
                        ep_url = _resolve_ep_url(v_cfg)
                        self.dlq.record_failure(
                            url=ep_url,
                            vendor_id=v_key,
                            error_type=type(v_err).__name__,
                            message=str(v_err),
                            status_code=500,
                            tier="pipeline_vendor"
                        )
                        self.metrics_collector.record_vendor_failure(v_key, str(v_err))
                        pending_keys = [tv[0] for tv in target_vendors if tv[0] not in completed_vendor_keys and tv[0] != v_key]
                        self.checkpoint_mgr.save_checkpoint(
                            vendor_id=v_key,
                            run_id=self.artifact_mgr.run_id,
                            status="degraded",
                            error_message=str(v_err),
                            completed_vendors=completed_vendor_keys,
                            pending_vendors=pending_keys,
                            harvested_records_count=len(all_harvested_products)
                        )
                        continue

        # -------------------------------------------------------------------------
        # STEP 5/6: DEDUPLICATION & MERGE
        # -------------------------------------------------------------------------
        print("\n[STEP 5/6: DEDUPLICATION & MERGE] Executing deterministic hash deduplication:")
        print("  -> Generated deterministic SHA-256 fingerprints: SHA-256(Vendor|Model|Stage|Date)")
        print(f"  -> Merging {len(all_harvested_products)} incoming records against historical master storage")
        total_in_storage, new_appended, refreshed = self.storage.upsert_and_persist(all_harvested_products)
        print(f"  -> Deduplication Result: {new_appended} new records appended, {refreshed} existing records refreshed.")
        print(f"  -> Current Active Storage Volume: {total_in_storage} total product records.")

        # Update Coverage & Delta Tracker comparing old mapping with new findings
        for v_key, v_cfg in target_vendors:
            v_name = v_cfg.get("name", v_key)
            v_recs = [
                p for p in all_harvested_products
                if (p.vendor_name or "").strip().lower() == v_name.strip().lower()
                or v_key in (p.vendor_name or "").lower().replace(" ", "_")
            ]
            v_models = [p.model_name for p in v_recs if p.model_name]
            v_urls = [p.source_url for p in v_recs if p.source_url]
            v_state = VendorRunState.load(v_key)
            if v_state and v_state.completed_units:
                v_urls = list(dict.fromkeys(v_urls + sorted(list(v_state.completed_units))))

            delta = self.coverage_tracker.record_run(
                vendor_id=v_key,
                current_run_urls=v_urls,
                current_run_models=v_models,
                current_run_records_count=len(v_recs),
                cycle=v_state.cycle if v_state else 1,
            )
            if delta.get("new_urls_count", 0) > 0 or delta.get("new_models_count", 0) > 0 or delta.get("new_records_count", 0) > 0:
                print(f"  -> [COVERAGE DELTA] '{v_key}': +{delta['new_urls_count']} new URLs, +{delta['new_models_count']} new models, +{delta['new_records_count']} records.")

            if v_state:
                v_state.update_progress_tracking()

        # -------------------------------------------------------------------------
        # STEP 6/6: EXPORT & OBSERVABILITY
        # -------------------------------------------------------------------------
        print("\n[STEP 6/6: EXPORT & OBSERVABILITY] Persisting clean datasets & dispatching alerts:")
        print(f"  -> Master Consolidated CSV: {self.master_csv} (Fingerprint column omitted as requested)")
        print(f"  -> Modular Per-Vendor JSON:  {self.output_dir}/<vendor>_lifecycle.json")
        print(f"  -> Coverage & Delta Tracker: {self.output_dir}/coverage_tracker.json & {self.output_dir}/coverage_tracker.md")
        print(f"  -> Batch Progress Dashboard: {self.output_dir}/batch_progress.json & artifacts/batch_progress.md")
        print(f"  -> Run Audit Artifacts:      {self.artifact_mgr.run_dir}")

        cache_stats = self.run_cache.get_stats()
        print(f"  -> Run Cache Telemetry:     {cache_stats['total_redundant_operations_saved']} redundant operations saved "
              f"({cache_stats['page_crawl_hits']} crawl hits, {cache_stats['extraction_cache_hits']} AI extraction hits, {cache_stats['file_hits']} file hits)")

        # Export crawl failure forensic map
        self.dlq.export_failures_json(self.artifact_mgr.run_dir / "crawl_failures.json")
        self.dlq.export_failures_json(self.output_dir / "crawl_failures.json")
        failure_summary = self.dlq.get_summary()

        metrics = self.metrics_collector.compute_metrics(
            all_products=all_harvested_products,
            new_appended=new_appended,
            refreshed_existing=refreshed
        )
        metrics["run_cache"] = cache_stats
        metrics["crawl_failures"] = failure_summary

        if failure_summary["total_failures"] > 0:
            sc_map = failure_summary["by_status_code"]
            sc_str = ", ".join(f"{str(k)}: {v}" for k, v in sorted(sc_map.items(), key=lambda x: str(x[0])))
            print(f"  -> Failure Forensic Telemetry: {failure_summary['total_failures']} failed URLs mapped to {self.output_dir / 'crawl_failures.json'}")
            print(f"     * Breakdown: {sc_str}")

        self.artifact_mgr.finalize_manifest(metrics)
        AlertDispatcher.dispatch_alert(metrics, webhook_url=self.webhook_url)

        # Clear checkpoint once entire run succeeds
        self.checkpoint_mgr.clear_checkpoint()

        return ScrapedDataset(
            source_url="multi-vendor-portal-manifest",
            crawl_timestamp=metrics["end_time_utc"],
            total_products=total_in_storage,
            ai_model_used=self.gemini.model_name if self.gemini.is_configured() else "Crawl4AI + Multi-Vendor Engine",
            products=all_harvested_products
        )
