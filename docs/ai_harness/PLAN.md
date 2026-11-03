# Vendor Onboarding & Execution Plan

## 1. Sequential Vendor Execution Protocol

Vendors are onboarded and executed sequentially down `configs/vendors.yaml`. Under no circumstances should parallel bulk execution be attempted before an individual vendor is fully audited, verified, and clean-board checked.

### Standard Operating Protocol for Each Vendor:
1. **Endpoint Audit**: Run `python scripts/audit_and_enrich_endpoints.py --vendor <vendor_id>` to assess endpoint health, WAF status, and crawler mode.
2. **Configuration Alignment**: Verify that `configs/vendors.yaml` contains authentic entry points with zero inferred defaults.
3. **Clean-Board Execution**: Run `python cli.py --vendor <vendor_id> --reset-state` to extract data from a clean board.
4. **Data Quality Audit**:
   - Verify non-empty `vendor_name`, `model_name`, `status`.
   - Verify `stage_date_utc` has zero inferred sitemap dates and is valid UTC ISO 8601 or empty string.
   - Verify `aliases` has zero date leakage (e.g., no `April 30 - 2026`) and zero boilerplate phrases.
   - Verify `replacement` contains authentic successor SKUs or is empty string.
   - Check partitioning: EOL records routed to `eol_products_lifecycle.csv`, Active records routed to `active_products_lifecycle.csv`.
5. **Pre-Commit Verification**: Run `python scripts/pre_commit_check.py` to ensure 8/8 gates pass before proceeding to the next vendor.

---

## 2. Vendor Execution Tracker

| # | Vendor ID | Vendor Name | Sector | Entry Points Status | EOL Records | Active Records | Verification Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | `mitsubishi` | Mitsubishi Electric | OT | EOL Discontinuation Tables & Linked PDFs | **1,472** | **0** | **VERIFIED GREEN** |
| **2** | `siemens` | Siemens | OT/IT | SiePortal Product Cancellation & Phase-Out | *In Progress* | *In Progress* | *Purged Sitemap Slugs; Re-aligning SiePortal* |
| **3** | `schneider_electric` | Schneider Electric | OT | US Product Range A-Z (Browser Mode) | *Pending* | *Pending* | Ready for Execution |
| **4** | `rockwell_automation` | Rockwell Automation | OT | Product Lifecycle Status Portal | *Pending* | *Pending* | Ready for Execution |
| **5** | `omron` | Omron Industrial | OT | Discontinued Products & Substitutes | *Pending* | *Pending* | Queued |
| **6** | `abb` | ABB | OT | Electrification & Automation Lifecycles | *Pending* | *Pending* | Queued |
| **7** | `yokogawa` | Yokogawa | OT | CENTUM & Field Instruments EOL Notices | *Pending* | *Pending* | Queued |
| **8** | `emerson` | Emerson DeltaV | OT | DeltaV & Ovation Lifecycle Bulletins | *Pending* | *Pending* | Queued |
| **9** | `beckhoff` | Beckhoff Automation | OT | IPC & EtherCAT Discontinuation Stages | *Pending* | *Pending* | Queued |
| **10** | `phoenix_contact` | Phoenix Contact | OT | Discontinued Products & Replacements | *Pending* | *Pending* | Queued |
| **11** | `cisco` | Cisco Systems | IT | Catalyst, Nexus, UCS EOL Bulletins | *Pending* | *Pending* | Queued |
| **12** | `cisco_meraki` | Cisco Meraki | IT | Meraki EOL Products & Dates Table | *Pending* | *Pending* | Queued (Date leak regex fixed) |
| **13** | `honeywell` | Honeywell | OT | Process Solutions & Scanner Lifecycles | *Pending* | *Pending* | Queued |

---

## 3. Clean-Board Criteria

A vendor run is deemed clean and complete when:
- Zero invalid model names (no `3-phase`, no `terms`, no URL slugs).
- Zero date leakage in `aliases` or `replacement` (no month names or years in non-date columns).
- Zero boilerplate phrases in `aliases` (no `Includes following models:`, `Replacement manual`, `Main series`).
- All models are unpacked into discrete records (no grouped models).
- Exact parity between state trackers and dual-CSV outputs.

