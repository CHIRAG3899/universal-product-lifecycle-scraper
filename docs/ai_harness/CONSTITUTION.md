# System Constitution & Operating Directives

## 1. The Zero-Inference Doctrine (Non-Negotiable)

Data integrity in enterprise lifecycle intelligence requires absolute authenticity. The scraper operates under a strict **Zero-Inference Doctrine**:

1. **Zero Date Inference**:
   - `stage_date_utc` must ONLY be populated when an explicit calendar date is stated by the manufacturer for that specific lifecycle milestone.
   - **Forbidden Practices**:
     - Never use XML sitemap `<lastmod>` timestamps as product milestone dates. (Sitemap `<lastmod>` reflects web server HTML update time, not product phase transitions).
     - Never use HTTP `Last-Modified` headers, crawl execution timestamps, or page publication dates.
     - Never guess year-ends, quarter-ends, or fiscal boundaries unless explicitly noted.
   - **Missing Date Rule**: If a product is stated as Discontinued / EOL without an explicit milestone date, set `stage_date_utc` to an empty string (`""`) and record `{"missing_date": true}` in `metadata`. Never drop or discard a legitimate product record because its date is missing!

2. **Zero Status Inference**:
   - The `status` field must reflect the authentic lifecycle milestone designated by the vendor.
   - Never assume or infer "Active" status simply because an HTML page or URL exists on a website.
   - Never assign default active statuses from config unless the source document or catalog is explicitly titled and structured as an active product portfolio.

3. **Zero Model Inference from URL Slugs**:
   - Never convert URL path segments (e.g., `/products/ruggedcom/terms/`, `/tools/`, `/timing-relays/`, `/top-connect/`, `/overview/`) into model numbers.
   - Extracted `model_name` strings must pass rigorous validation (`is_valid_product_model`):
     - Must be genuine hardware/software model numbers or recognized operating system names.
     - Reject website chrome, navigation links, legal headings, cookie policies, and generic category groupings.
     - Reject electrical specifications (e.g. `3-phase`, `1-phase`, `24VDC`, `10A`).

4. **Zero Date and Boilerplate Leakage**:
   - Calendar dates (e.g. `April 30 - 2026`, `2026-09-30`) belong exclusively in `stage_date_utc`. Under no circumstances may calendar dates leak into `model_name`, `aliases`, or `replacement`.
   - Instructional phrases and table headers (e.g. `Includes the following models:`, `Replacement manual`, `QAnS - Main series`, `Contact Repair & Replacement`, `Not Applicable`) must be aggressively stripped and rejected from all data fields.

---

## 2. Output Schema & Dual-CSV Contract

The scraper enforces a strict **Dual-CSV Output Contract**:

1. **`output/eol_products_lifecycle.csv`**:
   - Contains all records where the product has entered or announced an End-of-Lifecycle stage based on manufacturer terminology:
     - `Discontinued`, `End of Life (EOL)`, `End of Sale (EOS)`, `End of Support (EOSL)`, `Last Time Buy (LTB)`, `Phase-Out Announced`, `Obsolete`, `Classic`, `Limited`, `Stop Shipment`, `Withdrawal`, `Auslauftyp`, `Produktabkündigung`, `PM400`, `PM410`, `PM490`.
2. **`output/active_products_lifecycle.csv`**:
   - Contains all records where the product is verified to be in standard active production or commercial delivery:
     - `Active`, `Active Mature`, `Current`, `Supported`, `Available`, `Delivery Release`.
3. **Decommissioned Files**:
   - `output/all_vendors_lifecycle.csv` is permanently removed to prevent accidental consumption of unsegmented data.

### The 11 Database Columns (Exact Schema)
Both CSV outputs strictly maintain the following 11 database snake_case columns:
```
vendor_name,model_name,aliases,status,stage_date_utc,source_url,os,firmware,category,replacement,metadata
```
- **`vendor_name`**: Mandatory. Non-null, non-empty manufacturer name (e.g., `Mitsubishi Electric`, `Siemens`).
- **`model_name`**: Mandatory for hardware. Discrete single product model/part number (e.g., `MI3321G-W`, `A1CPU`). Empty permitted only for OS/software rows.
- **`aliases`**: Clean comma-separated string of genuine family names, series names, or alternative part numbers (e.g., `MELIPC series`, `An Series`). Zero dates, zero boilerplate.
- **`status`**: Mandatory. Exact lifecycle stage name according to vendor terminology.
- **`stage_date_utc`**: UTC ISO 8601 string (`YYYY-MM-DDTHH:MM:SSZ`) or empty string if date is not stated.
- **`source_url`**: Canonical source URL or PDF bulletin link where the evidence was discovered.
- **`os`**: Operating system name where applicable, or empty string.
- **`firmware`**: Specific firmware release where applicable, or empty string.
- **`category`**: Industrial category or technology classification.
- **`replacement`**: Genuine successor hardware/software SKU (e.g., `NZ2GN2B-60AD4`), or empty string. Zero placeholder boilerplate.
- **`metadata`**: Structured JSON string containing lineage attributes (`first_discovered_utc`, `last_updated_utc`, `region`, `bulletin_id`, etc.).

---

## 3. Coverage & Discrete Entity Invariant

1. **No Bundling of Models**:
   - When a table row or announcement lists multiple models (e.g., `MI3321G-W and MI3315G-W` or `A1NCPU, A2NCPU, A3NCPU`), the parser must unpack every single model into its own distinct, standalone `ProductRecord`.
   - Never combine or leave comma-separated models in `model_name`.
2. **Multi-Milestone Progression**:
   - If an announcement provides separate milestone dates for a model (e.g., End of Sale on 2024-09-30, Last Time Buy on 2025-03-31, End of Support on 2029-09-30), the scraper emits an independent record for EACH milestone.

---

## 4. LLM Role: Verification & Parsing Only (Zero-Inference AI Integration)

1. **Analytical Validator, Not Hallucination Engine**:
   - The LLM serves strictly as an analytical verification gate and structured parser. Its role is to confirm that extracted data faithfully mirrors authentic manufacturer disclosures.
   - The LLM is **STRICTLY PROHIBITED** from:
     - Inventing or guessing lifecycle statuses (e.g. assuming a product is active because a URL was found).
     - Guessing or synthesizing milestone dates.
     - Converting website URL slugs into fictitious model numbers (e.g. `terms`, `text-display`, `timing-relays`, `tools`, `top-connect`).
2. **Pre-Persistence Verification Gate**:
   - Before candidate records are committed to dual-CSV storage, they pass through the LLM verification gate (`verify_and_filter_records_with_llm`):
     - Validates that `model_name` is an authentic physical or software industrial product.
     - Validates that `status` is explicitly grounded in source evidence.
     - Enforces zero date leakage into `aliases`, `model_name`, or `replacement`.
     - Purges boilerplate phrases (`Includes the following models:`, `Replacement manual`, `QAnS - Main series`).

---

## 5. Engineering & Execution Discipline

1. **Zero Throwaway Scripts**:
   - All logic, audit routines, and test tooling must reside in version-controlled modules in `scraper/`, `scripts/`, or `configs/`. No ad-hoc, untracked scripts.
2. **Sequential Multi-Vendor Verification**:
   - Vendors must be audited, executed, and verified sequentially from a clean board without stopping in between.
   - Output data in `eol_products_lifecycle.csv` and `active_products_lifecycle.csv` must be inspected and validated after each vendor run.
3. **Pre-Commit Enforcement**:
   - No code or configuration changes may be merged without achieving 100% GREEN status across all 8 steps of `python scripts/pre_commit_check.py`.

