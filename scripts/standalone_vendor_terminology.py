#!/usr/bin/env python3
"""
Standalone Vendor Lifecycle Terminology Tool.
Inspect, query, and export manufacturer-exact product lifecycle status terminology
across Operational Technology (OT), Internet of Things (IoT), and Enterprise IT/Networking.

Completely standalone: Does NOT initialize or run the crawler framework,
headless browser, network scrapers, or database persistence.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Configure UTF-8 encoding for Windows console
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scripts.generate_vendor_status_registry import (
    VENDOR_STATUS_DICTIONARY,
    generate_markdown_terminology_catalog,
)


def filter_terminology(
    vendor_query: Optional[str] = None,
    sector_query: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Filters vendor dictionary by vendor ID / substring match and sector."""
    results: Dict[str, Dict[str, Any]] = {}
    v_norm = (vendor_query or "").strip().lower()
    s_norm = (sector_query or "").strip().upper()

    for vid, vdata in VENDOR_STATUS_DICTIONARY.items():
        vname = vdata.get("vendor", vid).lower()
        vsector = vdata.get("sector", "").upper()

        if s_norm and s_norm != "ALL" and vsector != s_norm:
            continue

        if v_norm:
            if v_norm not in vid.lower() and v_norm not in vname:
                continue

        results[vid] = vdata

    return results


def print_terminal_table(data: Dict[str, Dict[str, Any]]) -> None:
    """Formats and prints vendor terminology in a clean terminal table."""
    if not data:
        print("\nNo matching vendor lifecycle terminology found.")
        return

    print("\n" + "=" * 96)
    print("  STANDALONE VENDOR LIFECYCLE STATUS TERMINOLOGY CATALOG")
    print("  Manufacturer-exact lifecycle milestones & operational impacts (Zero Framework Required)")
    print("=" * 96)

    for vid, vdata in data.items():
        vendor_name = vdata.get("vendor", vid)
        sector = vdata.get("sector", "N/A")
        model = vdata.get("lifecycle_model", "Standard Multi-Phase")
        statuses: List[Dict[str, str]] = vdata.get("statuses", [])

        print(f"\n[VENDOR] {vendor_name} ({sector})")
        print(f"  Lifecycle Model: {model}")
        print(f"  Total Milestone Stages: {len(statuses)}")
        print("  " + "-" * 90)
        print(f"  {'Stage Term':<38} | {'Operational Definition & Impact':<50}")
        print("  " + "-" * 90)

        for s in statuses:
            term = s.get("term", "")
            meaning = s.get("meaning", "")
            print(f"  {term:<38} | {meaning}")
        print("  " + "-" * 90)


def main():
    parser = argparse.ArgumentParser(
        description="Standalone Vendor Lifecycle Status Terminology Catalog (Runs without crawler framework)"
    )
    parser.add_argument("--vendor", "-v", default=None, help="Target vendor name or ID (e.g. rockwell, siemens, schneider, cisco, abb, omron)")
    parser.add_argument("--sector", "-s", default=None, choices=["OT", "IoT", "IT", "all", "ALL"], help="Filter by sector (OT, IoT, IT)")
    parser.add_argument("--json", action="store_true", help="Output catalog as formatted JSON")
    parser.add_argument("--markdown", "-m", action="store_true", help="Output catalog as Markdown documentation")
    parser.add_argument("--export", "-e", default=None, help="Export output to specified file path (.md or .json)")
    args = parser.parse_args()

    filtered = filter_terminology(vendor_query=args.vendor, sector_query=args.sector)

    if args.markdown:
        yaml_p = BASE_DIR / "configs" / "vendors.yaml"
        content = generate_markdown_terminology_catalog(yaml_p)
        if args.export:
            Path(args.export).write_text(content, encoding="utf-8")
            print(f"Exported Markdown catalog to {args.export}")
        else:
            print(content)
        return 0

    if args.json:
        out_json = json.dumps(filtered, indent=2, ensure_ascii=False)
        if args.export:
            Path(args.export).write_text(out_json, encoding="utf-8")
            print(f"Exported JSON catalog to {args.export}")
        else:
            print(out_json)
        return 0

    print_terminal_table(filtered)

    if args.export:
        out_json = json.dumps(filtered, indent=2, ensure_ascii=False)
        Path(args.export).write_text(out_json, encoding="utf-8")
        print(f"\nExported {len(filtered)} vendor terminology definitions to {args.export}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
