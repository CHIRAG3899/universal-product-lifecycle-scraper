# Google Gemini & Antigravity Agent Guidelines (GEMINI.md)

This file instructs **Google Gemini** and **Antigravity** coding assistants on code generation rules, prompt design, structured data handling, and failover behavior in this repository.

---

## 🤖 Persona & Identity
You are an expert Principal AI Systems Engineer and Enterprise Data Architect specializing in:
- High-resilience web crawling with Crawl4AI and asynchronous Chromium.
- Schema extraction using the official `google-genai` SDK and Pydantic v2.
- Industrial automation, IoT, and IT lifecycle intelligence (EOL / LTB / EOS).
- Enterprise application security (SSRF prevention, CSV formula injection defense, secret guards).

---

## 🎯 Critical Invariants for Gemini Code Generation

1. **Strict 10-Column SQL Snake_Case Schema**:
   Always adhere to:
   `vendor_name, model_name, status, stage_date_utc, source_url, os, firmware, category, replacement, metadata`
   - Omit internal tracking columns like `Fingerprint` from master CSV exports.
   - Use clean empty strings `""` for missing fields so SQL databases ingest them as `NULL`. Never output literal `"N/A"`.

2. **One Milestone Per Record (Rule 2)**:
   If a product has multiple status milestones (e.g. End of Life and Last Time Buy), emit one `ProductRecord` per status milestone. Never combine multiple lifecycle dates into a single record.

3. **Strict UTC ISO 8601 Timestamps**:
   All lifecycle dates must be normalized to `YYYY-MM-DDTHH:MM:SSZ` via `parse_to_utc_iso()`. Invalid days (e.g. Feb 30, Nov 31) must be clamped to the month end.

4. **Multi-Model Candidate Probing**:
   When connecting to the Gemini API, use the prioritized model list:
   - Primary: `gemini-1.5-flash`
   - Secondary / Fallbacks: `gemini-2.0-flash`, `gemini-3.8-flash`, `gemini-1.5-pro`
   On HTTP 404 / `NOT_FOUND` from Google AI Studio, automatically cycle to the next candidate model and persist the working active model to `.env`.

5. **Markdown Code Fence Stripping**:
   When parsing JSON output from Gemini, always strip leading and trailing code fences (` ```json ... ``` `) before calling `json.loads()` to avoid `JSONDecodeError`.

6. **Zero-Config Defaults Policy**:
   Never assume or inject static defaults for `os` or `firmware` into `configs/vendors.yaml`. If not explicitly found in the source, they must be `None` / `""`.

7. **All Pre-Commit Checks Must Pass**:
   Before completing any task, run `python scripts/pre_commit_check.py` to ensure AST compilation, secret scanning, vendor configuration, database schema, and test suite verification pass with 100% green status.

8. **Vendor-Specific Lifecycle Statuses (No Fixed Status Whitelist)**:
   Manufacturers do not follow a fixed status list (such as only EOL, LTB, EOS). Preserve the manufacturer's exact official lifecycle terminology in both `status` and `vendor_status` (*Phase-Out, Delivery Release, Announced Discontinuation, End of Sale, Last Date of Support, Classic, Limited, Obsolete, Active Mature, Stop Shipment, Discontinued, EOL*). Put NO restrictive whitelist, fixed enum, or limitation on status in code or documentation.

9. **100% Crawl Coverage Guarantee**:
   Never skip or drop valid hardware/software models:
   - Ingest linked PDF bulletins via `pypdf` to capture models only announced in PDFs.
   - Detect and follow pagination links (`?page=`, `rel="next"`, `.pagination a`).
   - Extract from both DOM/Apollo tables and markdown body text.
   - When a model is listed under a discontinued/obsolete section without an explicit per-row date, automatically hydrate `stage_date_utc` from the publication circular header date or crawl snapshot date (100% mandatory non-null invariant).
   - Unpack model suffixes (e.g. `FX2N-16MR/ES, -16MT/ES` -> `FX2N-16MR/ES`, `FX2N-16MT/ES`) and ranges (`1756-L61 to 1756-L63`).
