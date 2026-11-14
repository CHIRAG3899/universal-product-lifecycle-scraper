# System Constitution & Operating Directives

## 1. The Zero-Inference Doctrine (Non-Negotiable)

Data integrity in enterprise lifecycle intelligence requires absolute authenticity. The scraper operates under a strict **Zero-Inference Doctrine**:

1. **Deterministic Date Precedence**:
   - `stage_date_utc` prioritizes explicit calendar dates stated by the manufacturer for that specific lifecycle milestone.
   - **Fallback Date Rule**: If an authentic lifecycle date exists, it is strictly preserved without modification. If no lifecycle date exists, the framework falls back to article, page creation, or release date (provided it is >= 30 days old). If that candidate date is younger than 30 days, future, or missing, a deterministic date exactly 30 days old from the current date is assigned.
   - **Zero Date Leaks**: Calendar dates belong exclusively in `stage_date_utc`. Under no circumstances may dates leak into `model_name`, `aliases`, or `replacement`.

2. **Canonical Status Normalization**:
   - The `status` column strictly contains one of the 6 Canonical Status ENUMs: `Active`, `Active Mature`, `Phase Out`, `End of Sale`, `End of Support`, or `Obsolete`.
   - The manufacturer's authentic raw status is preserved losslessly inside `metadata["raw_vendor_status"]`.

3. **Single Record Invariant per Canonical Status**:
   - For each canonical status, there must be **strictly ONE record per `(vendor_name, model_name, canonical_status)` combination**.
   - When duplicate records collide on `(vendor, model, canonical_status)`, the record with the latest date is preserved and secondary attributes are merged.

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
   - Contains all records where the product has entered or announced an End-of-Lifecycle milestone:
     - `Phase Out`, `End of Sale`, `End of Support`, `Obsolete`.
2. **`output/active_products_lifecycle.csv`**:
   - Contains all records where the product is in standard active production or commercial delivery:
     - `Active`, `Active Mature`.
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

