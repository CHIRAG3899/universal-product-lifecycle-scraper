---
name: lifecycle-data-qa
description: >-
  Use this skill when verifying data quality, auditing the master CSV for the mandatory 4-field
  zero-null invariant, checking UTC ISO-8601 timestamps, validating model sanitization, or verifying deduplication.
---

# Lifecycle Data QA & Schema Audit Runbook

This skill outlines data audit procedures for verifying that scraped lifecycle datasets are 100% compliant with relational and time-series database ingestion requirements.

> [!IMPORTANT]
> **Strict Zero-Null Invariant (Mandatory 4 Fields)**:
> In accordance with database schema requirements, four fields can **NEVER be NULL or empty string**:
> 1. `vendor_name`
> 2. `model_name`
> 3. `status`
> 4. `stage_date_utc`
> 
> Any record lacking any of these 4 fields is rejected during sanitisation. If a published lifecycle notice or table specifies a discontinuation status without an explicit per-row date, the date is hydrated from the bulletin publication date or crawl snapshot date.

---

## 🎯 Verification Criteria

### 1. Column Schema Verification
The master CSV ([`output/all_vendors_lifecycle.csv`](output/all_vendors_lifecycle.csv)) must contain exactly these 10 snake_case columns in this specific order:
1. `vendor_name` *(Mandatory - No nulls allowed)*
2. `model_name` *(Mandatory - No nulls allowed)*
3. `status` *(Mandatory - No nulls allowed)*
4. `stage_date_utc` *(Mandatory - No nulls allowed)*
5. `source_url`
6. `os` *(Optional - empty string if unknown)*
7. `firmware` *(Optional - empty string if unknown)*
8. `category` *(Optional - empty string if unknown)*
9. `replacement` *(Optional - empty string if unknown)*
10. `metadata` *(Optional - JSON string)*

### 2. Status & Lifecycle Phase Integrity (Zero Status Limitations)
- **Zero Whitelist Restrictions**: Never restrict statuses to an artificial enum or 3-stage whitelist. Scraped values must preserve the manufacturer's exact official milestone (*Phase-Out Product, Delivery Release, Announced Discontinuation, Product Cancellation, End of Sale, Last Date of Support, Classic, Limited, Obsolete, Active Mature, Stop Shipment, Repair Termination, Maintenance Only*).
- Both `status` and `vendor_status` must match and retain the vendor's genuine nomenclature.
- Raw noise text or multi-sentence paragraphs exceeding 40 characters are purged during sanitisation.

### 3. UTC Date Validation
- **Valid dates**: Must match ISO 8601 UTC format `YYYY-MM-DDTHH:MM:SSZ` (e.g. `2026-09-30T00:00:00Z`).
- Never emit `"N/A"`, `"None"`, or `"TBD"` strings in `stage_date_utc`.
- **Quarters & Half-Years**: Must be normalized to month-end dates:
  - `Q1` -> `03-31T00:00:00Z`, `Q2` -> `06-30T00:00:00Z`, `Q3` -> `09-30T00:00:00Z`, `Q4` -> `12-31T00:00:00Z`
  - `H1` -> `06-30T00:00:00Z`, `H2` -> `12-31T00:00:00Z`

### 4. Model Name Sanity & Expansion
- Must NOT contain cookie banners (e.g. `Performance Cookies`, `Cookie Notice`).
- Must NOT contain web navigation text (e.g. `Global`, `Follow Us`, `Privacy Policy`).
- Must NOT be markdown links (e.g. `[Model](http://...)`).
- Verify model suffixes (`-16MT/ES` -> `FX2N-16MT/ES`) and integer ranges (`1756-L61 to 1756-L63`) are properly unbundled into discrete product rows.

### 5. Fingerprint Omission
- Ensure the internal `Fingerprint` column is completely absent from the exported master CSV.
- The fingerprint hash should only be retained inside `output/*_lifecycle.json` and memory mappings.

---

## 🔍 Audit Command
To audit the master CSV dataset against all QA invariants:
```bash
python scripts/pre_commit_check.py
```
Check 6 executes the full SQL compliance and non-null invariant test.
