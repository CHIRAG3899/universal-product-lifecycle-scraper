# Capability-Based Batching & Dynamic Knowledge Base Synchronization

## 1. Overview
The **Universal Lifecycle Scraper** implements an autonomous, capability-based batching and multi-cycle knowledge base architecture. Instead of hardcoding static product keywords (which artificially constrain discovery) or performing unbounded site-wide runaway crawls, the system dynamically discovers **all URLs** (sitemaps, notice hubs, document indexes, product tables) across each vendor.

On every run, discovered URLs are synchronized with a persistent **Knowledge Base** (`artifacts/run_state/{vendor_id}_state.json`). Work is broken down into discrete capability-governed batches. One batch runs in the current invocation; subsequent batches process sequentially on subsequent runs. When all batches in a cycle complete, the cycle automatically refreshes, re-checks all URLs against the knowledge base for newly announced entries, and restarts the continuous ingestion lifecycle.

---

## 2. Core Architectural Principles

### A. Full URL Discovery Without Artificial Limits
- **Zero Keyword Restrictions**: All hardcoded seed keywords (e.g., `1756`, `1769`, `5069`, `2711P`) are purged. The crawler discovers genuine, unconstrained product models and SKUs directly from authoritative vendor feeds.
- **Uncapped Sitemaps**: No artificial caps (`max_sitemaps: 15` purged). Root sitemap indexes (e.g. Rockwell Automation's 182 PDP child sitemaps) are traversed completely and cataloged into the vendor Knowledge Base.

### B. Knowledge Base Synchronization
- **On Every Run**: The crawler fetches root sitemaps or hub indexes and extracts all URLs.
- **Comparison & Delta Detection**: New URLs not currently in the knowledge base are appended with `"status": "pending"`.
- **Cycle Reset**: If all units in the pending queue have completed, the system increments the `cycle` counter, preserves seen models to eliminate duplicates, and repopulates the pending queue for a fresh verification pass.

### C. Capability-Based Batching
Batch size is determined by ingestion capability and rate limits:
- **XML Sitemaps**: 1 to 5 child sitemaps per run (each child sitemap typically yields 1,000–2,000 discrete product models).
- **DOM Tables & Milestone Lists**: Processed in a single fast, deterministic pass.
- **Search Portals & Notice Hubs**: 10 to 20 notice URLs per run.
- **CLI Control**: Overridable via `--batch-size <N>` and `--all-batches` flags.

---

## 3. Progress Tracking & Metrics Dashboard

Progress is persisted on every batch execution across two synchronized formats:
1. **Machine-Readable JSON**: `artifacts/batch_progress.json` and `output/batch_progress.json`
2. **Human-Readable Dashboard**: `artifacts/batch_progress.md`

### Tracked Metrics per Vendor:
| Field | Description |
|:---|:---|
| `cycle` | Current ingestion cycle (increments upon 100% completion) |
| `total_discovered_units` | Total cataloged URLs / child sitemaps / notice documents in Knowledge Base |
| `completed_units` | Units successfully processed in current cycle |
| `pending_units` | Units remaining in pending queue for current cycle |
| `batch_size` | Number of units processed per run |
| `batches_completed` | Batches executed in current cycle ($\lceil \text{completed} / \text{batch\_size} \rceil$) |
| `batches_remaining` | Batches left to process ($\lceil \text{pending} / \text{batch\_size} \rceil$) |
| `total_records_harvested` | Total unique product records extracted |
| `progress_percent` | Percentage of units processed ($\text{completed} / \text{total} \times 100$) |
| `status` | Execution status (`IN_PROGRESS`, `CYCLE_COMPLETE`) |
| `last_run_utc` | ISO 8601 UTC timestamp of the most recent run |

---

## 4. Column Data Quality & Strict Schema Enforcement

All records exported to `output/all_vendors_lifecycle.csv` strictly adhere to the 11-column standard:
```csv
vendor_name,model_name,aliases,status,stage_date_utc,source_url,os,firmware,category,replacement,metadata
```

### Strict Column Guards:
- **`vendor_name`**: Standardized canonical vendor name.
- **`model_name`**: Authentic SKU / part identifier. No quotes, no CSV formula triggers, no noise categories.
- **`aliases`**: Alternate part names only. **Dates (e.g. `April 30 - 2026`, `2024-01-01`) and boilerplate (`n/a`, `-`) are strictly rejected**. When an announcement date is discovered in an alias column, it is automatically routed to `metadata["announcement_date_utc"]`.
- **`status`**: Official normalized lifecycle milestone (`Active`, `End of Sale`, `End of Support`, `Discontinued`).
- **`stage_date_utc`**: Strict ISO 8601 UTC format (`YYYY-MM-DDTHH:MM:SSZ`) or null (never "N/A" or raw strings).
- **`replacement`**: Genuine successor model number only. Sentences, dates, and sales boilerplate ("Contact sales", "Refer to bulletin") are purged.
- **`metadata`**: Structured JSON containing `announcement_date_utc`, `region`, and discovery timestamps.

