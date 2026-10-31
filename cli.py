"""
CLI Tool for Enterprise Multi-Vendor End of Lifecycle (EOL) AI Scraper.
Supports config-driven multi-vendor ingestion across 100 top IoT, OT, and IT vendors,
observable 6-stage execution, deep website domain crawling, deduplication,
and capability comparisons.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Configure UTF-8 encoding for Windows console compatibility
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import setup_key
from scraper.crawler_comparison import get_comparison_summary
from scraper.pipeline import LifecyclePipeline


def print_banner():
    banner = """
===================================================================================================
  ENTERPRISE MULTI-VENDOR LIFECYCLE & OBSOLESCENCE AI SCRAPER
  Framework: 140 Top Vendors (OT / IoT / IT) | Config-Driven | Zero Defaults | Append & Deduplicate
  Stages: [1] Discovery -> [2] Extraction -> [3] Normalisation -> [4] Sanitisation -> [5] Deduplication -> [6] Export
  Engine: Crawl4AI + Universal Multi-Provider AI (OpenAI, Claude, Azure, AWS Bedrock, Google, Ollama)
===================================================================================================
"""
    print(banner)


async def main():
    parser = argparse.ArgumentParser(description="Enterprise Multi-Vendor Lifecycle AI Scraper")
    parser.add_argument("--all-vendors", action="store_true", help="Run crawl across all 140 configured vendors")
    parser.add_argument("--vendor", default=None, help="Target specific vendor ID (e.g., mitsubishi, siemens, cisco_systems, intel_iot)")
    parser.add_argument("--sector", default=None, choices=["OT", "IoT", "IT", "all"], help="Filter execution by industry sector (OT, IoT, IT)")
    parser.add_argument("--site-crawl", action="store_true", default=True, help="Crawl the vendor's entire website domain rather than only specific pages (default: True)")
    parser.add_argument("--no-site-crawl", dest="site_crawl", action="store_false", help="Disable domain-level discovery crawl and target only entry-point URLs")
    parser.add_argument("--url", default=None, help="Ad-hoc website or portal URL to crawl")
    parser.add_argument("--provider", default=None, choices=["gemini", "openai", "anthropic", "claude", "azure", "aws", "bedrock", "ollama", "local", "openrouter", "auto"], help="AI Provider: gemini, openai, anthropic, azure, bedrock, ollama (default: auto-detected from environment)")
    parser.add_argument("--api-key", default=None, help="AI Provider API key (Google Gemini, OpenAI, Anthropic Claude, Azure, AWS Bedrock)")
    parser.add_argument("--api-base", default=None, help="Custom API Base URL for local models or proxies (e.g. http://localhost:11434/v1)")
    parser.add_argument("--model", default=None, help="AI Model name (default: auto-resolved based on active provider)")
    parser.add_argument("--webhook-url", default=None, help="Webhook URL for enterprise alerting (Slack/Teams)")
    parser.add_argument("--compare-modes", action="store_true", help="Display deep technical comparison between Generic IDE Crawler and AI Crawler")
    parser.add_argument("--compare-csv", nargs="+", default=None, metavar=("BASELINE", "CANDIDATE"), help="Compare legacy scraper CSV with candidate CSV (e.g. --compare-csv legacy.csv [output/all_vendors_lifecycle.csv])")
    parser.add_argument("--benchmark", action="store_true", help="Run head-to-head live benchmark between legacy scraper and Crawl4AI")
    parser.add_argument("--list-vendors", action="store_true", help="List all 140 supported enterprise vendors across OT, IoT, and IT")
    parser.add_argument("--setup-key", action="store_true", help="Launch interactive Universal Multi-Provider AI Key setup, validation, and .env configuration")
    parser.add_argument("--clean-artifacts", action="store_true", help="Purge all temporary run artifacts and orphaned temp files after review")
    parser.add_argument("--thinking-budget", type=int, default=None, help="Cap thinking token budget on Flash models (default: 0 to eliminate reasoning output token costs)")
    parser.add_argument("--prompt-caching", action="store_true", default=None, help="Enable Google Prompt Caching for repetitive site layouts (up to 90%% input discount)")
    parser.add_argument("--batch-mode", action="store_true", help="Enable Gemini Batch API for 50%% discount across both input and output tokens")
    parser.add_argument("--accumulate-batches", "--batch-crawl", dest="accumulate_batches", action="store_true", default=None, help="Accumulate all crawled page markdowns across portals before dispatching AI batch extraction (eliminates per-page latency and leverages 50%% batch discount)")
    parser.add_argument("--concurrency", type=int, default=None, help="Number of concurrent vendor crawl workers (defaults to MAX_CONCURRENT_VENDORS or 1)")
    parser.add_argument("--max-pages", type=int, default=0, help="Maximum number of website pages to crawl during site discovery (default: 0 = unlimited full site crawl)")
    parser.add_argument("--max-depth", type=int, default=0, help="Maximum link recursion depth for website network map crawling (default: 0 = unlimited depth)")
    parser.add_argument("--vendor-terminology", "--standalone-terminology", dest="vendor_terminology", action="store_true", help="Display manufacturer-exact lifecycle terminology catalog standalone (runs without crawler framework)")
    parser.add_argument("--status-registry", action="store_true", help="Display or query standalone vendor lifecycle status registry")
    parser.add_argument("--resume", action="store_true", help="Resume interrupted or failed crawl from the last saved checkpoint")
    parser.add_argument("--dlq", "--show-failures", "--failures", dest="show_failures", action="store_true", help="Inspect Dead Letter Queue (DLQ) forensic log and failure map of failed crawls")
    parser.add_argument("--retry-failures", action="store_true", help="Retry transient failed crawl requests from DLQ with resilient evasion headers and merge recovered data")
    parser.add_argument("--clear-checkpoint", action="store_true", help="Discard saved checkpoint and start fresh")
    args = parser.parse_args()

    print_banner()

    if args.vendor_terminology or args.status_registry:
        from scripts.standalone_vendor_terminology import filter_terminology, print_terminal_table
        filtered = filter_terminology(vendor_query=args.vendor, sector_query=args.sector)
        print_terminal_table(filtered)
        return

    if args.setup_key:
        setup_key.main()
        return

    if args.clean_artifacts:
        clean_kwargs = {"api_key": args.api_key, "model": args.model}
        if args.provider:
            clean_kwargs["provider"] = args.provider
        if args.api_base:
            clean_kwargs["api_base"] = args.api_base
        pipeline = LifecyclePipeline(**clean_kwargs)
        import shutil
        runs_dir = pipeline.artifacts_dir
        deleted = 0
        if runs_dir.exists():
            for item in runs_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                    deleted += 1
        tmp_cleaned = pipeline.storage.cleanup_temporary_files()
        print(f"\n[+] Successfully cleaned {deleted} run artifact directories and {tmp_cleaned} temporary files from disk.")
        return

    if args.compare_modes:
        print("\n=== TECHNICAL COMPARISON: GENERIC IDE CRAWLER vs. ENTERPRISE AI CRAWLER ===")
        print(get_comparison_summary())
        print("\n=================================================================================\n")
        return

    if args.compare_csv:
        from scraper.crawler_comparison import compare_csv_datasets, format_dataset_comparison_markdown
        baseline_file = args.compare_csv[0]
        candidate_file = args.compare_csv[1] if len(args.compare_csv) > 1 else str(Path(__file__).resolve().parent / "output" / "all_vendors_lifecycle.csv")
        summary = compare_csv_datasets(baseline_file, candidate_file)
        print("\n" + format_dataset_comparison_markdown(summary) + "\n")
        return

    if args.benchmark:
        from scraper.crawler_comparison import benchmark_url_head_to_head
        test_url = args.url or "https://ia.omron.co.jp/support/discontinued/"
        v_name = args.vendor or "Generic"
        res = benchmark_url_head_to_head(test_url, vendor=v_name)
        print("\n" + "-" * 75)
        print("  HEAD-TO-HEAD BENCHMARK RESULTS")
        print("-" * 75)
        print(f"Target URL:         {res['target_url']}")
        print(f"Legacy Latency:     {res['legacy_scraper']['elapsed_ms']} ms")
        print(f"AI Latency:         {res['crawl4ai_universal_ai']['elapsed_ms']} ms")
        print(f"Legacy Records:     {res['legacy_scraper']['records_extracted']} models")
        print(f"AI Records:         {res['crawl4ai_universal_ai']['records_extracted']} models")
        print(f"Zero-Token Bypass:  {res['crawl4ai_universal_ai']['zero_token_direct_extracted']} records parsed directly without LLM tokens")
        print(f"Tokens Saved:       ~{res['crawl4ai_universal_ai']['approx_tokens_saved']:,} tokens (${res['crawl4ai_universal_ai']['cost_saved_usd']:.5f})")
        print(f"Verdict:            {res['efficiency_verdict']}")
        print("-" * 75 + "\n")
        return

    pipeline_kwargs = {
        "api_key": args.api_key,
        "model": args.model,
        "batch_mode": args.batch_mode,
        "thinking_budget": args.thinking_budget,
        "enable_prompt_caching": args.prompt_caching,
    }
    if args.provider:
        pipeline_kwargs["provider"] = args.provider
    if args.api_base:
        pipeline_kwargs["api_base"] = args.api_base

    pipeline = LifecyclePipeline(**pipeline_kwargs)

    if args.clear_checkpoint:
        if pipeline.checkpoint_mgr.clear_checkpoint():
            print("\n[+] Checkpoint successfully cleared. Next crawl will start fresh.")
        else:
            print("\n[*] No active checkpoint found to clear.")
        return

    if getattr(args, "show_failures", False):
        summary = pipeline.dlq.get_summary()
        failures = summary.get("failures", [])
        total = summary.get("total_failures", 0)
        print(f"\n[*] Crawl Failure Forensic Telemetry ({total} Total Tracked Failures):")
        print("-" * 96)
        if total == 0:
            print("  (Zero failures recorded. All crawls succeeded with 100% availability!)")
        else:
            by_sc = summary.get("by_status_code", {})
            by_vendor = summary.get("by_vendor", {})
            sc_line = " | ".join(f"{k}: {v}" for k, v in sorted(by_sc.items()))
            print(f"  Status Code Breakdown: {sc_line}")
            top_v = ", ".join(f"{k}: {v}" for k, v in list(by_vendor.items())[:6])
            print(f"  Top Failing Vendors:   {top_v}")
            print("-" * 96)
            print(f"{'Vendor':<16} | {'Status':<6} | {'Category':<22} | URL")
            print("-" * 96)
            for it in failures[-30:]:
                sc_str = str(it.get("status_code") or "N/A")
                print(f"{it.get('vendor_id', 'unknown')[:16]:<16} | {sc_str:<6} | {it.get('error_type', 'UNKNOWN')[:22]:<22} | {it.get('url', '')}")
            print("-" * 96)
            print("  Full JSON map exported to: output/crawl_failures.json")
        return

    if getattr(args, "retry_failures", False):
        retryable = pipeline.dlq.get_retryable_failures()
        print(f"\n[*] Recovering Transient Failed Crawls ({len(retryable)} retryable failures in DLQ)...")
        if not retryable:
            print("  No retryable failures found in DLQ (all failures either empty or permanent 404s).")
            return
        recovered_records = []
        for it in retryable:
            print(f"  -> Retrying {it.url} (Prior status: {it.status_code}, Vendor: {it.vendor_id})...")
            try:
                prods = await pipeline.crawler.run(it.url)
                if prods:
                    print(f"     [SUCCESS] Recovered {len(prods)} product records from {it.url}!")
                    recovered_records.extend(prods)
                else:
                    print("     [NO DATA] URL reachable but yielded no lifecycle product tables.")
            except Exception as re_err:
                print(f"     [STILL FAILING] {re_err}")
        if recovered_records:
            total_in_storage, new_appended, refreshed = pipeline.storage.upsert_and_persist(recovered_records)
            print(f"\n[+] Retry Recovery Complete: {len(recovered_records)} records extracted ({new_appended} new, {refreshed} refreshed).")
            print(f"    Master Consolidated CSV Updated: {pipeline.master_csv}")
        else:
            print("\n[*] Retry cycle completed. Zero new records recovered.")
        return

    if args.list_vendors:
        vendors = pipeline.config.get("vendors", {})
        print(f"\n[*] Configured Vendors ({len(vendors)} Total across OT, IoT, and IT):")
        print("-" * 80)
        print(f"{'ID':<22} | {'Sector(s)':<12} | {'Vendor Name':<35} | Website")
        print("-" * 88)
        for v_id, v_cfg in vendors.items():
            sec_display = "/".join(v_cfg.get("sectors", [v_cfg.get("sector", "N/A")]))
            print(f"{v_id:<22} | {sec_display:<12} | {v_cfg.get('name', v_id):<35} | {v_cfg.get('website', '')}")
        print("-" * 88)
        print(f"Total: {len(vendors)} vendors ready for lifecycle crawling.")
        return

    if args.webhook_url:
        os.environ["WEBHOOK_URL"] = args.webhook_url

    if args.vendor:
        target_vendor = args.vendor
    elif args.all_vendors or args.sector:
        target_vendor = "all"
    else:
        target_vendor = "mitsubishi"
        print("[*] No vendor, sector, or --all-vendors specified. Running single-vendor test crawl on 'mitsubishi'.")
        print("    -> To crawl ALL 140 enterprise vendors: python cli.py --all-vendors")
        print("    -> To crawl an entire sector:           python cli.py --sector OT (or IoT, IT)")
        print("    -> To target a specific vendor:         python cli.py --vendor <vendor_id>\n")

    target_sector = args.sector

    print(f"[*] Starting Pipeline Run (Vendor Target: '{target_vendor}', Sector: '{target_sector or 'All'}', Site Crawl: {args.site_crawl}, Resume: {args.resume})...")
    exec_kwargs: dict = {
        "vendor_filter": target_vendor,
        "sector_filter": target_sector,
        "target_url": args.url,
        "site_crawl": args.site_crawl,
        "max_pages": args.max_pages,
        "max_depth": args.max_depth,
        "resume": args.resume,
    }
    if args.concurrency is not None:
        exec_kwargs["concurrency"] = args.concurrency
    if args.accumulate_batches is not None:
        exec_kwargs["accumulate_batches"] = args.accumulate_batches

    dataset = await pipeline.execute(**exec_kwargs)
    
    print("\n" + "=" * 90)
    print("[+] Pipeline Execution Completed Successfully!")
    print(f"    Total Active Records in Storage: {dataset.total_products}")
    print(f"    Master Consolidated CSV:         {pipeline.master_csv} (Fingerprint column omitted)")
    print(f"    Vendor JSON Directory:           {pipeline.output_dir}")
    print(f"    Audit Traceability Run Folder:   {pipeline.artifact_mgr.run_dir}")
    print("=" * 90)


if __name__ == "__main__":
    asyncio.run(main())
