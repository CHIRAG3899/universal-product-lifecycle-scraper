"""
Coverage and Delta Tracker Module for Universal Lifecycle Scraper.

Maintains persistent coverage state in `output/coverage_tracker.json` and
generates a human-readable markdown dashboard in `output/coverage_tracker.md`.

On each run, compares the prior mapping snapshot with newly scraped findings:
- Tracks cumulative covered URLs/entry points and harvested models.
- Calculates run-level deltas (newly discovered URLs, newly harvested models, new records).
- Preserves historical run logs so operators can audit what each run contributed.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from scraper.storage import is_eol_status

logger = logging.getLogger("ai_scraper.coverage")


class CoverageTracker:
    """
    Tracks covered URLs, discovered models, and incremental deltas across runs.
    Saves outputs directly to `output/` and mirrors to `artifacts/`.
    """

    def __init__(self, output_dir: Optional[Path] = None, artifacts_dir: Optional[Path] = None):
        self.output_dir = Path(output_dir or "output")
        self.artifacts_dir = Path(artifacts_dir or "artifacts")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        self.json_path = self.output_dir / "coverage_tracker.json"
        self.md_path = self.output_dir / "coverage_tracker.md"
        self.artifacts_json_path = self.artifacts_dir / "coverage_tracker.json"
        self.artifacts_md_path = self.artifacts_dir / "coverage_tracker.md"

        self.state: Dict[str, Any] = self._load_or_initialize()

    def _load_or_initialize(self) -> Dict[str, Any]:
        """Loads existing tracker JSON, or initializes from CSV and run_state files if first run."""
        if self.json_path.exists():
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "vendors" in data:
                        return data
            except Exception as e:
                logger.warning(f"[COVERAGE TRACKER] Error loading {self.json_path}: {e}")

        # Initialize fresh structure
        initial_state: Dict[str, Any] = {
            "version": "1.0",
            "last_updated_utc": datetime.now(timezone.utc).isoformat(),
            "global_summary": {
                "total_vendors_tracked": 0,
                "total_covered_urls": 0,
                "total_covered_models": 0,
                "total_records": 0,
                "latest_run": None,
            },
            "vendors": {},
            "history": [],
        }

        # Backfill from existing master CSV and run_state if available
        self._backfill_initial_state(initial_state)
        return initial_state

    def _canonical_vendor_key(self, vendor_str: str) -> str:
        """Resolves any vendor name or id to official vendors.yaml key."""
        v_clean = vendor_str.lower().strip()
        # Direct mappings
        name_map = {
            "cisco systems": "cisco",
            "cisco": "cisco",
            "cisco meraki": "cisco_meraki",
            "juniper networks": "juniper",
            "juniper": "juniper",
            "honeywell": "honeywell",
            "rockwell automation (allen-bradley)": "rockwell_automation",
            "rockwell automation": "rockwell_automation",
            "siemens": "siemens",
            "schneider electric": "schneider_electric",
            "abb": "abb",
            "omron corporation": "omron",
            "omron": "omron",
            "mitsubishi electric": "mitsubishi",
            "mitsubishi": "mitsubishi",
        }
        if v_clean in name_map:
            return name_map[v_clean]
        # Fallback replacement
        return v_clean.replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "").strip("_")

    def _backfill_initial_state(self, state: Dict[str, Any]) -> None:
        """Populates baseline state from existing dual CSVs and run_state directory."""
        csv_sources = [
            (self.output_dir / "eol_products_lifecycle.csv", True),
            (self.output_dir / "active_products_lifecycle.csv", False),
        ]
        csv_models_by_vendor: Dict[str, Set[str]] = {}
        csv_records_by_vendor: Dict[str, int] = {}
        csv_urls_by_vendor: Dict[str, Set[str]] = {}
        csv_eol_by_vendor: Dict[str, int] = {}
        csv_active_by_vendor: Dict[str, int] = {}

        for csv_path, is_eol_file in csv_sources:
            if csv_path.exists():
                try:
                    df = pd.read_csv(csv_path, dtype=str)
                    for _, row in df.iterrows():
                        v_raw = str(row.get("vendor_name") or "").strip()
                        m_raw = str(row.get("model_name") or "").strip()
                        u_raw = str(row.get("source_url") or "").strip()
                        s_raw = str(row.get("status") or "").strip()

                        v_key = self._canonical_vendor_key(v_raw)
                        if not v_key:
                            continue

                        if v_key not in csv_models_by_vendor:
                            csv_models_by_vendor[v_key] = set()
                            csv_records_by_vendor[v_key] = 0
                            csv_urls_by_vendor[v_key] = set()
                            csv_eol_by_vendor[v_key] = 0
                            csv_active_by_vendor[v_key] = 0

                        if m_raw:
                            csv_models_by_vendor[v_key].add(m_raw.upper())
                        if u_raw:
                            csv_urls_by_vendor[v_key].add(u_raw)
                        csv_records_by_vendor[v_key] += 1
                        if is_eol_status(s_raw) or is_eol_file:
                            csv_eol_by_vendor[v_key] += 1
                        else:
                            csv_active_by_vendor[v_key] += 1
                except Exception as e:
                    logger.warning(f"[COVERAGE TRACKER] Could not backfill from {csv_path}: {e}")

        # Check artifacts/run_state/ for completed URLs
        run_state_dir = Path("artifacts") / "run_state"
        state_urls_by_vendor: Dict[str, Set[str]] = {}
        state_cycles: Dict[str, int] = {}
        if run_state_dir.exists():
            for sf in run_state_dir.glob("*_state.json"):
                try:
                    with open(sf, "r", encoding="utf-8") as f:
                        s_data = json.load(f)
                        raw_vid = s_data.get("vendor_id", sf.stem.replace("_state", ""))
                        vid = self._canonical_vendor_key(raw_vid)
                        c_units = set(s_data.get("completed_units", []))
                        state_urls_by_vendor.setdefault(vid, set()).update(c_units)
                        state_cycles[vid] = max(state_cycles.get(vid, 1), s_data.get("cycle", 1))
                except Exception:
                    pass

        # Merge vendors (filtered strictly to real vendors in vendors.yaml)
        from scraper.vendors import _get_yaml_vendors
        valid_vendors = set(_get_yaml_vendors().keys())
        all_vids = {v for v in (set(csv_models_by_vendor.keys()) | set(state_urls_by_vendor.keys())) if v in valid_vendors}
        for vid in sorted(all_vids):
            models = sorted(list(csv_models_by_vendor.get(vid, set())))
            urls = sorted(list(csv_urls_by_vendor.get(vid, set()) | state_urls_by_vendor.get(vid, set())))
            rec_count = csv_records_by_vendor.get(vid, len(models))
            eol_cnt = csv_eol_by_vendor.get(vid, 0)
            active_cnt = csv_active_by_vendor.get(vid, rec_count - eol_cnt)

            state["vendors"][vid] = {
                "vendor_id": vid,
                "cycle": state_cycles.get(vid, 1),
                "total_covered_urls": len(urls),
                "total_covered_models": len(models),
                "total_records": rec_count,
                "eol_records_count": eol_cnt,
                "active_records_count": active_cnt,
                "has_data": bool(rec_count > 0),
                "data_status": "ACTIVE_DATA" if rec_count > 0 else "NO_DATA",
                "latest_delta": {
                    "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "newly_added_urls": urls[:20],
                    "newly_added_models_sample": models[:20],
                    "new_urls_count": len(urls),
                    "new_models_count": len(models),
                    "new_records_count": rec_count,
                },
                "covered_urls": urls,
                "covered_models": models,
            }

        self._refresh_global_summary(state)

    def _refresh_global_summary(self, state: Dict[str, Any]) -> None:
        """Recalculates totals across all vendors."""
        all_urls: Set[str] = set()
        all_models: Set[str] = set()
        total_records = 0

        for vdata in state["vendors"].values():
            all_urls.update(vdata.get("covered_urls", []))
            all_models.update(vdata.get("covered_models", []))
            total_records += vdata.get("total_records", 0)

        state["global_summary"]["total_vendors_tracked"] = len(state["vendors"])
        state["global_summary"]["total_covered_urls"] = len(all_urls)
        state["global_summary"]["total_covered_models"] = len(all_models)
        state["global_summary"]["total_records"] = total_records
        state["last_updated_utc"] = datetime.now(timezone.utc).isoformat()

    def record_run(
        self,
        vendor_id: str,
        current_run_urls: List[str],
        current_run_models: List[str],
        current_run_records_count: int,
        cycle: int = 1,
    ) -> Dict[str, Any]:
        """
        Compares old mapping with new findings for the vendor, records the delta,
        updates cumulative state, and saves both JSON and Markdown dashboards.

        Returns delta dictionary for observability.
        """
        clean_vid = self._canonical_vendor_key(vendor_id)
        from scraper.vendors import _get_yaml_vendors
        valid_vendors = set(_get_yaml_vendors().keys())
        if clean_vid not in valid_vendors and os.getenv("SCRAPER_TEST_MODE") != "1":
            return {}
        now_str = datetime.now(timezone.utc).isoformat()

        # Existing vendor mapping
        v_existing = self.state["vendors"].get(clean_vid, {})
        old_urls_set = set(u.strip().lower() for u in v_existing.get("covered_urls", []))
        old_models_set = set(m.strip().upper() for m in v_existing.get("covered_models", []))

        # Current findings
        norm_run_urls = [u.strip() for u in current_run_urls if u.strip()]
        norm_run_models = [m.strip().upper() for m in current_run_models if m.strip()]

        # Compute Deltas (What was newly added on this run)
        newly_added_urls = [
            u for u in norm_run_urls
            if u.lower() not in old_urls_set
        ]
        # Deduplicate while preserving order
        newly_added_urls = list(dict.fromkeys(newly_added_urls))

        newly_added_models = [
            m for m in norm_run_models
            if m not in old_models_set
        ]
        newly_added_models = list(dict.fromkeys(newly_added_models))

        # Update cumulative sets
        combined_urls = list(dict.fromkeys(v_existing.get("covered_urls", []) + newly_added_urls))
        combined_models = list(dict.fromkeys(v_existing.get("covered_models", []) + newly_added_models))
        new_total_records = v_existing.get("total_records", 0) + current_run_records_count

        delta_info = {
            "run_timestamp_utc": now_str,
            "newly_added_urls": newly_added_urls,
            "newly_added_models_sample": newly_added_models[:50],
            "new_urls_count": len(newly_added_urls),
            "new_models_count": len(newly_added_models),
            "new_records_count": current_run_records_count,
        }

        # Compute EOL vs Active counts from dual CSVs
        eol_cnt = 0
        active_cnt = 0
        eol_csv = self.output_dir / "eol_products_lifecycle.csv"
        active_csv = self.output_dir / "active_products_lifecycle.csv"
        v_clean_search = clean_vid.replace("_", "").replace("-", "")

        for csv_path, is_eol_file in [(eol_csv, True), (active_csv, False)]:
            if csv_path.exists():
                try:
                    df = pd.read_csv(csv_path, dtype=str)
                    v_mask = df["vendor_name"].astype(str).apply(
                        lambda vn: v_clean_search in vn.lower().replace("_", "").replace("-", "").replace(" ", "")
                        or vn.lower().replace("_", "").replace("-", "").replace(" ", "") in v_clean_search
                    )
                    v_df = df[v_mask]
                    if not v_df.empty:
                        if is_eol_file:
                            eol_cnt += len(v_df)
                        else:
                            active_cnt += len(v_df)
                except Exception:
                    pass

        # Read reconciliation audit data if available
        rec_audit_file = self.output_dir / "reconciliation_audit.json"
        rec_data: Dict[str, Any] = {}
        if rec_audit_file.exists():
            try:
                with open(rec_audit_file, "r", encoding="utf-8") as rf:
                    all_rec = json.load(rf)
                    rec_data = all_rec.get(clean_vid, {})
            except Exception:
                pass

        # Update vendor entry
        self.state["vendors"][clean_vid] = {
            "vendor_id": clean_vid,
            "cycle": cycle,
            "total_covered_urls": len(combined_urls),
            "total_covered_models": len(combined_models),
            "total_records": new_total_records,
            "eol_records_count": eol_cnt,
            "active_records_count": active_cnt,
            "cross_entrypoint_duplicates_count": rec_data.get("cross_entrypoint_duplicates_count", 0),
            "llm_rejected_count": rec_data.get("llm_rejected_count", 0),
            "reconciliation_explanation": rec_data.get("reconciliation_explanation", ""),
            "has_data": bool(new_total_records > 0),
            "data_status": "ACTIVE_DATA" if new_total_records > 0 else "NO_DATA",
            "latest_delta": delta_info,
            "covered_urls": combined_urls,
            "covered_models": combined_models,
        }

        # Record history entry (max 50 past entries)
        history_entry = {
            "timestamp_utc": now_str,
            "vendor_id": clean_vid,
            "cycle": cycle,
            "new_urls_count": len(newly_added_urls),
            "new_models_count": len(newly_added_models),
            "new_records_count": current_run_records_count,
            "cumulative_vendor_models": len(combined_models),
            "cumulative_vendor_records": new_total_records,
        }
        self.state.setdefault("history", []).append(history_entry)
        if len(self.state["history"]) > 50:
            self.state["history"] = self.state["history"][-50:]

        self.state["global_summary"]["latest_run"] = history_entry
        self._refresh_global_summary(self.state)

        # Persist files atomically
        self.save()

        logger.info(
            f"[COVERAGE TRACKER] Vendor '{clean_vid}' Delta: +{len(newly_added_urls)} new URLs, "
            f"+{len(newly_added_models)} new models, +{current_run_records_count} records. "
            f"Cumulative: {len(combined_urls)} URLs, {len(combined_models)} models, {new_total_records} records."
        )

        return delta_info

    def save(self) -> None:
        """Atomically saves coverage tracker JSON and Markdown dashboard to output/ and artifacts/."""
        # 1. Save JSON
        for target_p in (self.json_path, self.artifacts_json_path):
            tmp_p = target_p.with_suffix(".tmp")
            with open(tmp_p, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
            tmp_p.replace(target_p)

        # 2. Render and save Markdown Dashboard
        md_content = self._render_markdown()
        for target_md in (self.md_path, self.artifacts_md_path):
            tmp_md = target_md.with_suffix(".tmp")
            with open(tmp_md, "w", encoding="utf-8") as f:
                f.write(md_content)
            tmp_md.replace(target_md)

    def _render_markdown(self) -> str:
        """Generates GitHub-flavored markdown dashboard representing current coverage and deltas."""
        g = self.state["global_summary"]
        last_run = g.get("latest_run") or {}

        lines = [
            "# Multi-Vendor Lifecycle Scraper - Coverage & Delta Tracker",
            "",
            f"> **Last Synchronized:** `{self.state.get('last_updated_utc', 'N/A')}`",
            "",
            "## 1. Global Coverage Summary",
            "",
            f"- **Total Vendors Monitored:** `{g.get('total_vendors_tracked', 0)}`",
            f"- **Total Covered Endpoints/URLs:** `{g.get('total_covered_urls', 0):,}`",
            f"- **Total Unique Models Harvested:** `{g.get('total_covered_models', 0):,}`",
            f"- **Total Master Records:** `{g.get('total_records', 0):,}`",
        ]

        if last_run:
            lines.extend([
                f"- **Latest Run Vendor:** `{last_run.get('vendor_id')}` (Cycle {last_run.get('cycle', 1)})",
                f"- **Latest Run Delta:** `+{last_run.get('new_urls_count', 0)}` new URLs, "
                f"`+{last_run.get('new_models_count', 0)}` new models, `+{last_run.get('new_records_count', 0)}` records",
            ])

        lines.extend([
            "",
            "---",
            "",
            "## 2. Vendor Coverage Status & Latest Deltas",
            "",
            "| Vendor ID | Cycle | Total URLs Covered | Total Models Covered | Total Records | EOL Records | Active Records | Data Status | Latest Run Delta | Last Run UTC |",
            "|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|",
        ])

        empty_vendors = []
        for vid, vdata in sorted(self.state.get("vendors", {}).items()):
            delta = vdata.get("latest_delta", {})
            delta_str = (
                f"+{delta.get('new_urls_count', 0)} URLs / +{delta.get('new_models_count', 0)} models"
                if delta else "Baseline"
            )
            run_utc = delta.get("run_timestamp_utc", "N/A")[:19]
            eol_c = vdata.get("eol_records_count", 0)
            act_c = vdata.get("active_records_count", 0)
            d_status = vdata.get("data_status", "ACTIVE_DATA" if vdata.get("total_records", 0) > 0 else "NO_DATA")
            if d_status == "NO_DATA" or vdata.get("total_records", 0) == 0:
                empty_vendors.append(vid)

            lines.append(
                f"| `{vid}` | {vdata.get('cycle', 1)} | {vdata.get('total_covered_urls', 0):,} | "
                f"**{vdata.get('total_covered_models', 0):,}** | {vdata.get('total_records', 0):,} | "
                f"{eol_c:,} | {act_c:,} | `{d_status}` | "
                f"`{delta_str}` | `{run_utc}` |"
            )

        if empty_vendors:
            lines.extend([
                "",
                "### ⚠️ Flagged Vendors with Zero Data (NO_DATA)",
                "> The following vendors currently have 0 records. Run `python scripts/audit_and_enrich_endpoints.py --vendor <id> --auto-fix` to diagnose and enrich their endpoints.",
                "",
            ])
            for ev in empty_vendors:
                lines.append(f"- ⚠️ `{ev}`: 0 records generated")

        lines.extend([
            "",
            "---",
            "",
            "## 3. Latest Discovered Endpoints & Model Samples (Per Vendor)",
            "",
        ])

        for vid, vdata in sorted(self.state.get("vendors", {}).items()):
            delta = vdata.get("latest_delta", {})
            new_urls = delta.get("newly_added_urls", [])
            new_models = delta.get("newly_added_models_sample", [])

            lines.append(f"### Vendor: `{vid}`")
            lines.append(f"- **Total URLs:** {vdata.get('total_covered_urls', 0)} | **Total Models:** {vdata.get('total_covered_models', 0)}")

            if new_urls:
                lines.append(f"- **Newly Discovered URLs in Latest Run ({len(new_urls)}):**")
                for u in new_urls[:5]:
                    lines.append(f"  - `{u}`")
                if len(new_urls) > 5:
                    lines.append(f"  - *...and {len(new_urls) - 5} more URLs*")
            else:
                lines.append("- **Newly Discovered URLs in Latest Run:** None (All endpoints previously known)")

            if new_models:
                lines.append(f"- **Newly Discovered Models Sample ({len(new_models)}):**")
                sample_str = ", ".join(f"`{m}`" for m in new_models[:12])
                lines.append(f"  {sample_str}")
                if len(new_models) > 12:
                    lines.append(f"  *(and {len(new_models) - 12} more models)*")
            else:
                lines.append("- **Newly Discovered Models in Latest Run:** None")
            lines.append("")

        lines.extend([
            "---",
            "",
            "## 4. Run Execution History",
            "",
            "| Timestamp (UTC) | Vendor ID | Cycle | New URLs | New Models | New Records | Cumulative Models | Cumulative Records |",
            "|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|",
        ])

        history_list = self.state.get("history", [])
        if not history_list:
            lines.append("| *No incremental runs recorded yet.* | | | | | | | |")
        else:
            for h in reversed(history_list[-25:]):
                t_str = str(h.get("timestamp_utc", ""))[:19]
                lines.append(
                    f"| `{t_str}` | `{h.get('vendor_id')}` | {h.get('cycle', 1)} | "
                    f"+{h.get('new_urls_count', 0)} | +{h.get('new_models_count', 0)} | "
                    f"+{h.get('new_records_count', 0)} | {h.get('cumulative_vendor_models', 0):,} | "
                    f"{h.get('cumulative_vendor_records', 0):,} |"
                )

        lines.append("")
        return "\n".join(lines)
