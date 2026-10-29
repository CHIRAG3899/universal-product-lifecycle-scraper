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

from scraper.config import GEMINI_MODEL
from scraper.crawler_comparison import get_comparison_summary
from scraper.pipeline import LifecyclePipeline


def print_banner():
    banner = """
===================================================================================================
  ENTERPRISE MULTI-VENDOR LIFECYCLE & OBSOLESCENCE AI SCRAPER
  Framework: 140 Top Vendors (OT / IoT / IT) | Config-Driven | Zero Defaults | Append & Deduplicate
  Stages: [1] Discovery -> [2] Extraction -> [3] Normalisation -> [4] Sanitisation -> [5] Deduplication -> [6] Export
  Engine: Crawl4AI + Google Gemini (gemini-3.5-flash-lite / gemini-3.5-flash via google-genai)
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
    parser.add_argument("--api-key", default=None, help="Google Gemini API key")
    parser.add_argument("--model", default=GEMINI_MODEL, help="Gemini Model name")
    parser.add_argument("--webhook-url", default=None, help="Webhook URL for enterprise alerting (Slack/Teams)")
    parser.add_argument("--compare-modes", action="store_true", help="Display deep technical comparison between Generic IDE Crawler and AI Crawler")
    parser.add_argument("--list-vendors", action="store_true", help="List all 140 supported enterprise vendors across OT, IoT, and IT")
    parser.add_argument("--setup-key", action="store_true", help="Launch interactive Gemini API Key setup, validation, and .env configuration")
    parser.add_argument("--clean-artifacts", action="store_true", help="Purge all temporary run artifacts and orphaned temp files after review")
    parser.add_argument("--thinking-budget", type=int, default=None, help="Cap thinking token budget on Flash models (default: 0 to eliminate reasoning output token costs)")
    parser.add_argument("--prompt-caching", action="store_true", default=None, help="Enable Google Prompt Caching for repetitive site layouts (up to 90%% input discount)")
    parser.add_argument("--batch-mode", action="store_true", help="Enable Gemini Batch API for 50%% discount across both input and output tokens")
    parser.add_argument("--concurrency", type=int, default=None, help="Number of concurrent vendor crawl workers (defaults to MAX_CONCURRENT_VENDORS or 1)")
    parser.add_argument("--max-pages", type=int, default=0, help="Maximum number of website pages to crawl during site discovery (default: 0 = unlimited full site crawl)")
    parser.add_argument("--max-depth", type=int, default=0, help="Maximum link recursion depth for website network map crawling (default: 0 = unlimited depth)")
    parser.add_argument("--resume", action="store_true", help="Resume interrupted or failed crawl from the last saved checkpoint")
    parser.add_argument("--dlq", action="store_true", help="Inspect Dead Letter Queue (DLQ) forensic log of failed crawls")
    parser.add_argument("--clear-checkpoint", action="store_true", help="Discard saved checkpoint and start fresh")
    args = parser.parse_args()

    print_banner()

    if args.setup_key:
        import setup_key
        setup_key.main()
        return

    if args.clean_artifacts:
        pipeline = LifecyclePipeline(api_key=args.api_key, model=args.model)
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

    pipeline = LifecyclePipeline(
        api_key=args.api_key,
        model=args.model,
        batch_mode=args.batch_mode,
        thinking_budget=args.thinking_budget,
        enable_prompt_caching=args.prompt_caching
    )

    if args.clear_checkpoint:
        if pipeline.checkpoint_mgr.clear_checkpoint():
            print("\n[+] Checkpoint successfully cleared. Next crawl will start fresh.")
        else:
            print("\n[*] No active checkpoint found to clear.")
        return

    if args.dlq:
        failures = pipeline.dlq.get_failures()
        print(f"\n[*] Dead Letter Queue: {len(failures)} logged failure events")
        print("-" * 88)
        if not failures:
            print("  (DLQ is empty - no recorded failure events)")
        else:
            print(f"{'Vendor':<18} | {'Type':<18} | {'Status':<6} | URL")
            print("-" * 88)
            for it in failures[-20:]:
                print(f"{it.vendor_id:<18} | {it.error_type:<18} | {str(it.status_code or 'N/A'):<6} | {it.url}")
        print("-" * 88)
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
