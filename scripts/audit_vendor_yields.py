#!/usr/bin/env python3
"""
Audit script analyzing vendor yield, crawl errors, entry point strategies,
and sitemap availability across all 219 configured vendors.
"""

import csv
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("vendor_audit")

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "configs" / "vendors.yaml"
V16_PATH = BASE_DIR / "configs" / "vendors_lifecycle_enriched_v16.yaml"
ACTIVE_CSV = BASE_DIR / "output" / "active_products_lifecycle.csv"
EOL_CSV = BASE_DIR / "output" / "eol_products_lifecycle.csv"


def run_audit():
    # 1. Load CSV record counts
    vendor_counts: Counter[str] = Counter()
    for path in [ACTIVE_CSV, EOL_CSV]:
        if path.exists():
            with open(path, "r", encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    v = r.get("vendor_name", "").strip()
                    if v:
                        vendor_counts[v] += 1

    # 2. Load configs
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        curr_vendors = yaml.safe_load(f).get("vendors", {})
    with open(V16_PATH, "r", encoding="utf-8") as f:
        v16_vendors = yaml.safe_load(f).get("vendors", {})

    logger.info(f"Total current vendors configured: {len(curr_vendors)}")

    zero_records: List[Dict[str, Any]] = []
    under_100: List[Dict[str, Any]] = []
    one_hundred_to_1000: List[Dict[str, Any]] = []
    over_1000: List[Dict[str, Any]] = []

    audit_results: Dict[str, Any] = {
        "summary": {},
        "zero_records": zero_records,
        "under_100": under_100,
        "100_to_1000": one_hundred_to_1000,
        "over_1000": over_1000,
    }

    for v_id, v_info in curr_vendors.items():
        name = v_info.get("name", "")
        cnt = vendor_counts.get(name, 0)
        if cnt == 0:
            for csv_v, c in vendor_counts.items():
                if v_id in csv_v.lower().replace(" ", "_").replace("-", "_") or name.lower() in csv_v.lower():
                    cnt = c
                    break

        eps = v_info.get("entry_points", [])
        v16_eps = v16_vendors.get(v_id, {}).get("entry_points", [])

        # Categorize strategies
        strategies = [str(ep.get("strategy")) for ep in eps]
        has_sitemap = any(
            "sitemap" in str(ep.get("strategy", "")).lower()
            or "sitemap" in str(ep.get("crawler_type", "")).lower()
            or str(ep.get("url", "")).endswith((".xml", ".xml.gz"))
            for ep in eps
        )

        entry_point_details = []
        for ep in eps:
            entry_point_details.append({
                "name": ep.get("name"),
                "url": ep.get("url"),
                "strategy": ep.get("strategy"),
                "crawler_type": ep.get("crawler_type"),
                "recommended_crawler_type": ep.get("recommended_crawler_type"),
            })

        info = {
            "id": v_id,
            "name": name,
            "count": cnt,
            "sector": v_info.get("sector", ""),
            "category": v_info.get("category", ""),
            "has_sitemap_configured": has_sitemap,
            "curr_ep_count": len(eps),
            "v16_ep_count": len(v16_eps),
            "strategies": list(set(strategies)),
            "entry_points": entry_point_details,
            "website": v_info.get("website", ""),
        }

        if cnt == 0:
            zero_records.append(info)
        elif cnt < 100:
            under_100.append(info)
        elif cnt < 1000:
            one_hundred_to_1000.append(info)
        else:
            over_1000.append(info)

    audit_results["summary"] = {
        "total_configured_vendors": len(curr_vendors),
        "zero_records_vendors_count": len(audit_results["zero_records"]),
        "under_100_vendors_count": len(audit_results["under_100"]),
        "100_to_1000_vendors_count": len(audit_results["100_to_1000"]),
        "over_1000_vendors_count": len(audit_results["over_1000"]),
        "total_harvested_records": sum(vendor_counts.values())
    }

    out_json = BASE_DIR / "output" / "vendor_yield_audit.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(audit_results, f, indent=2)

    logger.info("Audit completed:")
    logger.info(f"  Zero records: {len(audit_results['zero_records'])}")
    logger.info(f"  Under 100 records: {len(audit_results['under_100'])}")
    logger.info(f"  100 to 1000 records: {len(audit_results['100_to_1000'])}")
    logger.info(f"  Over 1000 records: {len(audit_results['over_1000'])}")
    logger.info(f"  Wrote report to {out_json}")


if __name__ == "__main__":
    run_audit()
