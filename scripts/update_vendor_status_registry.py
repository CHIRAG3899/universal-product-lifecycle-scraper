#!/usr/bin/env python3
"""
Enterprise Vendor Lifecycle Status Registry and README Synchronizer.

Maintains and updates manufacturer-exact lifecycle terminology models and
trusted lifecycle source URLs across Operational Technology (OT),
Internet of Things (IoT), and Enterprise IT/Networking.

Automatically synchronizes and generates `configs/README.md` documentation.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Configure UTF-8 encoding for Windows console
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scripts.generate_vendor_status_registry import (
    VENDOR_STATUS_DICTIONARY,
    generate_markdown_terminology_catalog,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("update_vendor_status_registry")

README_FILE = BASE_DIR / "configs" / "README.md"


def write_readme(output_path: Path = README_FILE) -> bool:
    """Regenerates configs/README.md with manufacturer-exact terminology and trusted source URLs."""
    try:
        vendors_yaml_path = BASE_DIR / "configs" / "vendors.yaml"
        content = generate_markdown_terminology_catalog(vendors_yaml_path)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Successfully updated '{output_path}' with verified manufacturer status terminologies and trusted source URLs.")
        return True
    except Exception as e:
        logger.error(f"Failed to write README: {e}")
        return False


def get_vendor_entry(vendor_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves vendor entry from registry with case-insensitive and alias matching."""
    v_norm = vendor_id.strip().lower()
    
    # Direct match
    if v_norm in VENDOR_STATUS_DICTIONARY:
        return VENDOR_STATUS_DICTIONARY[v_norm]

    # Partial/token match
    for k, v in VENDOR_STATUS_DICTIONARY.items():
        if k == v_norm or v_norm in k or k in v_norm:
            return v
        vname = v.get("vendor", "").lower()
        if v_norm in vname:
            return v

    return None


def update_vendor_registry(
    vendor_id: str,
    lifecycle_model: Optional[str] = None,
    source_url: Optional[str] = None,
    new_status: Optional[str] = None,
    new_meaning: Optional[str] = None,
    write_to_readme: bool = True
) -> bool:
    """Updates a vendor's lifecycle terminology model, trusted source URL, or status terms."""
    entry = get_vendor_entry(vendor_id)
    if not entry:
        logger.error(f"Vendor '{vendor_id}' not found in status registry.")
        return False

    v_name = entry.get("vendor", vendor_id)

    if lifecycle_model:
        entry["lifecycle_model"] = lifecycle_model.strip()
        logger.info(f"Updated lifecycle model for '{v_name}': {lifecycle_model}")

    if source_url:
        entry["trusted_source_url"] = source_url.strip()
        logger.info(f"Updated trusted source URL for '{v_name}': {source_url}")

    if new_status:
        statuses = entry.setdefault("statuses", [])
        meaning = new_meaning or f"Manufacturer-exact status defined by {v_name}."
        
        # Check if status already exists and update, or append
        updated = False
        for s in statuses:
            if s.get("term", "").lower() == new_status.strip().lower():
                s["meaning"] = meaning
                updated = True
                break
        if not updated:
            statuses.append({"term": new_status.strip(), "meaning": meaning})
        logger.info(f"Registered status '{new_status}' for '{v_name}': {meaning}")

    if write_to_readme:
        return write_readme()

    return True


def display_vendor_status(vendor_id: str) -> None:
    """Prints vendor lifecycle status terms and trusted source URL."""
    entry = get_vendor_entry(vendor_id)
    if not entry:
        print(f"Vendor '{vendor_id}' not found in status registry.")
        return

    v_name = entry.get("vendor", vendor_id)
    sector = entry.get("sector", "")
    model = entry.get("lifecycle_model", "")
    url = entry.get("trusted_source_url", "N/A")
    statuses = entry.get("statuses", [])

    print("\n" + "=" * 70)
    print(f" 🏷️  [{sector}] {v_name}")
    print("=" * 70)
    print(f" Lifecycle Phasing Model:   {model}")
    print(f" Trusted Source URL:        {url}")
    print("-" * 70)
    print(" Exact Vendor Terminology & Operational Definitions:")
    for s in statuses:
        term = s.get("term", "")
        meaning = s.get("meaning", "")
        print(f"   • `{term}`: {meaning}")
    print("=" * 70 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enterprise Vendor Lifecycle Status Registry and README Synchronizer"
    )
    parser.add_argument(
        "--vendor", "-v",
        help="Vendor ID or name to inspect or update"
    )
    parser.add_argument(
        "--write-readme",
        action="store_true",
        help="Synchronize and rewrite configs/README.md with all 143 manufacturer-exact statuses and trusted URLs"
    )
    parser.add_argument(
        "--set-model",
        help="Update the vendor's lifecycle phasing model description"
    )
    parser.add_argument(
        "--set-source",
        help="Update the vendor's trusted lifecycle source URL"
    )
    parser.add_argument(
        "--add-status",
        help="Add or update a manufacturer-exact status term for the vendor"
    )
    parser.add_argument(
        "--meaning",
        help="Operational meaning/definition for the added status term"
    )
    parser.add_argument(
        "--list-all",
        action="store_true",
        help="List all vendors registered in the dictionary"
    )

    args = parser.parse_args()

    if args.write_readme and not (args.set_model or args.set_source or args.add_status):
        success = write_readme()
        return 0 if success else 1

    if args.list_all:
        print(f"\nRegistered Vendors in Status Dictionary ({len(VENDOR_STATUS_DICTIONARY)} total):")
        for k, v in sorted(VENDOR_STATUS_DICTIONARY.items()):
            print(f"  • {k:25s} -> [{v.get('sector')}] {v.get('vendor')} | {v.get('trusted_source_url')}")
        return 0

    if args.vendor:
        if args.set_model or args.set_source or args.add_status:
            success = update_vendor_registry(
                vendor_id=args.vendor,
                lifecycle_model=args.set_model,
                source_url=args.set_source,
                new_status=args.add_status,
                new_meaning=args.meaning,
                write_to_readme=args.write_readme or True
            )
            return 0 if success else 1
        else:
            display_vendor_status(args.vendor)
            return 0

    # Default action
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
