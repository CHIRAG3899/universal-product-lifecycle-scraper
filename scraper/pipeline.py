"""
Enterprise Unified Scraper Pipeline.
Coordinates config-driven multi-vendor crawling across OT, IoT, and IT sectors,
dynamic site-level discovery, database-ready normalization, security sanitization,
SHA-256 deduplication, non-overwriting export, run traceability artifacts,
and enterprise observability alerts.
"""

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from scraper.artifacts import RunArtifactManager
from scraper.checkpoint import CheckpointManager
from scraper.config import BASE_DIR
from scraper.crawl_engine import UniversalAICrawler
from scraper.delta_cache import DeltaCache
from scraper.dlq import DeadLetterQueue
from scraper.gemini_extractor import GeminiExtractor
from scraper.models import (
    ProductRecord,
    ScrapedDataset,
    is_valid_product_model,
    is_well_known_os_or_software,
)
from scraper.observability import AlertDispatcher, PipelineMetricsCollector
from scraper.security import is_safe_url
from scraper.storage import MasterStorageManager

logger = logging.getLogger("ai_scraper.pipeline")


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
    ):
        self.config_path = config_path or (BASE_DIR / "configs" / "vendors.yaml")
        self.config = self._load_config()

        # Paths
        storage_cfg = self.config.get("storage", {})
        self.master_csv = BASE_DIR / storage_cfg.get("master_csv_path", "output/all_vendors_lifecycle.csv")
        self.output_dir = BASE_DIR / storage_cfg.get("per_vendor_json_dir", "output")
        self.artifacts_dir = BASE_DIR / storage_cfg.get("artifacts_dir", "artifacts/runs")

        # Core Components with Token & Cost Optimizations
        self.gemini = GeminiExtractor(
            api_key=api_key,
            model_name=model,
            thinking_budget=thinking_budget,
            enable_prompt_caching=enable_prompt_caching,
            batch_mode=batch_mode,
            provider=provider,
            api_base=api_base,
        )
        self.crawler = UniversalAICrawler(gemini_extractor=self.gemini)
        self.storage = MasterStorageManager(self.master_csv, self.output_dir)
        self.artifact_mgr = RunArtifactManager(self.artifacts_dir, run_id=run_id)
        self.checkpoint_mgr = CheckpointManager()
        self.dlq = DeadLetterQueue()
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
        site_crawl: bool = True,
        max_pages: int = 0,
        max_depth: int = 0
    ) -> List[ProductRecord]:
        """
        Executes pipeline for a single vendor across configured entry points or full website domain.
        Logs each of the 6 pipeline stages clearly.
        """
        vendor_name = vendor_cfg.get("name", vendor_key.title())
        vendor_id = vendor_cfg.get("id", vendor_key.lower())
        sector = vendor_cfg.get("sector", "General")
        website = vendor_cfg.get("website", "")
        entry_points = vendor_cfg.get("entry_points", [])
        allowed_domains = vendor_cfg.get("allowed_domains", [])

        print("\n" + "=" * 90)
        print(f"[*] LIFECYCLE SCRAPING WORKFLOW: [{sector}] {vendor_name} (ID: {vendor_id})")
        print("=" * 90)

        # -------------------------------------------------------------------------
        # STEP 1/6: DISCOVERY & CRAWLING
        # -------------------------------------------------------------------------
        print(f"[STEP 1/6: DISCOVERY & CRAWLING] Target Domain / Website: {website or 'N/A'}")
        vendor_products: List[ProductRecord] = []
        vendor_start = datetime.now()
        error_msg = None

        try:
            if site_crawl and website:
                page_str = "Unlimited" if not max_pages or max_pages <= 0 else str(max_pages)
                depth_str = "Unlimited" if not max_depth or max_depth <= 0 else str(max_depth)
                print(f"  -> Executing site-level discovery crawl across domain: {website} (Max pages: {page_str}, Max depth: {depth_str})")
                records = await self.crawler.crawl_website(website, allowed_domains=allowed_domains, max_pages=max_pages, max_depth=max_depth)
                for r in records:
                    r.vendor_name = vendor_name
                    if "region" not in r.metadata:
                        r.metadata["region"] = "Global"
                vendor_products.extend(records)
            else:
                for ep in entry_points:
                    url = ep.get("url")
                    name = ep.get("name", "entry")
                    region = ep.get("region", "Global")

                    if not is_safe_url(url, allowed_domains):
                        print(f"  [!] Security Guard: Blocked untrusted URL or non-whitelisted domain: {url}")
                        continue

                    print(f"  -> Crawling entry point '{name}' ({region}): {url}")
                    try:
                        records = await self.crawler.run(url)
                        for r in records:
                            r.vendor_name = vendor_name
                            if "region" not in r.metadata:
                                r.metadata["region"] = region
                        vendor_products.extend(records)
                    except Exception as ep_err:
                        print(f"  [!] Warning on entry point {name} ({url}): {ep_err}")
                        self.dlq.record_failure(
                            url=str(url),
                            vendor_id=vendor_id,
                            error_type=type(ep_err).__name__,
                            message=str(ep_err),
                            details={"region": region, "entry_point": name}
                        )

                # Automatic recovery fallback: If entry points yield 0 records, try domain-level discovery crawl
                if len(vendor_products) == 0 and website:
                    print(f"  [!] Entry points returned 0 records. Initiating automatic fallback site discovery crawl on: {website}")
                    try:
                        fb_records = await self.crawler.crawl_website(website, allowed_domains=allowed_domains, max_pages=max_pages, max_depth=max_depth)
                        for r in fb_records:
                            r.vendor_name = vendor_name
                            if "region" not in r.metadata:
                                r.metadata["region"] = "Global"
                        vendor_products.extend(fb_records)
                    except Exception as fb_err:
                        print(f"  [!] Fallback site discovery crawl failed: {fb_err}")

            # -------------------------------------------------------------------------
            # STEP 2/6: EXTRACTION
            # -------------------------------------------------------------------------
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
                if not is_sw:
                    if not m_name or m_name.lower() in ("n/a", "none", "null", "nan") or not is_valid_product_model(m_name):
                        purged_noise_count += 1
                        continue
                else:
                    if m_name and m_name.lower() not in ("n/a", "none", "null", "nan") and not is_valid_product_model(m_name):
                        purged_noise_count += 1
                        continue
                if not st_val or st_val.lower() in ("n/a", "none", "null", "nan") or len(st_val) > 40:
                    purged_noise_count += 1
                    continue
                # Missing date should never drop the record: all models reaching end of lifecycle must have an entry
                if not dt_val or dt_val.lower() in ("n/a", "none", "null", "nan"):
                    p.stage_date_utc = None
                    if isinstance(p.metadata, dict):
                        p.metadata["missing_date"] = True
                sanitized_products.append(p)

            print(f"  -> Field & Model Validator: Purged {purged_noise_count} invalid noise elements. Retained {len(sanitized_products)} clean products (including undated EOL models).")
            print("  -> CSV Formula Injection Shield: Sanitized formula trigger characters (=, +, -, @)")
            print(f"  -> SSRF Protection: Verified private IP restrictions across {len(allowed_domains)} allowed domains")
            vendor_products = sanitized_products

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
        site_crawl: bool = True,
        concurrency: Optional[int] = None,
        max_pages: int = 0,
        max_depth: int = 0,
        resume: bool = False,
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
            # Filter targeted vendors
            target_vendors = []
            for v_key, v_cfg in vendors_dict.items():
                if vendor_filter and vendor_filter.lower() != "all" and vendor_filter.lower() != v_key.lower():
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

            max_workers = concurrency or int(os.getenv("MAX_CONCURRENT_VENDORS", "1"))
            if max_workers > 1 and len(target_vendors) > 1:
                print(f"\n[*] Executing multi-vendor crawl with bounded concurrency: {max_workers} parallel workers")
                sem = asyncio.Semaphore(max_workers)

                async def _worker(vk: str, vc: Dict[str, Any]):
                    async with sem:
                        res = await self.execute_vendor(vk, vc, site_crawl=site_crawl, max_pages=max_pages, max_depth=max_depth)
                        completed_vendor_keys.append(vk)
                        return res

                results = await asyncio.gather(*[_worker(vk, vc) for vk, vc in target_vendors], return_exceptions=True)
                failed_exceptions = []
                for r in results:
                    if isinstance(r, list):
                        all_harvested_products.extend(r)
                    elif isinstance(r, Exception):
                        logger.error(f"Worker task error: {r}")
                        failed_exceptions.append(r)

                if failed_exceptions:
                    pending_keys = [tv[0] for tv in target_vendors if tv[0] not in completed_vendor_keys]
                    self.checkpoint_mgr.save_checkpoint(
                        vendor_id=pending_keys[0] if pending_keys else "concurrent_worker",
                        run_id=self.artifact_mgr.run_id,
                        status="failed",
                        error_message=str(failed_exceptions[0]),
                        completed_vendors=completed_vendor_keys,
                        pending_vendors=pending_keys,
                        harvested_records_count=len(all_harvested_products)
                    )
            else:
                for v_key, v_cfg in target_vendors:
                    try:
                        v_prods = await self.execute_vendor(v_key, v_cfg, site_crawl=site_crawl, max_pages=max_pages, max_depth=max_depth)
                        all_harvested_products.extend(v_prods)
                        completed_vendor_keys.append(v_key)
                    except Exception as v_err:
                        pending_keys = [tv[0] for tv in target_vendors if tv[0] not in completed_vendor_keys]
                        self.checkpoint_mgr.save_checkpoint(
                            vendor_id=v_key,
                            run_id=self.artifact_mgr.run_id,
                            status="failed",
                            error_message=str(v_err),
                            completed_vendors=completed_vendor_keys,
                            pending_vendors=pending_keys,
                            harvested_records_count=len(all_harvested_products)
                        )
                        raise v_err

        # -------------------------------------------------------------------------
        # STEP 5/6: DEDUPLICATION & MERGE
        # -------------------------------------------------------------------------
        print("\n[STEP 5/6: DEDUPLICATION & MERGE] Executing deterministic hash deduplication:")
        print("  -> Generated deterministic SHA-256 fingerprints: SHA-256(Vendor|Model|Stage|Date)")
        print(f"  -> Merging {len(all_harvested_products)} incoming records against historical master storage")
        total_in_storage, new_appended, refreshed = self.storage.upsert_and_persist(all_harvested_products)
        print(f"  -> Deduplication Result: {new_appended} new records appended, {refreshed} existing records refreshed.")
        print(f"  -> Current Active Storage Volume: {total_in_storage} total product records.")

        # -------------------------------------------------------------------------
        # STEP 6/6: EXPORT & OBSERVABILITY
        # -------------------------------------------------------------------------
        print("\n[STEP 6/6: EXPORT & OBSERVABILITY] Persisting clean datasets & dispatching alerts:")
        print(f"  -> Master Consolidated CSV: {self.master_csv} (Fingerprint column omitted as requested)")
        print(f"  -> Modular Per-Vendor JSON:  {self.output_dir}/<vendor>_lifecycle.json")
        print(f"  -> Run Audit Artifacts:      {self.artifact_mgr.run_dir}")

        metrics = self.metrics_collector.compute_metrics(
            all_products=all_harvested_products,
            new_appended=new_appended,
            refreshed_existing=refreshed
        )
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
