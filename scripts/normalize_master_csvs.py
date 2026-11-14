#!/usr/bin/env python3
"""
Master Dataset Canonical Status Normalization & Deduplication Pass.

Applies User Directives 11 & 12:
1. Canonical Status Normalization: Normalizes raw vendor terminology to 6 canonical ENUM statuses
   (Active, Active Mature, Phase Out, End of Sale, End of Support, Obsolete).
2. Deduplication with Latest Date Retention: Ensures that for each normalized status,
   there is strictly ONE record per vendor + model combination, keeping the record
   with the latest date and merging non-empty aliases, replacements, and metadata.
3. OS Extraction & Model Cleansing: Separates OS versions (e.g. Apple iOS, macOS) from model names
   into the 'os' column and sets category to 'Software - OS'.
4. Synchronizes SQLite staging buffer (output/staging_buffer.db) and per-vendor JSON files.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.models import (
    classify_hardware_or_software,
    compare_and_select_latest_record,
    normalize_to_canonical_status,
    parse_to_utc_iso,
    resolve_fallback_stage_date,
)
from scraper.storage import SQLiteStagingBuffer, is_eol_status, sanitize_csv_cell

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def normalize_master_datasets():
    eol_path = BASE_DIR / "output" / "eol_products_lifecycle.csv"
    act_path = BASE_DIR / "output" / "active_products_lifecycle.csv"
    output_dir = BASE_DIR / "output"

    if not eol_path.exists() and not act_path.exists():
        logger.error("Master dual CSVs not found in output/")
        return

    eol_df = pd.read_csv(eol_path, dtype=str, keep_default_na=False) if eol_path.exists() else pd.DataFrame()
    act_df = pd.read_csv(act_path, dtype=str, keep_default_na=False) if act_path.exists() else pd.DataFrame()

    combined_df = pd.concat([eol_df, act_df], ignore_index=True)
    total_input = len(combined_df)
    logger.info(f"Loaded {total_input} total records from dual CSVs.")

    # 1. OS Extraction and Model Cleansing
    fixed_os_count = 0
    records_to_dedup: Dict[str, Dict[str, Any]] = {}

    for _, row in combined_df.iterrows():
        row_dict = row.to_dict()
        v_name = (row_dict.get("vendor_name") or "").strip()
        m_name = (row_dict.get("model_name") or "").strip()
        raw_status = (row_dict.get("status") or "").strip()
        d_utc = (row_dict.get("stage_date_utc") or "").strip()
        os_val = (row_dict.get("os") or "").strip()
        cat_val = (row_dict.get("category") or "").strip()

        # Classify hardware or software OS
        prod_class, ext_os = classify_hardware_or_software(v_name, m_name, os_name=os_val, category=cat_val)
        if ext_os and not os_val:
            row_dict["os"] = ext_os
            os_val = ext_os
            fixed_os_count += 1
        if prod_class and prod_class != "Hardware" and cat_val in ("IT", "OT", "IoT", "General Automation", ""):
            row_dict["category"] = prod_class
            cat_val = prod_class

        # Canonical status normalization
        c_status = normalize_to_canonical_status(raw_status, v_name)
        row_dict["status"] = c_status
        row_dict["canonical_status"] = c_status

        # Date normalization & fallback guarantee
        if d_utc and d_utc.lower() not in ("n/a", "none", "null", "nan", ""):
            parsed_d = parse_to_utc_iso(d_utc)
            if parsed_d:
                row_dict["stage_date_utc"] = parsed_d
            else:
                row_dict["stage_date_utc"] = resolve_fallback_stage_date(None)
        else:
            row_dict["stage_date_utc"] = resolve_fallback_stage_date(None)

        # Unique key for: (vendor_name, model_name, canonical_status)
        model_part = (m_name or os_val).strip().upper()
        dedup_key = f"{v_name.strip().upper()}|||{model_part}|||{c_status.strip().upper()}"

        if dedup_key in records_to_dedup:
            existing_rec = records_to_dedup[dedup_key]
            records_to_dedup[dedup_key] = compare_and_select_latest_record(existing_rec, row_dict)
        else:
            records_to_dedup[dedup_key] = row_dict

    deduped_records = list(records_to_dedup.values())
    purged_count = total_input - len(deduped_records)
    logger.info(f"Fixed OS in model: {fixed_os_count} rows.")
    logger.info(f"Deduplicated: {total_input} -> {len(deduped_records)} (purged {purged_count} redundant records).")

    # 2. Split into EOL and Active Datasets
    eol_records = []
    active_records = []

    expected_cols = [
        "vendor_name", "model_name", "aliases", "status", "stage_date_utc", "source_url",
        "os", "firmware", "category", "replacement", "metadata"
    ]

    for r in deduped_records:
        clean_row = {
            col: sanitize_csv_cell(str(r.get(col) or ""), col)
            for col in expected_cols
        }
        status_val = clean_row["status"]
        if is_eol_status(status_val):
            eol_records.append(clean_row)
        else:
            active_records.append(clean_row)

    # Sort deterministically by vendor, model, date
    eol_df_out = pd.DataFrame(eol_records, columns=expected_cols).sort_values(
        by=["vendor_name", "model_name", "stage_date_utc"], ascending=[True, True, False]
    )
    act_df_out = pd.DataFrame(active_records, columns=expected_cols).sort_values(
        by=["vendor_name", "model_name", "stage_date_utc"], ascending=[True, True, False]
    )

    eol_df_out.to_csv(eol_path, index=False, encoding="utf-8-sig")
    act_df_out.to_csv(act_path, index=False, encoding="utf-8-sig")
    logger.info(f"Exported EOL Master CSV: {len(eol_df_out)} rows to {eol_path.name}")
    logger.info(f"Exported Active Master CSV: {len(act_df_out)} rows to {act_path.name}")

    # 3. Populate SQLite Staging Buffer
    staging_buffer = SQLiteStagingBuffer(output_dir / "staging_buffer.db")
    staging_buffer.clear()
    staging_buffer.stage_records(deduped_records)
    logger.info(f"Synchronized SQLite Staging Buffer with {staging_buffer.count()} verified records.")

    # 4. Refresh Tracked Per-Vendor JSON files
    vendor_groups: Dict[str, list] = {}
    for r in deduped_records:
        v_name = r.get("vendor_name", "unknown")
        # Sanitize vendor name for filename
        v_slug = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in v_name).lower()
        vendor_groups.setdefault(v_slug, []).append(r)

    json_count = 0
    for v_slug, v_recs in vendor_groups.items():
        v_json_path = output_dir / f"{v_slug}_lifecycle.json"
        if v_json_path.exists():
            with open(v_json_path, "w", encoding="utf-8") as f:
                json.dump(v_recs, f, indent=2, ensure_ascii=False)
            json_count += 1
    logger.info(f"Updated {json_count} tracked per-vendor JSON files in output/.")


if __name__ == "__main__":
    normalize_master_datasets()
