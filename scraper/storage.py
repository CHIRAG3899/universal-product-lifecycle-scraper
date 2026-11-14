"""
Storage & State Management Module for Lifecycle Scraper.
Manages master multi-vendor CSV dataset with append/upsert logic,
per-vendor JSON datasets, and state fingerprinting.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from scraper.models import (
    ProductRecord,
    extract_date_from_bulletin_code,
    is_valid_product_model,
    is_valid_replacement_model,
    is_well_known_os_or_software,
    parse_to_utc_iso,
    sanitize_alias_string,
    sanitize_replacement_string,
)
from scraper.security import safe_atomic_replace, sanitize_csv_cell

logger = logging.getLogger("ai_scraper.storage")


def is_genuine_lifecycle_record(data: Dict[str, Any]) -> bool:
    """Strict lifecycle data integrity filter rejecting sitemaps, noise, services, and home appliances."""
    def _s(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, float):
            import math
            if math.isnan(v):
                return ""
        return str(v).strip().lower()

    m_name = _s(data.get("model_name"))
    st_val = _s(data.get("status") or data.get("stage") or data.get("vendor_status"))
    cat = _s(data.get("category") or data.get("product_category"))
    src = _s(data.get("source_url"))

    disallowed_statuses = {
        "active sitemaps record", "support video published",
        "consulting services", "flexible credits", "operations offerings",
        "service program", "battery recall program", "available order"
    }
    if st_val in disallowed_statuses or "video" in st_val or "sitemap" in st_val:
        return False
    if any(kw in src for kw in ("videos", "newsroom", "professional-services")):
        return False
    if "sitemap" in m_name or m_name.endswith(".xml"):
        return False
    if any(kw in cat for kw in ("topic", "consulting", "support services", "fan", "refrigerator")):
        return False
    if any(kw in m_name for kw in ("onecare", "battery maintenance", "commissioning service", "electric fan", "ventilation fan", "battery recall")):
        return False

    return True

_safe_atomic_replace = safe_atomic_replace


def is_eol_status(status: str) -> bool:
    """
    Determines if a product status represents End of Lifecycle based on vendor terminology.
    Distinguishes active/current products from end-of-life/discontinued/retired/obsolete products.
    """
    s = str(status or "").strip().lower()
    if not s:
        return False
    # Definite active terms
    if s in ("active", "active mature", "current", "supported", "available", "delivery release", "series delivery", "regular availability"):
        return False
    import re
    if re.search(r'\bend\s+of\s+(?:[a-z]+\s+)?(?:support|service|life|sale|sales|engineering|availability|maintenance)\b', s):
        return True
    # Vendor-specific EOL / discontinued / obsolete terms
    eol_keywords = (
        "discontinued", "end of life", "eol", "end of support", "end of service",
        "end of sale", "end of engineering", "end of sw support", "last time buy",
        "ltb", "retired", "obsolete", "phase-out", "phaseout", "classic", "limited",
        "stop shipment", "end-of-service", "end-of-build", "end-of-sale", "end-of-life",
        "eosl", "repair termination", "production termination", "withdrawal",
        "abkündigung", "produktabkündigung", "auslauf", "pm400", "pm410", "pm490"
    )
    return any(k in s for k in eol_keywords)


class MasterStorageManager:
    """
    Manages centralized dual-CSV lifecycle persistence:
    1. eol_products_lifecycle.csv: Products that have reached End of Life / Discontinued / Obsolete / Phase-out.
    2. active_products_lifecycle.csv: Products that are currently Active / Supported / Available.
    3. Per-vendor JSON exports for modular downstream ingestion.
    Note: all_vendors_lifecycle.csv has been deprecated and removed per user directive.
    """

    def __init__(self, master_csv_path: Optional[Path] = None, output_dir: Optional[Path] = None):
        self.output_dir = Path(output_dir or Path("output"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.eol_csv_path = self.output_dir / "eol_products_lifecycle.csv"
        self.active_csv_path = self.output_dir / "active_products_lifecycle.csv"
        if master_csv_path and Path(master_csv_path).name != "all_vendors_lifecycle.csv":
            self.master_csv_path = Path(master_csv_path)
        else:
            self.master_csv_path = self.eol_csv_path
        self.cleanup_temporary_files()
        # Purge deprecated all_vendors_lifecycle.csv if present
        deprecated_all = self.output_dir / "all_vendors_lifecycle.csv"
        if deprecated_all.exists():
            try:
                deprecated_all.unlink()
                logger.info(f"Purged deprecated all_vendors_lifecycle.csv: {deprecated_all}")
            except Exception:
                pass

    def cleanup_temporary_files(self) -> int:
        """Purges any orphaned .tmp files in storage and output directories."""
        removed = 0
        search_dirs = list(dict.fromkeys([self.output_dir.resolve()]))
        for d in search_dirs:
            if d.exists():
                for tmp_file in d.glob("*.tmp"):
                    try:
                        tmp_file.unlink()
                        removed += 1
                    except Exception:
                        pass
        return removed

    def purge_vendor_records(self, vendor_query: str) -> int:
        """Purges all persisted rows for a vendor from both eol and active CSVs."""
        clean_q = vendor_query.lower().replace("_", "").replace("-", "").replace(" ", "")
        total_removed = 0
        for csv_path in (self.eol_csv_path, self.active_csv_path):
            if not csv_path.exists():
                continue
            try:
                df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
                if df.empty or "vendor_name" not in df.columns:
                    continue
                v_mask = df["vendor_name"].astype(str).apply(
                    lambda vn: clean_q in vn.lower().replace("_", "").replace("-", "").replace(" ", "")
                    or vn.lower().replace("_", "").replace("-", "").replace(" ", "") in clean_q
                )
                removed_count = int(v_mask.sum())
                if removed_count > 0:
                    kept_df = df[~v_mask]
                    kept_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
                    total_removed += removed_count
                    logger.info(f"[STORAGE PURGE] Removed {removed_count} stale rows for '{vendor_query}' from {csv_path.name}")
            except Exception as e:
                logger.warning(f"Error purging {vendor_query} from {csv_path}: {e}")
        return total_removed

    def load_existing_records(self) -> Dict[str, Dict[str, Any]]:
        """Loads existing records from active and eol CSVs indexed by fingerprint, filtering out any invalid rows."""
        records = {}
        source_paths = [self.eol_csv_path, self.active_csv_path]
        if self.master_csv_path.exists() and self.master_csv_path not in source_paths and self.master_csv_path.name != "all_vendors_lifecycle.csv":
            source_paths.insert(0, self.master_csv_path)
        for src_path in source_paths:
            if not src_path.exists():
                continue
            try:
                df = pd.read_csv(src_path, dtype=str, keep_default_na=False)
                for row_dict in df.to_dict("records"):
                    fp = row_dict.get("Fingerprint") or row_dict.get("fingerprint")
                    v_name = str(row_dict.get("vendor_name") or row_dict.get("Vendor Name") or "").strip()
                    model = str(row_dict.get("model_name") or row_dict.get("Model Name") or "").strip()
                    status = str(row_dict.get("status") or row_dict.get("Status") or row_dict.get("Stage") or row_dict.get("Vendor Status") or "").strip()
                    d_utc = str(row_dict.get("stage_date_utc") or row_dict.get("Stage Date (UTC)") or "").strip()
                    raw_al = str(row_dict.get("aliases") or row_dict.get("model_aliases") or "").strip()
                    aliases = "" if raw_al.lower() in ("nan", "none", "null", "n/a", "undefined") else raw_al
                    row_dict["aliases"] = aliases
                    
                    raw_repl = str(row_dict.get("replacement") or "").strip()
                    row_dict["replacement"] = "" if raw_repl.lower() in ("nan", "none", "null", "n/a", "undefined") else raw_repl

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
                        from scraper.models import strip_regional_suffix
                        clean_mod, stripped_reg = strip_regional_suffix(model)
                        if clean_mod and is_valid_product_model(clean_mod):
                            model = clean_mod
                            row_dict["model_name"] = clean_mod
                    else:
                        if model and model.lower() not in ("n/a", "none", "null", "nan") and not is_valid_product_model(model):
                            continue
                        from scraper.models import strip_regional_suffix
                        clean_mod, stripped_reg = strip_regional_suffix(model)
                        if clean_mod and is_valid_product_model(clean_mod):
                            model = clean_mod
                            row_dict["model_name"] = clean_mod
                    if not status or status.lower() in ("n/a", "none", "null", "nan") or len(status) > 40:
                        continue

                    # Date normalization: if present, ensure UTC ISO format; if missing, preserve without dropping
                    if d_utc and d_utc.lower() not in ("n/a", "none", "null", "nan", ""):
                        if not (d_utc.endswith("Z") and "T" in d_utc):
                            parsed_d = parse_to_utc_iso(d_utc)
                            if parsed_d:
                                d_utc = parsed_d
                                row_dict["stage_date_utc"] = parsed_d
                    else:
                        # Attempt date recovery from bulletin metadata
                        meta_raw = row_dict.get("metadata", "{}")
                        try:
                            meta_obj = json.loads(meta_raw) if isinstance(meta_raw, str) else {}
                            b_code = meta_obj.get("bulletin_title") or meta_obj.get("bulletin_code")
                            recovered = extract_date_from_bulletin_code(b_code)
                            if recovered:
                                d_utc = recovered
                                row_dict["stage_date_utc"] = recovered
                            else:
                                d_utc = ""
                                row_dict["stage_date_utc"] = ""
                        except Exception:
                            d_utc = ""
                            row_dict["stage_date_utc"] = ""

                    # Recompute deterministic canonical case-insensitive SHA-256 hash
                    model_part = (model or os_val).strip().upper()
                    key = f"{v_name.strip().upper()}|{model_part}|{status.strip().upper()}|{d_utc.strip()}"
                    fp = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
                    row_dict["Fingerprint"] = fp

                    if not is_genuine_lifecycle_record(row_dict):
                        continue

                    records[fp] = row_dict
            except Exception as e:
                logger.warning(f"Could not read {src_path} ({e}). Starting fresh for this source.")

        logger.info(f"Loaded {len(records)} verified clean records from dual CSVs for upsert matching.")
        return records

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
            if not is_genuine_lifecycle_record(p.model_dump()):
                continue
            v_name = (p.vendor_name or "").strip()
            m_name = (p.model_name or "").strip()
            status_val = (p.status or p.vendor_status or p.stage or "").strip()
            d_utc = (p.stage_date_utc or "").strip()

            # MANDATORY 3-FIELD GUARD: NO NULL / EMPTY ALLOWED FOR VENDOR, MODEL, STATUS
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

            # Missing date should never drop the record: all models reaching end of lifecycle must have an entry
            if d_utc and d_utc.lower() not in ("n/a", "none", "null", "nan", ""):
                if not (d_utc.endswith("Z") and "T" in d_utc):
                    parsed = parse_to_utc_iso(d_utc)
                    if parsed:
                        d_utc = parsed
            else:
                d_utc = ""

            model_part = (m_name or p.os or "").strip().upper()
            fp_key = f"{v_name.strip().upper()}|{model_part}|{status_val.strip().upper()}|{d_utc.strip()}"
            fp = hashlib.sha256(fp_key.encode("utf-8")).hexdigest()[:16]
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
            if raw_repl and is_valid_replacement_model(str(raw_repl).strip()):
                replacement = str(raw_repl).strip()
            else:
                replacement = ""
            category = p.category or p.product_category or "General Automation"

            raw_aliases = p.aliases or meta.get("aliases") or ""
            clean_aliases = str(raw_aliases).strip() if raw_aliases else ""

            # 11 streamlined columns in Database Snake Case as requested by user
            flat_record = {
                "Fingerprint": fp,
                "vendor_name": sanitize_csv_cell(v_name, "vendor_name"),
                "model_name": sanitize_csv_cell(m_name, "model_name"),
                "aliases": sanitize_csv_cell(clean_aliases, "aliases"),
                "status": sanitize_csv_cell(status_val, "status"),
                "stage_date_utc": sanitize_csv_cell(d_utc, "stage_date_utc"),
                "source_url": sanitize_csv_cell(source_url, "source_url"),
                "os": sanitize_csv_cell(p.os or "", "os"),
                "firmware": sanitize_csv_cell(p.firmware or "", "firmware"),
                "category": sanitize_csv_cell(category, "category"),
                "replacement": sanitize_csv_cell(replacement, "replacement"),
                "metadata": json.dumps(meta, ensure_ascii=False)
            }

            if fp in merged_map:
                existing_rec = merged_map[fp]
                existing_repl = str(existing_rec.get("replacement") or "").strip()
                # If new replacement is empty but existing had a genuine replacement, preserve it
                if not replacement and existing_repl and not any(kw in existing_repl.lower() for kw in ["consult", "representative"]):
                    flat_record["replacement"] = existing_repl

                # If new aliases is empty but existing had aliases, preserve it
                existing_aliases = str(existing_rec.get("aliases") or "").strip()
                if not clean_aliases and existing_aliases:
                    flat_record["aliases"] = existing_aliases

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
            "aliases",
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
            # Strict database readiness filter: drop rows where mandatory vendor or status are null/empty
            for col in ["vendor_name", "status"]:
                if col in export_df.columns:
                    export_df = export_df.dropna(subset=[col])
                    export_df = export_df[~export_df[col].astype(str).str.strip().str.lower().isin(["", "nan", "none", "null", "n/a"])]

            # Clean stage_date_utc: keep valid dates or normalize to empty string (never drop records for missing dates)
            if "stage_date_utc" in export_df.columns:
                export_df["stage_date_utc"] = export_df["stage_date_utc"].fillna("").astype(str).str.strip()
                export_df["stage_date_utc"] = export_df["stage_date_utc"].apply(
                    lambda v: "" if v.lower() in ("nan", "none", "null", "n/a", "unknown", "tbd") else v
                )

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

            # Clean string columns: purge any residual 'nan', 'none', 'null', boilerplate or date leaks
            for col in ["aliases", "replacement", "os", "firmware", "category"]:
                if col in export_df.columns:
                    export_df[col] = export_df[col].fillna("").astype(str).str.strip()
                    export_df[col] = export_df[col].apply(
                        lambda v: "" if v.lower() in ("nan", "none", "null", "n/a", "unknown", "undefined") else v
                    )

            if "replacement" in export_df.columns:
                export_df["replacement"] = export_df["replacement"].apply(
                    lambda v: sanitize_replacement_string(v) or ""
                )

            if "aliases" in export_df.columns:
                export_df["aliases"] = export_df["aliases"].apply(
                    lambda v: sanitize_alias_string(v) or ""
                )

            # Mandatory Case-Insensitive Deduplication Pass:
            # Enforce (vendor_name, model_name, status) uniqueness, prioritizing dated over undated records
            export_df = export_df.sort_values(by=["stage_date_utc"], ascending=False)
            export_df["_status_dedup_key"] = (
                export_df["vendor_name"].astype(str).str.strip().str.upper() + "|||" +
                export_df["model_name"].astype(str).str.strip().str.upper() + "|||" +
                export_df["status"].astype(str).str.strip().str.upper()
            )
            export_df = export_df.drop_duplicates(subset=["_status_dedup_key"], keep="first")
            export_df = export_df.drop(columns=["_status_dedup_key"])

            # Deterministic sorting
            sort_cols = [c for c in ["vendor_name", "model_name", "status"] if c in export_df.columns]
            if sort_cols:
                export_df = export_df.sort_values(by=sort_cols, ascending=True)

            ordered_cols = [c for c in desired_columns if c in export_df.columns]
            export_df = export_df[ordered_cols]

        # Atomic segmented CSV writes: EOL vs Active products based on vendor terminology
        # User directive: "Get rid of all vendors lifecycle csv have active and eol csv only"
        # If a model has an EOL milestone (Discontinued, End of Life, Obsolete), remove duplicate active placeholder from active_df
        if not export_df.empty and "status" in export_df.columns:
            eol_mask = export_df["status"].apply(is_eol_status)
            eol_df = export_df[eol_mask]
            active_candidate_df = export_df[~eol_mask]
            if not eol_df.empty and not active_candidate_df.empty:
                eol_keys = set(
                    (str(r.get("vendor_name", "")).strip().upper(), str(r.get("model_name", "")).strip().upper())
                    for r in eol_df.to_dict("records")
                )
                active_df = active_candidate_df[
                    ~active_candidate_df.apply(
                        lambda r: (str(r["vendor_name"]).strip().upper(), str(r["model_name"]).strip().upper()) in eol_keys,
                        axis=1
                    )
                ]
            else:
                active_df = active_candidate_df
        else:
            eol_df = pd.DataFrame(columns=desired_columns)
            active_df = pd.DataFrame(columns=desired_columns)

        temp_eol = self.eol_csv_path.with_suffix(".tmp")
        eol_df.to_csv(temp_eol, index=False, encoding="utf-8-sig")
        _safe_atomic_replace(temp_eol, self.eol_csv_path)

        temp_active = self.active_csv_path.with_suffix(".tmp")
        active_df.to_csv(temp_active, index=False, encoding="utf-8-sig")
        _safe_atomic_replace(temp_active, self.active_csv_path)

        # If a custom master_csv_path was supplied (e.g. for unit tests), persist to it as well
        if self.master_csv_path not in (self.eol_csv_path, self.active_csv_path) and self.master_csv_path.name != "all_vendors_lifecycle.csv":
            temp_custom = self.master_csv_path.with_suffix(".tmp")
            export_df.to_csv(temp_custom, index=False, encoding="utf-8-sig")
            _safe_atomic_replace(temp_custom, self.master_csv_path)

        # Ensure deprecated all_vendors_lifecycle.csv is deleted if present
        deprecated_master = self.output_dir / "all_vendors_lifecycle.csv"
        if deprecated_master.exists():
            try:
                deprecated_master.unlink()
            except Exception:
                pass

        logger.info(
            f"Persisted dual lifecycle CSVs: {len(eol_df)} EOL records -> {self.eol_csv_path}, "
            f"{len(active_df)} Active records -> {self.active_csv_path} (+{new_count} new, {updated_count} updated)"
        )

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

            # Merge vendor products by case-insensitive fingerprint, enforcing genuine lifecycle filter
            v_map = {}
            for item in existing_v_list:
                if isinstance(item, dict) and is_genuine_lifecycle_record(item):
                    m_part = (item.get("model_name") or item.get("os") or "").strip().upper()
                    v_part = str(item.get("vendor_name") or "").strip().upper()
                    s_part = str(item.get("status") or item.get("vendor_status") or item.get("stage") or "").strip().upper()
                    d_part = str(item.get("stage_date_utc") or "").strip()
                    c_key = f"{v_part}|{m_part}|{s_part}|{d_part}"
                    c_fp = hashlib.sha256(c_key.encode("utf-8")).hexdigest()[:16]
                    item["fingerprint"] = c_fp
                    v_map[c_fp] = item

            for p in v_products:
                p_dump = p.model_dump()
                if is_genuine_lifecycle_record(p_dump):
                    m_part = (p.model_name or p.os or "").strip().upper()
                    v_part = (p.vendor_name or "").strip().upper()
                    s_part = (p.status or p.vendor_status or p.stage or "").strip().upper()
                    d_part = (p.stage_date_utc or "").strip()
                    c_key = f"{v_part}|{m_part}|{s_part}|{d_part}"
                    c_fp = hashlib.sha256(c_key.encode("utf-8")).hexdigest()[:16]
                    p_dump["fingerprint"] = c_fp
                    v_map[c_fp] = p_dump

            # Deduplicate vendor products by (vendor, model, status), prioritizing dated records
            v_dedup: Dict[str, Dict[str, Any]] = {}
            for fp, item in v_map.items():
                m_part = (item.get("model_name") or item.get("os") or "").strip().upper()
                v_part = str(item.get("vendor_name") or "").strip().upper()
                s_part = str(item.get("status") or item.get("vendor_status") or item.get("stage") or "").strip().upper()
                v_key_triple = f"{v_part}|{m_part}|{s_part}"
                existing = v_dedup.get(v_key_triple)
                if not existing or (item.get("stage_date_utc") and not existing.get("stage_date_utc")):
                    v_dedup[v_key_triple] = item

            # Only persist vendor JSON if genuine records exist
            if not v_dedup:
                if vendor_json_path.exists():
                    try:
                        vendor_json_path.unlink()
                    except Exception:
                        pass
                continue

            vendor_dataset = {
                "vendor_id": v_key,
                "vendor_name": v_products[0].vendor_name if v_products else "Unknown",
                "total_records": len(v_dedup),
                "products": list(v_dedup.values())
            }

            temp_json = vendor_json_path.with_suffix(".tmp")
            with open(temp_json, "w", encoding="utf-8") as f:
                json.dump(vendor_dataset, f, indent=2, ensure_ascii=False)
            _safe_atomic_replace(temp_json, vendor_json_path)
            logger.info(f"Persisted per-vendor JSON for '{v_key}' ({len(v_map)} records): {vendor_json_path}")

        return len(merged_map), new_count, updated_count

    def split_master_csv(self) -> Tuple[int, int]:
        """
        Splits existing master CSV into separate eol_products_lifecycle.csv and active_products_lifecycle.csv.
        Returns (eol_count, active_count).
        """
        if not self.master_csv_path.exists():
            return (0, 0)
        df = pd.read_csv(self.master_csv_path, encoding="utf-8-sig", keep_default_na=False)
        if df.empty or "status" not in df.columns:
            return (0, 0)
        eol_mask = df["status"].apply(is_eol_status)
        eol_df = df[eol_mask]
        active_df = df[~eol_mask]

        temp_eol = self.eol_csv_path.with_suffix(".tmp")
        eol_df.to_csv(temp_eol, index=False, encoding="utf-8-sig")
        _safe_atomic_replace(temp_eol, self.eol_csv_path)

        temp_active = self.active_csv_path.with_suffix(".tmp")
        active_df.to_csv(temp_active, index=False, encoding="utf-8-sig")
        _safe_atomic_replace(temp_active, self.active_csv_path)

        logger.info(
            f"[LIFECYCLE SEGMENTATION] Shifted {len(df)} records into "
            f"EOL CSV ({len(eol_df)} records) and Active CSV ({len(active_df)} records)."
        )
        return (len(eol_df), len(active_df))
