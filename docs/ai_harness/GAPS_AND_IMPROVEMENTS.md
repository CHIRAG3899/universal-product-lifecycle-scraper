# Strategic Improvements, Gaps & Future Vision

## 1. Identified Architecture Gaps

1. **Complex Single-Page Applications (SPAs)**:
   - Several major vendors (e.g. Rockwell Automation Product Lifecycle Portal, Siemens SiePortal) deliver lifecycle queries via Angular/React client-side single-page applications protected by Akamai bot management.
   - *Current State*: Standard HTTP requests receive 403 Forbidden. Crawl4AI browser mode successfully loads initial state, but dynamic search input fields and AJAX pagination require automated interaction handlers.
   - *Improvement*: Expand `SearchPortalStrategy` with declarative action sequences (`click_selector`, `fill_input`, `wait_for_network_idle`).

2. **Multilingual Lifecycle Terminology Ingestion**:
   - Japanese (`生産終了`, `最終受注`, `修理対応終了`), German (`Auslauftyp`, `Produktabkündigung`, `Lieferstopp`), and French (`Fin de commercialisation`) terminology requires continuous vocabulary synchronization to prevent unmapped stages.
   - *Improvement*: Dynamic ingestion of multilingual lifecycle dictionaries via the AI extractor's multi-lingual prompt normalization layer.

3. **Vendor Sitemap Over-Reliance**:
   - Vendor sitemaps frequently bundle marketing landing pages and legal notices alongside technical products.
   - *Resolution Applied*: Implemented zero-inference rules rejecting non-alphanumeric slugs (`terms`, `tools`, `privacy`) and sitemap `<lastmod>` dates. Long term, sitemaps should be used strictly for initial URL discovery, followed by LLM-driven verification of each page.

---

## 2. Roadmap & Strategic Enhancements

1. **Continuous Automated Endpoint Auditing**:
   - Integrate `scripts/audit_and_enrich_endpoints.py` into a weekly scheduled GitHub Actions workflow to detect upstream vendor URL migrations, 404 dead links, and newly introduced WAF restrictions.
2. **Dynamic Replacement Graph Generation**:
   - Construct a directed replacement graph ($A \to B \to C$) across historical discontinuation bulletins, enabling enterprise users to trace legacy obsolete hardware through multiple successor generations to currently available active units.
3. **Automated Delta Intelligence Delivery**:
   - Deliver weekly change alerts notifying asset managers whenever an active product enters "Phase-Out Announced" or reaches its "Last Time Buy" milestone.

