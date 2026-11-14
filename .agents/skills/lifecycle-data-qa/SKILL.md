---
name: lifecycle-data-qa
description: >-
  Use this skill when verifying data quality, auditing the master CSV for the mandatory 4-field
  zero-null invariant, checking UTC ISO-8601 timestamps, validating model sanitization, or verifying deduplication.
---

# Lifecycle Data QA & Schema Audit Runbook

This skill outlines data audit procedures for verifying that scraped lifecycle datasets are 100% compliant with relational and time-series database ingestion requirements.

> [!IMPORTANT]
> **Data Quality & Mandatory Field Invariants**:
> In accordance with database schema requirements:
> 1. `vendor_name` is **strictly mandatory** (never null, N/A, or empty).
> 2. `model_name` is **strictly mandatory for hardware** (empty permitted ONLY for standalone OS/software lifecycles where `os` is set).
> 3. `status` is **strictly mandatory** and must conform to one of the 6 Canonical Status ENUMs.
> 4. `aliases` and `replacement` must **never leak calendar dates or narrative boilerplate**.

---

## 🎯 Verification Criteria

### 1. Dual CSV 11-Column Schema Verification
Datasets are strictly partitioned into two production CSVs in Database Snake Case:
- `output/eol_products_lifecycle.csv` (Phase Out, End of Sale, End of Support, Obsolete)
- `output/active_products_lifecycle.csv` (Active, Active Mature)

Both CSVs must strictly contain these 11 columns in exact order:
1. `vendor_name` *(Mandatory)*
2. `model_name` *(Mandatory for hardware)*
3. `aliases` *(Zero date leaks, genuine SKUs only)*
4. `status` *(Mandatory - Canonical Status ENUM)*
5. `stage_date_utc` *(Strict ISO 8601 UTC format or empty)*
6. `source_url` *(SSRF-validated public HTTP/HTTPS URL)*
7. `os` *(Operating system name/version)*
8. `firmware` *(Firmware microcode revision)*
9. `category` *(Mandatory - Product classification)*
10. `replacement` *(Validated successor SKU, zero boilerplate)*
11. `metadata` *(JSON audit trail string)*

### 2. The 6 Canonical Status ENUMs
Every vendor-specific raw status is normalized to:
- `Active` (General commercial availability)
- `Active Mature` (Orderable, but NRND or classic sustaining)
- `Phase Out` (Discontinuation announced, migration advised)
- `End of Sale` (Order stop, Last Time Buy reached)
- `End of Support` (Software updates, vulnerability fixes, and repairs ended)
- `Obsolete` (Complete lifecycle termination)

### 3. Deduplication & Latest Date Retention Rule
- **Strict Invariant**: Exactly **ONE record per `(vendor_name, model_name, canonical_status)` combination**.
- **Latest Date Retention**: When milestone duplicates collide, the record with the newer `stage_date_utc` is preserved, and missing attributes from the loser are merged.
- **Active / EOL Mutual Exclusivity**: When a model enters an EOL milestone, any legacy active placeholder is automatically pruned from `output/active_products_lifecycle.csv`.

### 4. UTC Date Validation
- Must match ISO 8601 UTC format `YYYY-MM-DDTHH:MM:SSZ` (e.g. `2026-09-30T00:00:00Z`).
- Never emit `"N/A"`, `"None"`, or `"TBD"` strings in `stage_date_utc`.
- Quarter and half-year milestones clamped to valid month-ends (Q1 -> March 31, Q2 -> June 30, Q3 -> September 30, Q4 -> December 31).

### 5. Fingerprint Column Omission
- Ensure the internal `Fingerprint` column is completely absent from exported master CSVs. Fingerprints are restricted to SQLite buffer tables (`staging_records`) and memory mappings.

---

## 🔍 Audit Command
To audit the master CSV dataset against all QA invariants:
```bash
python scripts/pre_commit_check.py
```
Check 6 executes the full SQL compliance and non-null invariant test.
