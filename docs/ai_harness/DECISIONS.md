# Architecture Decision Records (ADRs)

## ADR-001: Zero-Inference Operating Doctrine
* **Status**: ACCEPTED (Immutable)
* **Date**: 2026-11-02
* **Context**: Earlier crawling strategies occasionally inferred "Active" statuses for products simply because a web page existed, or mapped XML sitemap `<lastmod>` timestamps into `stage_date_utc`. This produced corrupt records (e.g. Siemens legal URLs like `/terms/` extracted as active models with `<lastmod>` dates).
* **Decision**: Adopt an uncompromising Zero-Inference Doctrine:
  1. No date is recorded unless explicitly stated in the vendor notice for that milestone.
  2. No status is assumed unless explicitly designated by the manufacturer.
  3. No URL slugs are converted to models without passing strict alphanumeric SKU validation.
* **Consequences**: Zero false-positive active products; missing dates are marked with `{"missing_date": true}` rather than synthetic placeholders.

---

## ADR-002: Dual-CSV Output Standard & Deprecation of `all_vendors_lifecycle.csv`
* **Status**: ACCEPTED
* **Date**: 2026-11-03
* **Context**: Downstream consumption systems require clear distinction between end-of-lifecycle inventory (requiring mitigation/replacement) and active portfolio items. A monolithic CSV caused confusion and risked blending retired hardware with active catalog ranges.
* **Decision**:
  1. Maintain strictly two CSV outputs:
     - `output/eol_products_lifecycle.csv` (EOL, Discontinued, Obsolete, LTB, EOSL)
     - `output/active_products_lifecycle.csv` (Active, Supported, Available)
  2. Permanently delete and prevent the generation of `output/all_vendors_lifecycle.csv`.
* **Consequences**: Immediate, clear segmentation for risk analysts; clean separate datasets with identical 11-column schemas.

---

## ADR-003: LLM-First Parsing Over Heuristic-Only Extraction
* **Status**: ACCEPTED
* **Date**: 2026-11-03
* **Context**: Heuristic regexes frequently failed to unpack multi-card tables, multilingual notices (Japanese, German), and complex replacement matrices, or mistakenly captured dates into alias columns.
* **Decision**: When an AI client is configured (`self.extractor.is_configured()`), prioritize LLM extraction (`gemini-3.5-flash-lite`) over zero-token heuristic fallbacks. Heuristic extraction is retained strictly as an offline/unconfigured fallback.
* **Consequences**: High contextual comprehension of vendor announcements; automatic translation of Japanese/German lifecycle stages; elimination of regex fragility.

---

## ADR-004: Anti-WAF Stealth Browser Integration for Enterprise Catalogs
* **Status**: ACCEPTED
* **Date**: 2026-11-01
* **Context**: Key industrial vendors (Schneider Electric, Cisco, Rockwell Automation) utilize Akamai Ghost / Cloudflare bot management, returning HTTP 403 Forbidden to standard Python HTTP requests.
* **Decision**: Implement dual-mode crawling (`crawler_mode: browser` vs `crawler_mode: http`) using Crawl4AI with Playwright Chromium, stealth navigator shims, and automatic detection of Akamai/Cloudflare challenge headers.
* **Consequences**: Reliable ingestion of 1,000+ protected product ranges without human intervention or proxy bypass hacks.

---

## ADR-005: Deterministic Canonical SHA-256 Fingerprinting
* **Status**: ACCEPTED
* **Date**: 2026-10-30
* **Context**: Repeated crawl cycles and multiple entry points for the same vendor risked duplicate rows and non-deterministic sorting in CSV exports.
* **Decision**: Compute a 16-character SHA-256 fingerprint from the tuple `(VENDOR | MODEL | STATUS | DATE)` in normalized uppercase format. All upserts, merges, and dedup passes use this deterministic key.
* **Consequences**: Idempotent pipeline runs; identical results across repeat invocations; zero row duplication.

---

## ADR-006: Pre-Commit Verification Gate as Hard Enforcement Mechanism
* **Status**: ACCEPTED
* **Date**: 2026-10-31
* **Context**: Divergent configuration syntax, unformatted imports, or broken unit tests could silently degrade data quality.
* **Decision**: Enforce an 8-step pre-commit verification gate (`scripts/pre_commit_check.py`):
  1. Ruff Linter & Formatter
  2. Mypy Static Type Checking
  3. Security & Threat Scanning (Bandit, Formula Injection, SSRF)
  4. Vendor Config Syntax & Schema Integrity
  5. Unique Vendor Name & Key Invariance
  6. Dataset Schema & DB Readiness (Dual-CSV 11-column check)
  7. Full Test Suite (250+ automated unit and integration tests)
  8. Code Coverage & Branch Verification
* **Consequences**: Zero regressions can reach production; every pull request and milestone build is provably clean.

---

## ADR-007: Mandatory Pre-Persistence LLM Verification Gate
* **Status**: ACCEPTED
* **Date**: 2026-11-03
* **Context**: Crawlers harvesting DOM tables, sitemaps, or text may capture navigation tokens (`terms`, `text-display`, `timing-relays`, `tools`), document titles (`replacement manual`), or dates in aliases (`April 30 - 2026`). The pipeline required a unified gate to verify all records before storage.
* **Decision**: Wire the LLM into a dedicated pre-persistence verification gate (`verify_and_filter_records_with_llm`). The LLM's mandate is strictly verification and correct parsing—never inference. It confirms that the product model is genuine, status is authentic, milestone date is exact, and alias contains zero date or boilerplate leaks.
* **Consequences**: Provable zero-leakage guarantee across all 11 columns in dual CSV outputs.

