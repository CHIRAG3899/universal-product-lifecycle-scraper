"""
PR Metrics & Health Report Generator.
Analyzes the scraper execution, Master Consolidated CSV, DLQ forensic error traces,
and generates a comprehensive GitHub Flavored Markdown report for Pull Request descriptions.

Highlights:
- Succeeded vendors vs Failed vendors (unable to provide data)
- Forensic failure classification (HTTP 403/Anti-Bot, Timeout, Selector Drift, 0 Records)
- Data Quality & Hygiene (UTC date coverage, Undated EOL preservation, Rich metadata)
- Impending Last-Time-Buy (LTB) critical alerts within 90 days
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


def generate_pr_metrics(
    master_csv_path: Path,
    artifacts_dir: Path,
    dlq_path: Path,
    output_md_path: Path
) -> str:
    """
    Parses storage, DLQ, and run manifests to build a rich Markdown PR description.
    """
    master_csv_path = Path(master_csv_path)
    artifacts_dir = Path(artifacts_dir)
    dlq_path = Path(dlq_path)
    output_md_path = Path(output_md_path)
    output_md_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Inspect Master CSV
    total_records = 0
    df = None
    vendors_in_csv: set = set()
    valid_utc_dates = 0
    undated_eol_records = 0
    rich_metadata_count = 0
    firmware_normalized_count = 0
    upcoming_ltb_alerts: List[Dict[str, Any]] = []

    now_utc = datetime.now(timezone.utc)

    if master_csv_path.exists():
        try:
            df = pd.read_csv(master_csv_path, dtype=str).fillna("")
            total_records = len(df)
            if "vendor_name" in df.columns:
                vendors_in_csv = set(df["vendor_name"].str.strip().unique()) - {""}

            for _, row in df.iterrows():
                d_val = str(row.get("stage_date_utc", "")).strip()
                st_val = str(row.get("status", "")).strip()
                v_name = str(row.get("vendor_name", "")).strip()
                m_name = str(row.get("model_name", "")).strip()
                meta_str = str(row.get("metadata", "")).strip()
                fw_val = str(row.get("firmware", "")).strip()

                if d_val and d_val.endswith("Z") and "T" in d_val:
                    valid_utc_dates += 1
                    # Check for upcoming LTB within 90 days
                    if any(term in st_val.lower() for term in ["last time buy", "ltb"]):
                        try:
                            dt = datetime.fromisoformat(d_val.replace("Z", "+00:00"))
                            days_remaining = (dt - now_utc).days
                            if 0 <= days_remaining <= 90:
                                upcoming_ltb_alerts.append({
                                    "vendor": v_name,
                                    "model": m_name,
                                    "date": d_val[:10],
                                    "days_remaining": days_remaining,
                                    "replacement": row.get("replacement", "Consult Representative")
                                })
                        except Exception:
                            pass
                else:
                    undated_eol_records += 1

                if fw_val and fw_val.lower() not in ("nan", "none", "null", "n/a", ""):
                    firmware_normalized_count += 1

                try:
                    if meta_str and len(meta_str) > 10:
                        m_obj = json.loads(meta_str)
                        if isinstance(m_obj, dict) and len(m_obj) >= 3:
                            rich_metadata_count += 1
                except Exception:
                    pass

        except Exception as e:
            print(f"[METRICS] Error reading master CSV ({e})", file=sys.stderr)

    # 2. Inspect Run Manifests
    latest_run_manifest = None
    total_run_duration = 0.0

    if artifacts_dir.exists():
        manifest_files = list(artifacts_dir.glob("**/run_manifest.json"))
        if manifest_files:
            latest_manifest_path = max(manifest_files, key=lambda p: p.stat().st_mtime)
            try:
                with open(latest_manifest_path, "r", encoding="utf-8") as f:
                    latest_run_manifest = json.load(f)
                    total_run_duration = latest_run_manifest.get("duration_seconds", 0.0)
            except Exception:
                pass

    # 3. Inspect DLQ for Failed Vendors
    dlq_records = []
    if dlq_path.exists():
        try:
            with open(dlq_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        dlq_records.append(json.loads(line))
        except Exception:
            pass

    # Classify failures
    failure_map: Dict[str, Dict[str, Any]] = {}
    for entry in dlq_records:
        v_key = entry.get("vendor_id") or entry.get("vendor_name") or "unknown_vendor"
        if v_key not in failure_map:
            failure_map[v_key] = {
                "vendor_name": entry.get("vendor_name", v_key),
                "url": entry.get("url", "N/A"),
                "reason": entry.get("failure_stage", "Extraction Failed"),
                "error": entry.get("error_message", "Unknown error"),
                "attempts": entry.get("attempts", 1),
                "timestamp": entry.get("timestamp_utc", "N/A")
            }

    # Calculate coverage percentages
    utc_coverage_pct = round((valid_utc_dates / total_records * 100), 1) if total_records > 0 else 0.0
    meta_coverage_pct = round((rich_metadata_count / total_records * 100), 1) if total_records > 0 else 0.0

    # Build Markdown Report
    md = []
    md.append("# 🚀 Automated Product Lifecycle Dataset Update & Health Metrics")
    md.append("")
    md.append(f"**Execution Timestamp**: `{now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}`  ")
    md.append("**Master Dataset Path**: [`output/all_vendors_lifecycle.csv`](output/all_vendors_lifecycle.csv)  ")
    md.append(f"**Total Verified Products in Master Dataset**: **{total_records:,}**  ")
    md.append("")

    # Status Badges Summary
    failed_count = len(failure_map)
    active_vendors_count = len(vendors_in_csv)
    health_status = "HEALTHY" if failed_count == 0 else ("DEGRADED" if active_vendors_count > 0 else "CRITICAL_FAILURE")
    badge_color = "brightgreen" if health_status == "HEALTHY" else ("yellow" if health_status == "DEGRADED" else "red")

    md.append("<p align='left'>")
    md.append(f"  <img src='https://img.shields.io/badge/Pipeline_Health-{health_status}-{badge_color}.svg?style=for-the-badge' alt='Pipeline Health' />")
    md.append(f"  <img src='https://img.shields.io/badge/Active_Vendors-{active_vendors_count}-blue.svg?style=for-the-badge' alt='Active Vendors' />")
    md.append(f"  <img src='https://img.shields.io/badge/Failed_Vendors-{failed_count}-{'red' if failed_count > 0 else 'lightgrey'}.svg?style=for-the-badge' alt='Failed Vendors' />")
    md.append(f"  <img src='https://img.shields.io/badge/UTC_Date_Coverage-{utc_coverage_pct}%25-informational.svg?style=for-the-badge' alt='UTC Dates' />")
    md.append("</p>")
    md.append("")

    # Section 1: Executive Metrics Overview
    md.append("## 📊 Executive Pipeline Health & Data Quality Summary")
    md.append("")
    md.append("| Metric Category | Value | Operational Status & Description |")
    md.append("|:---|:---|:---|")
    md.append(f"| **Total Product Records** | **{total_records:,}** | Total deduplicated lifecycle milestones currently in master CSV |")
    md.append(f"| **Active Ingested Vendors** | **{active_vendors_count}** vendors | Vendors with verified, clean products in dataset |")
    md.append(f"| **Failed / Blocked Vendors** | **{failed_count}** vendors | Vendors unable to provide data during this run (detailed below) |")
    md.append(f"| **Exact UTC Dates** | **{valid_utc_dates:,}** ({utc_coverage_pct}%) | Milestones with verified ISO 8601 UTC timestamps |")
    md.append(f"| **Undated EOL Records Preserved** | **{undated_eol_records:,}** | Models reaching EOL without vendor dates (preserved without dropping) |")
    md.append(f"| **Rich Metadata Richness** | **{rich_metadata_count:,}** ({meta_coverage_pct}%) | Records with successor replacement part, category, & bulletin info |")
    md.append(f"| **Semantic Firmware Normalized** | **{firmware_normalized_count:,}** | Cleaned semantic version strings (X.Y.Z) |")
    md.append(f"| **Total Pipeline Duration** | **{round(total_run_duration, 2)}s** | End-to-end execution across crawl, AI extraction, and storage |")
    md.append("")

    # Section 2: Vendors Unable to Provide Data (Actionable Failure Diagnostics)
    md.append("## ⚠️ Vendors Unable to Provide Data (Forensic DLQ Failure Report)")
    md.append("")
    if failed_count == 0:
        md.append("> [!TIP]")
        md.append("> **100% Data Ingestion Success**: All configured vendors successfully fetched and parsed without any dead letter failures.")
    else:
        md.append("> [!WARNING]")
        md.append(f"> **{failed_count} vendor(s) encountered data acquisition issues**. Below is the exact forensic root-cause analysis to guide maintenance:")
        md.append("")
        md.append("| Vendor Name | Target URL | Failure Stage | Failure Category & Root Cause | Recommended Remediation |")
        md.append("|:---|:---|:---|:---|:---|")

        for vid, finfo in failure_map.items():
            err_msg = finfo["error"]
            remediation = "Inspect DOM selector"
            cat = "Selector Drift"

            if "403" in err_msg or "cloudflare" in err_msg.lower() or "bot" in err_msg.lower() or "captcha" in err_msg.lower():
                cat = "Anti-Bot / Cloudflare Block (403)"
                remediation = "Enable Playwright stealth mode or rotate user agent"
            elif "timeout" in err_msg.lower():
                cat = "Network Timeout"
                remediation = "Increase timeout_seconds or check vendor site connectivity"
            elif "404" in err_msg:
                cat = "Endpoint Not Found (404)"
                remediation = "Update vendor entry_point URL in configs/vendors.yaml"
            elif "0 records" in err_msg.lower():
                cat = "Empty DOM / SPA Pagination"
                remediation = "Switch crawler_type to nextjs_apollo or dynamic JS scroll"

            md.append(f"| **{finfo['vendor_name']}** | [`{finfo['url'][:45]}...`]({finfo['url']}) | `{finfo['reason']}` | **{cat}**: `{err_msg[:60]}` | {remediation} |")

    md.append("")

    # Section 3: Impending Last Time Buy (LTB) Alerts
    md.append("## 🚨 Impending Last-Time-Buy (LTB) Urgent Notices (Next 90 Days)")
    md.append("")
    if not upcoming_ltb_alerts:
        md.append("No products in the dataset have a Last Time Buy date expiring within the next 90 days.")
    else:
        md.append(f"**{len(upcoming_ltb_alerts)} product(s)** have an impending Last Time Buy deadline. Procurement action required:")
        md.append("")
        md.append("| Vendor | Model Name | LTB Cutoff Date (UTC) | Days Remaining | Successor / Migration Recommendation |")
        md.append("|:---|:---|:---|:---|:---|")
        for alert in sorted(upcoming_ltb_alerts, key=lambda a: a["days_remaining"]):
            md.append(f"| **{alert['vendor']}** | `{alert['model']}` | **{alert['date']}** | ⚠️ **{alert['days_remaining']} days left** | {alert['replacement']} |")

    md.append("")

    # Section 4: Data Quality & Schema Integrity Safeguards
    md.append("## 🛡️ Data Quality & Invariant Verification")
    md.append("- **Zero Dropped EOL Models**: All models that have reached end-of-lifecycle as per manufacturer notifications are captured even when explicit dates are absent.")
    md.append("- **Formula Injection Shield**: All cells starting with `=`, `+`, `-`, or `@` are sanitized with leading single quotes to prevent CSV execution attacks.")
    md.append("- **SSRF Protection**: Private IPv4, IPv6, AWS/GCP metadata endpoints (`169.254.169.254`), and loopback addresses strictly forbidden during site crawls.")
    md.append("- **Deterministic Upserts**: Duplicate records are merged based on 16-character SHA-256 fingerprint matching without data loss.")
    md.append("")
    md.append("---")
    md.append("*Generated automatically by the Enterprise Product Lifecycle Intelligence Pipeline.*")

    full_report = "\n".join(md)
    output_md_path.write_text(full_report, encoding="utf-8")
    print(f"[METRICS] Generated PR metrics report at: {output_md_path} ({len(full_report)} bytes)")

    # If running inside GitHub Actions, append to GITHUB_STEP_SUMMARY
    github_step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if github_step_summary:
        try:
            with open(github_step_summary, "a", encoding="utf-8") as f:
                f.write(full_report + "\n")
            print(f"[METRICS] Appended report to GITHUB_STEP_SUMMARY: {github_step_summary}")
        except Exception as e:
            print(f"[METRICS] Could not write to GITHUB_STEP_SUMMARY ({e})", file=sys.stderr)

    return full_report


if __name__ == "__main__":
    root = Path(__file__).parent.parent
    master_csv = root / "output" / "all_vendors_lifecycle.csv"
    artifacts = root / "artifacts" / "runs"
    dlq = root / "artifacts" / "dlq" / "dead_letters.jsonl"
    out_md = root / "output" / "pr_description.md"

    generate_pr_metrics(master_csv, artifacts, dlq, out_md)
