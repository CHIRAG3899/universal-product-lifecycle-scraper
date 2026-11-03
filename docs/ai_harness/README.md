# Universal Lifecycle Scraper - AI Harness

## Master Overview & Documentation Index

The AI Harness serves as the authoritative architectural foundation, operating constitution, and execution governance framework for the Universal Multi-Vendor Product Lifecycle Intelligence Scraper.

This harness guarantees absolute data fidelity, eliminates heuristic halluncination, standardizes multi-vendor hardware/software milestone extraction, and enforces a strict dual-dataset output standard across industrial automation (OT), Internet of Things (IoT), and Information Technology (IT) domains.

---

## Document Index & Hierarchy

| Document | Primary Focus | Key Responsibilities |
| :--- | :--- | :--- |
| [**CONSTITUTION.md**](CONSTITUTION.md) | Immutable Operating Principles | Zero-inference doctrine, true lifecycle milestones only, dual-CSV contract, anti-leakage invariants. |
| [**TECH_DESIGN.md**](TECH_DESIGN.md) | Technical Architecture & Modules | Crawl engine, strategy layer, LLM integration, models, validation, storage. |
| [**DECISIONS.md**](DECISIONS.md) | Architecture Decision Records (ADRs) | ADR-001 through ADR-006 documenting design decisions, rationale, and tradeoffs. |
| [**FLOWS.md**](FLOWS.md) | Visual & Operational Workflows | Mermaid sequence and state flows for crawling, LLM extraction, sanitization, and routing. |
| [**PLAN.md**](PLAN.md) | Vendor Roadmap & Execution Plan | Sequential vendor-by-vendor execution protocol, clean-board audit criteria, milestones. |
| [**SECURITY.md**](SECURITY.md) | Enterprise Threat Defense | SSRF defense, CSV formula injection neutralization, WAF stealth, credential security. |
| [**GAPS_AND_IMPROVEMENTS.md**](GAPS_AND_IMPROVEMENTS.md) | Residual Challenges & Future Vision | Single-page dynamic applications, Akamai mitigation, self-healing runtime audits. |

---

## Core System Directives at a Glance

1. **Zero Inference Doctrine**: Never infer, guess, or extrapolate dates, statuses, categories, or models. If a fact is not explicitly stated by the manufacturer, it remains null/empty.
2. **Dual-CSV Output Standard**: The scraper generates strictly two partitioned lifecycle datasets:
   - `output/eol_products_lifecycle.csv`: All products that have reached or announced End of Life, Discontinuation, Phase-Out, Obsoletion, or Last Time Buy.
   - `output/active_products_lifecycle.csv`: All products currently in Active, Supported, or Standard Availability stages.
   - The consolidated `all_vendors_lifecycle.csv` has been permanently decommissioned.
3. **LLM-First Extraction Everywhere**: Leverages Gemini 3.5 (and pluggable LLMs) across unstructured bulletins, HTML tables, and complex multi-card layouts, replacing fragile regex-only assumptions.
4. **Clean Board Vendor Audit**: Each vendor in `configs/vendors.yaml` is tested and verified sequentially with zero cross-vendor divergence and zero throwaway scripts.

