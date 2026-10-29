"""
Storage & State Management Module for Lifecycle Scraper.
Manages master multi-vendor CSV dataset with append/upsert logic,
per-vendor JSON datasets, and state fingerprinting.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from scraper.models import (
    ProductRecord,
    extract_date_from_bulletin_code,
    is_valid_product_model,
    is_well_known_os_or_software,
    parse_to_utc_iso,
)
from scraper.security import safe_atomic_replace, sanitize_csv_cell

logger = logging.getLogger("ai_scraper.storage")

_safe_atomic_replace = safe_atomic_replace


class MasterStorageManager:
    """
    Manages centralized data persistence:
    1. Single consolidated CSV containing all vendors with append/upsert logic.
    2. Per-vendor JSON exports for modular downstream ingestion.
    """

    def __init__(self, master_csv_path: Path, output_dir: Path):
        self.master_csv_path = Path(master_csv_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cleanup_temporary_files()

    def cleanup_temporary_files(self) -> int:
        """Purges any orphaned .tmp files in storage and output directories."""
        removed = 0
        search_dirs = list(dict.fromkeys([self.output_dir.resolve(), self.master_csv_path.parent.resolve()]))
        for d in search_dirs:
            if d.exists():
                for tmp_file in d.glob("*.tmp"):
                    try:
                        tmp_file.unlink()
                        removed += 1
                    except Exception:
                        pass
        return removed

    def load_existing_records(self) -> Dict[str, Dict[str, Any]]:
        """Loads existing records from master CSV indexed by fingerprint, filtering out any invalid rows."""
        if not self.master_csv_path.exists():
            return {}

        try:
            df = pd.read_csv(self.master_csv_path, dtype=str)
            records = {}
            for _, row in df.iterrows():
                row_dict = row.to_dict()
                fp = row_dict.get("Fingerprint") or row_dict.get("fingerprint")
                v_name = str(row_dict.get("vendor_name") or row_dict.get("Vendor Name") or "").strip()
                model = str(row_dict.get("model_name") or row_dict.get("Model Name") or "").strip()
                status = str(row_dict.get("status") or row_dict.get("Status") or row_dict.get("Stage") or row_dict.get("Vendor Status") or "").strip()
                d_utc = str(row_dict.get("stage_date_utc") or row_dict.get("Stage Date (UTC)") or "").strip()

                cat = str(row_dict.get("category") or "").strip()
                os_val = str(row_dict.get("os") or "").strip()
                is_software_or_os = is_well_known_os_or_software(category=cat, os_name=os_val, model_name=model)

                # MANDATORY INVARIANT: vendor_name, status must be non-empty and valid
                if not v_name or v_name.lower() in ("n/a", "none", "null", "nan"):
                    continue
                # For hardware, model_name is mandatory. For OS / software lifecycles, model_name may be empty.
                if not is_software_or_os:
                    if not model or model.lower() in ("n/a", "none", "null", "nan") or not is_valid_product_model(model):
                        continue
                else:
                    if model and model.lower() not in ("n/a", "none", "null", "nan") and not is_valid_product_model(model):
                        continue
                if not status or status.lower() in ("n/a", "none", "null", "nan") or len(status) > 40:
                    continue

                # MANDATORY INVARIANT: stage_date_utc must not be empty or null
                if not d_utc or d_utc.lower() in ("n/a", "none", "null", "nan", ""):
                    # Attempt date recovery from bulletin metadata
                    meta_raw = row_dict.get("metadata", "{}")
                    try:
                        meta_obj = json.loads(meta_raw) if isinstance(meta_raw, str) else {}
                        b_code = meta_obj.get("bulletin_title") or meta_obj.get("bulletin_code")
                        recovered = extract_date_from_bulletin_code(b_code)
                        if recovered:
                            d_utc = recovered
                            row_dict["stage_date_utc"] = recovered
                    except Exception:
                        pass

                # If still no valid date, REJECT AND DROP (NO NULL ALLOWED)
                if not d_utc or d_utc.lower() in ("n/a", "none", "null", "nan", ""):
                    continue

                # Ensure strict UTC ISO format (YYYY-MM-DDTHH:MM:SSZ)
                if not (d_utc.endswith("Z") and "T" in d_utc):
                    parsed_d = parse_to_utc_iso(d_utc)
                    if not parsed_d:
                        continue
                    d_utc = parsed_d
                    row_dict["stage_date_utc"] = parsed_d

                # Recompute deterministic SHA-256 hash if missing
                if not fp:
                    model_part = (model or os_val).upper()
                    key = f"{v_name.upper()}|{model_part}|{status.upper()}|{d_utc}"
                    fp = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
                    row_dict["Fingerprint"] = fp

                records[fp] = row_dict

            logger.info(f"Loaded {len(records)} verified clean records from master CSV for upsert matching.")
            return records
        except Exception as e:
            logger.warning(f"Could not read existing master CSV ({e}). Starting fresh.")
            return {}

    def upsert_and_persist(
        self,
        new_products: List[ProductRecord]
    ) -> Tuple[int, int, int]:
        """
        Merges new products into storage without overwriting existing historical data.
        Returns (total_records, new_appended, updated_existing).
        """
        existing_records = self.load_existing_records()
        new_count = 0
        updated_count = 0

        # Master record map indexed by fingerprint
        merged_map: Dict[str, Dict[str, Any]] = dict(existing_records)

        for p in new_products:
            v_name = (p.vendor_name or "").strip()
            m_name = (p.model_name or "").strip()
            status_val = (p.status or p.vendor_status or p.stage or "").strip()
            d_utc = (p.stage_date_utc or "").strip()

            # MANDATORY 4-FIELD GUARD: NO NULL / EMPTY ALLOWED
            if not v_name or v_name.lower() in ("n/a", "none", "null", "nan"):
                continue
            is_sw_os = is_well_known_os_or_software(category=p.category, os_name=p.os, model_name=m_name)
            if not is_sw_os:
                if not m_name or m_name.lower() in ("n/a", "none", "null", "nan") or not is_valid_product_model(m_name):
                    continue
            else:
                if m_name and m_name.lower() not in ("n/a", "none", "null", "nan") and not is_valid_product_model(m_name):
                    continue
            if not status_val or status_val.lower() in ("n/a", "none", "null", "nan") or len(status_val) > 40:
                continue
            if not d_utc or d_utc.lower() in ("n/a", "none", "null", "nan"):
                continue
            if not (d_utc.endswith("Z") and "T" in d_utc):
                parsed = parse_to_utc_iso(d_utc)
                if not parsed:
                    continue
                d_utc = parsed

            model_part = (m_name or p.os or "").strip().upper()
            fp = str(p.fingerprint or hashlib.sha256(f"{v_name}|{model_part}|{status_val}|{d_utc}".encode("utf-8")).hexdigest()[:16])
            meta = dict(p.metadata or {})

            # Consolidate all secondary attributes cleanly into metadata dictionary
            if p.first_discovered_utc:
                meta["first_discovered_utc"] = p.first_discovered_utc
            if p.last_updated_utc:
                meta["last_updated_utc"] = p.last_updated_utc
            if p.stage and p.stage != status_val:
                meta["canonical_stage"] = p.stage

            source_url = p.source_url or meta.get("source_url", "")
            raw_repl = p.replacement or meta.get("replacement") or ""
            if not raw_repl or str(raw_repl).strip().lower() in ("n/a", "none", "null", "-", "--", "nan", "unknown") or any(kw in str(raw_repl).lower() for kw in ["consult", "representative", "official sales", "contact your", "sales rep"]):
                replacement = ""
            else:
                replacement = str(raw_repl).strip()
            category = p.category or p.product_category or "General Automation"

            # 10 streamlined columns in Database Snake Case as requested by user
            flat_record = {
                "Fingerprint": fp,
                "vendor_name": sanitize_csv_cell(v_name),
                "model_name": sanitize_csv_cell(m_name),
                "status": sanitize_csv_cell(status_val),
                "stage_date_utc": sanitize_csv_cell(d_utc),
                "source_url": sanitize_csv_cell(source_url),
                "os": sanitize_csv_cell(p.os or ""),
                "firmware": sanitize_csv_cell(p.firmware or ""),
                "category": sanitize_csv_cell(category),
                "replacement": sanitize_csv_cell(replacement),
                "metadata": json.dumps(meta, ensure_ascii=False)
            }

            if fp in merged_map:
                existing_rec = merged_map[fp]
                existing_repl = str(existing_rec.get("replacement") or "").strip()
                # If new replacement is empty but existing had a genuine replacement, preserve it
                if not replacement and existing_repl and not any(kw in existing_repl.lower() for kw in ["consult", "representative"]):
                    flat_record["replacement"] = existing_repl

                # Update existing record: preserve first_discovered in metadata if present
                existing_meta = {}
                try:
                    existing_meta = json.loads(existing_rec.get("metadata", "{}"))
                except Exception:
                    pass
                if "first_discovered_utc" in existing_meta:
                    meta["first_discovered_utc"] = existing_meta["first_discovered_utc"]
                    flat_record["metadata"] = json.dumps(meta, ensure_ascii=False)

                merged_map[fp] = flat_record
                updated_count += 1
            else:
                merged_map[fp] = flat_record
                new_count += 1

        # 1. Write Consolidated Master CSV (Drop internal 'Fingerprint' from CSV as required)
        df = pd.DataFrame(list(merged_map.values()))
        self.master_csv_path.parent.mkdir(parents=True, exist_ok=True)
        export_df = df.drop(columns=["Fingerprint"], errors="ignore")

        desired_columns = [
            "vendor_name",
            "model_name",
            "status",
            "stage_date_utc",
            "source_url",
            "os",
            "firmware",
            "category",
            "replacement",
            "metadata"
        ]

        if export_df.empty:
            export_df = pd.DataFrame(columns=desired_columns)
        else:
            # Strict database readiness filter: drop any row where mandatory fields are null or empty
            for col in ["vendor_name", "status", "stage_date_utc"]:
                if col in export_df.columns:
                    export_df = export_df.dropna(subset=[col])
                    export_df = export_df[~export_df[col].astype(str).str.strip().str.lower().isin(["", "nan", "none", "null", "n/a"])]

            # model_name must be non-empty unless software/well-known OS
            if "model_name" in export_df.columns:
                def _is_valid_row_model(r):
                    m = str(r.get("model_name") or "").strip()
                    c = str(r.get("category") or "").strip()
                    o = str(r.get("os") or "").strip()
                    if is_well_known_os_or_software(category=c, os_name=o, model_name=m):
                        return True if not m else (m.lower() not in ("nan", "none", "null", "n/a") and is_valid_product_model(m))
                    return bool(m and m.lower() not in ("nan", "none", "null", "n/a") and is_valid_product_model(m))

                valid_mask = export_df.apply(_is_valid_row_model, axis=1)
                export_df = export_df[valid_mask]

            ordered_cols = [c for c in desired_columns if c in export_df.columns]
            export_df = export_df[ordered_cols]

        # Atomic CSV file write to prevent data corruption
        temp_csv = self.master_csv_path.with_suffix(".tmp")
        export_df.to_csv(temp_csv, index=False, encoding="utf-8-sig")
        _safe_atomic_replace(temp_csv, self.master_csv_path)
        logger.info(f"Persisted master CSV ({len(export_df)} total records, +{new_count} new, {updated_count} refreshed, Fingerprint column excluded): {self.master_csv_path}")

        # 2. Write Per-Vendor JSON Files
        records_by_vendor: Dict[str, List[ProductRecord]] = {}
        for p in new_products:
            v_key = p.vendor_name.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("-", "_")
            if v_key not in records_by_vendor:
                records_by_vendor[v_key] = []
            records_by_vendor[v_key].append(p)

        for v_key, v_products in records_by_vendor.items():
            vendor_json_path = self.output_dir / f"{v_key}_lifecycle.json"
            
            # If vendor JSON exists, load and merge
            existing_v_list = []
            if vendor_json_path.exists():
                try:
                    with open(vendor_json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        existing_v_list = data.get("products", [])
                except Exception:
                    pass

            # Merge vendor products by fingerprint
            v_map = {item.get("fingerprint"): item for item in existing_v_list if isinstance(item, dict) and item.get("fingerprint")}
            for p in v_products:
                v_map[p.fingerprint] = p.model_dump()

            vendor_dataset = {
                "vendor_id": v_key,
                "vendor_name": v_products[0].vendor_name if v_products else "Unknown",
                "total_records": len(v_map),
                "products": list(v_map.values())
            }

            temp_json = vendor_json_path.with_suffix(".tmp")
            with open(temp_json, "w", encoding="utf-8") as f:
                json.dump(vendor_dataset, f, indent=2, ensure_ascii=False)
            _safe_atomic_replace(temp_json, vendor_json_path)
            logger.info(f"Persisted per-vendor JSON for '{v_key}' ({len(v_map)} records): {vendor_json_path}")

        return len(merged_map), new_count, updated_count
