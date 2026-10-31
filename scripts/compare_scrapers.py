#!/usr/bin/env python3
"""
Scraper Comparison & Benchmarking CLI Utility.
Allows users to empirically compare their existing legacy scrapers (CSV datasets or live URLs)
against the Crawl4AI + Universal Multi-Provider AI Scraper to evaluate efficiency gains,
anti-bot survival rates, token savings, model catalog coverage, and data quality.
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.crawler_comparison import (
    benchmark_url_head_to_head,
    compare_csv_datasets,
    format_dataset_comparison_markdown,
    get_comparison_summary,
)


def main():
    parser = argparse.ArgumentParser(
        description="Scraper Comparison & Benchmarking Tool: Legacy Scraper vs Universal AI Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 1. Compare legacy scraper output CSV against current AI crawler dataset:
  python scripts/compare_scrapers.py --baseline legacy_siemens.csv --candidate output/all_vendors_lifecycle.csv

  # 2. Compare and export markdown report:
  python scripts/compare_scrapers.py --baseline legacy_omron.csv --output-md comparison_report.md

  # 3. Print technical capability matrix:
  python scripts/compare_scrapers.py --matrix

  # 4. Run live head-to-head benchmark on a specific vendor URL:
  python scripts/compare_scrapers.py --benchmark --vendor mitsubishi --url "https://ia.omron.co.jp/support/discontinued/"
        """
    )
    parser.add_argument(
        "--baseline",
        type=str,
        help="Path to baseline legacy scraper CSV dataset to compare against."
    )
    parser.add_argument(
        "--candidate",
        type=str,
        default=str(BASE_DIR / "output" / "all_vendors_lifecycle.csv"),
        help="Path to candidate Crawl4AI / AI scraper CSV (defaults to output/all_vendors_lifecycle.csv)."
    )
    parser.add_argument(
        "--baseline-name",
        type=str,
        default="Legacy Scraper",
        help="Display name for baseline dataset."
    )
    parser.add_argument(
        "--candidate-name",
        type=str,
        default="Universal AI Crawler (Crawl4AI)",
        help="Display name for candidate dataset."
    )
    parser.add_argument(
        "--output-md",
        type=str,
        help="Optional file path to write Markdown comparison report."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON summary."
    )
    parser.add_argument(
        "--matrix",
        action="store_true",
        help="Display the 10-dimension architectural comparison matrix."
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run a live or synthetic head-to-head benchmark between legacy scraper and Crawl4AI."
    )
    parser.add_argument(
        "--url",
        type=str,
        help="Target URL for head-to-head benchmark."
    )
    parser.add_argument(
        "--vendor",
        type=str,
        default="Generic",
        help="Vendor identifier for benchmark."
    )

    args = parser.parse_args()

    # 1. Matrix Display
    if args.matrix:
        print("\n" + "=" * 90)
        print("  ARCHITECTURAL COMPARISON: TRADITIONAL / IDE SCRAPER vs. UNIVERSAL AI CRAWLER")
        print("=" * 90 + "\n")
        print(get_comparison_summary())
        print("\n" + "=" * 90)
        return

    # 2. Benchmark URL
    if args.benchmark:
        test_url = args.url or "https://ia.omron.co.jp/support/discontinued/"
        print(f"\n[*] Running Head-to-Head Benchmark on: {test_url} (Vendor: {args.vendor})...")
        res = benchmark_url_head_to_head(test_url, vendor=args.vendor)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
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

    # 3. CSV Dataset Comparison
    if args.baseline:
        base_path = Path(args.baseline)
        if not base_path.is_file():
            print(f"[ERROR] Baseline CSV file does not exist: {base_path}", file=sys.stderr)
            sys.exit(1)

        cand_path = Path(args.candidate)
        if not cand_path.is_file():
            print(f"[ERROR] Candidate CSV file does not exist: {cand_path}", file=sys.stderr)
            print("        Run a crawl first to generate output/all_vendors_lifecycle.csv", file=sys.stderr)
            sys.exit(1)

        print("\n[*] Comparing datasets...")
        print(f"    Baseline:  {base_path} ({args.baseline_name})")
        print(f"    Candidate: {cand_path} ({args.candidate_name})\n")

        summary = compare_csv_datasets(
            str(base_path),
            str(cand_path),
            baseline_label=args.baseline_name,
            candidate_label=args.candidate_name
        )

        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            md_report = format_dataset_comparison_markdown(summary)
            print(md_report)

        if args.output_md:
            out_p = Path(args.output_md)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            with open(out_p, "w", encoding="utf-8") as f:
                f.write(format_dataset_comparison_markdown(summary))
            print(f"\n[+] Wrote comparison markdown report to: {out_p.resolve()}")
        return

    # No arguments provided
    parser.print_help()


if __name__ == "__main__":
    main()
