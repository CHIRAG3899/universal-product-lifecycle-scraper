# Universal Multi-Vendor EOL & Lifecycle AI Scraper: Agent Instructions (AGENTS.md)

Welcome, AI Agent! This document contains the definitive architecture, design constraints, invariants, tool protocols, and execution workflows for the **Universal Multi-Vendor EOL & Lifecycle AI Scraper** repository.

Any AI agent (Antigravity, Gemini, Copilot, Cursor, Claude, etc.) operating in this workspace MUST strictly adhere to the rules, schemas, and workflows defined here.

---

## 🧭 Repository Mission & Scope

The platform is an enterprise-grade intelligence engine designed to autonomously discover, crawl, normalize, sanitize, deduplicate, and monitor enterprise hardware and software reaching their:
- **Last Time Buy (LTB)**
- **End of Life / End of Sale (EOL)**
- **End of Service / End of Support (EOS)**

It provides native out-of-the-box support for **140 top enterprise vendors** across:
1. **Operational Technology (OT) & Factory Automation**: 54 vendors (JTEKT Toyoda [Toyopuc PLCs], Rockwell Automation / Allen-Bradley, Siemens, Mitsubishi Electric, Schneider Electric, ABB, Omron, Hitachi Industrial Equipment, Shibaura Machine, Dragos, Phoenix Contact, Yokogawa, Fanuc, Lenze, Parker Hannifin, Fuji Electric, IDEC, National Instruments, etc.)
2. **Internet of Things (IoT), Smart Cameras & Edge Vision**: 44 vendors (Cisco Meraki [MV cameras & switches], Nozomi Networks, Axis Communications, Hikvision, Dahua, Hanwha Vision, Teledyne FLIR, Basler, Mobotix, Bosch Security, Avigilon, Uniview, Advantech, Digi International, Intel IoT, etc.)
3. **Enterprise IT, Switches & Networking**: 42 vendors (Barracuda Networks, Fluke Networks, Cisco Systems, HPE / Aruba Networks, Allied Telesis, D-Link Enterprise, NETGEAR Business, TP-Link Enterprise, Zyxel, Westermo, Alcatel-Lucent Enterprise, Juniper, Arista, Fortinet, Dell Technologies, etc.)

---

## 🧱 Technology Stack

| Layer | Technology | Key Components / Responsibilities |
|---|---|---|
| **Language & Runtime** | Python 3.10+ | Asynchronous asyncio runtime, type annotations, strict PEP 8 style |
| **Linting & Code Style** | [Ruff](https://astral.sh/ruff) | Ultra-fast Python linter and code formatter enforced in pre-commit |
| **Static Type Checking** | [Mypy](https://mypy-lang.org/) | Strict static typing and annotation validation across all 33+ modules |
| **Web Crawling** | [Crawl4AI](https://crawl4ai.com) | Asynchronous headless Chromium, DOM rendering, overlay/cookie banner removal |
| **HTTP Fallback** | `urllib` + `BeautifulSoup4` | Resilient fallback crawler with rotating Chrome headers when Chromium is unavailable |
| **AI Extraction Engine** | [Google Gemini](https://ai.google.dev) | Official `google-genai` SDK (`gemini-1.5-flash`, `gemini-2.0-flash`, `gemini-3.8-flash`) |
| **Data Schema & Validation** | [Pydantic v2](https://docs.pydantic.dev) | `ProductRecord`, `GeminiExtractionBatch`, `ScrapedDataset` |
| **Persistence & Merging** | Pandas & Standard Lib | Atomic swapping (`.tmp` + rename), SHA-256 deduplication, non-overwriting incremental append |
| **Web Interface** | Vanilla HTML / CSS / JS | Zero-dependency multi-threaded Python HTTP server (`server.py`), responsive dashboard |
| **Security** | `scraper.security` | SSRF prevention (private IP / CIDR / integer / hex IP blocking), CSV formula sanitization |

---

## ⚠️ Non-Negotiable Core Invariants & Rules

When generating code, modifying schemas, or running pipeline operations, you MUST strictly enforce these 10 core invariants:

<details open>
<summary><b>Invariant 1: Database 10-Column Snake_Case Schema</b> (Click to collapse)</summary>

The exported master dataset (`output/all_vendors_lifecycle.csv`) must match this exact 10-column schema:
```text
vendor_name, model_name, status, stage_date_utc, source_url, os, firmware, category, replacement, metadata
```
- **`vendor_name`**: Clean English manufacturer name (e.g. `Mitsubishi Electric`, `JTEKT Toyoda`) - **MANDATORY, NO NULL ALLOWED**.
- **`model_name`**: Discrete hardware part number or software SKU (never bundled, e.g. `MI3321G-W`) - **MANDATORY, NO NULL ALLOWED**.
- **`status`**: Unified lifecycle milestone status reflecting exact vendor terminology - **MANDATORY, NO NULL ALLOWED**.
- **`stage_date_utc`**: Strict UTC ISO 8601 timestamp (`YYYY-MM-DDTHH:MM:SSZ`) - **MANDATORY, NO NULL ALLOWED**.
- **`source_url`**: Canonical URL where the intelligence was extracted.
- **`os`**: Operating system / software runtime, or empty string `""` if not specified in source (no fake defaults).
- **`firmware`**: Semantic firmware version (e.g. `1.0.0`, `2.1.0`), or empty string `""` for hardware (no fake defaults).
- **`category`**: Product category (e.g. `PLC`, `Industrial PC`, `HMI`, `Inverter / Drive`).
- **`replacement`**: Successor or migration model recommendation.
- **`metadata`**: JSON-encoded string containing all extended attributes (`part_number`, `family`, `series`, `bulletin_code`, `detected_language`, etc.).
</details>

<details open>
<summary><b>Invariant 2: STRICT Exclusion of Internal Tracking Columns</b> (Click to collapse)</summary>

- The internal deduplication column **`Fingerprint` MUST NEVER be written to the master CSV export** (`output/all_vendors_lifecycle.csv`).
- Fingerprints are strictly ephemeral for memory lookups and per-vendor JSON manifests.
</details>

<details open>
<summary><b>Invariant 3: Strict SQL Database Compliance & Mandatory Field Invariants</b> (Click to collapse)</summary>

- **Strict Software / OS Empty Model Policy**: For hardware items (PLCs, drives, inverters, switches, sensors, cameras, etc.), `model_name` is **strictly mandatory and cannot be null or empty under any circumstance**. `model_name` is allowed to be empty/blank **ONLY** in case of software applications or well-known OS entries (e.g., Linux, Debian, Windows, Ubuntu, RHEL, CentOS, SUSE, FreeBSD, VxWorks, QNX).
- **Mandatory Non-Null Invariant**: `vendor_name`, `status`, and `stage_date_utc` are **100% mandatory with zero nulls allowed** in all cases. If a published bulletin lacks an explicit per-row date, the crawler automatically hydrates the date from the circular publication date or crawl snapshot date.
- **Single Entry Per Vendor (Zero Category Splitting)**: If a vendor manufactures products across IT, IoT, and OT (such as Cisco, Honeywell, Bosch, Schneider Electric, Hitachi, Huawei, etc.), there must be **ONLY ONE unified entry** for that specific vendor in `configs/vendors.yaml` with multi-sector coverage (`sectors: ["IT", "IoT", "OT"]`). Do NOT create separate entries per category. Link discovery traverses the vendor's entire website domain network map.
- **Optional Columns**: Technical attributes (`os`, `firmware`) are populated only when explicitly detected in vendor documentation, remaining SQL `NULL` (`""`) otherwise (zero artificial defaults).
- NEVER emit literal `"N/A"`, `"None"`, `"null"`, or `"TBD"` strings in date or version columns.
</details>

<details>
<summary><b>Invariant 4: Rule 2 — Exactly One Record Per Lifecycle Status Milestone</b> (Click to expand)</summary>

- If a hardware part lists multiple lifecycle dates (e.g., Last Time Buy date, End of Life date, and End of Support date), the extractor MUST explode that product into **separate, discrete records**—one for each milestone stage.
- Never bundle multiple lifecycle dates into a single row.
</details>

<details>
<summary><b>Invariant 5: Zero Hardcoded Config Defaults Policy</b> (Click to expand)</summary>

- NEVER inject synthetic defaults like `default_os: "Linux"` or `default_firmware: "1.0.0"` into `configs/vendors.yaml`.
- All technical specifications must be dynamically discovered by the crawler from the source page; if absent, they remain `None` / `""`.
</details>

<details>
<summary><b>Invariant 6: SSRF Boundary Enforcement & Private IP Blocking</b> (Click to expand)</summary>

- All crawl URLs must be validated with `scraper.security.is_safe_url(url, allowed_domains)`.
- Blocked targets: Loopback (`127.0.0.0/8`, `::1`), private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `fc00::/7`), cloud metadata (`169.254.169.254`), unspecified (`0.0.0.0`, `::`), decimal integer IPs (`2130706433`), and hex IPs (`0x7f000001`).
</details>

<details>
<summary><b>Invariant 7: Google Gemini Model Probing & Fallback Protocol</b> (Click to expand)</summary>

- When interacting with the Gemini API, default to `gemini-1.5-flash`.
- If Google AI Studio returns `404 NOT_FOUND` (account-specific model deprecation), the code must automatically probe candidate models in order:
  `["gemini-1.5-flash", "gemini-2.0-flash", "gemini-3.8-flash", "gemini-1.5-pro"]`.
- Always strip markdown code fences (` ```json ... ``` `) before calling `json.loads` on LLM responses.
</details>

<details>
<summary><b>Invariant 8: Vendor-Specific Lifecycle Statuses (No Fixed Status Whitelist)</b> (Click to expand)</summary>

- **Zero Status Limitations**: Manufacturers do NOT follow a single fixed status list (such as only EOL, LTB, EOS). Each vendor defines specialized lifecycle milestones (e.g., *Phase-Out Product, Delivery Release, Announced Discontinuation, Product Cancellation, End of Sale (EoS), Last Date of Support (LDoS), Classic, Limited, Obsolete, Active Mature, End of New Service, Repair Termination, Maintenance Only, Stop Shipment, Discontinued, End of Life*).
- The pipeline preserves the vendor's EXACT official lifecycle status in both `status` and `vendor_status` columns. Put NO restrictive whitelist, fixed enum, or artificial status limitation in code or documentation.
</details>

<details>
<summary><b>Invariant 9: 100% Crawl Coverage & Zero Missed Models Guarantee</b> (Click to expand)</summary>

- **Deep Document Ingestion**: Crawler deep-crawls technical bulletin notices linked as `.pdf` documents via `pypdf`, capturing hardware models only announced in PDFs.
- **Pagination Crawling**: Automatically discovers and follows paginated portals (`?page=`, `rel="next"`, `.pagination a`).
- **Hybrid Multi-Source Extraction**: Parses structured DOM / Next.js Apollo tables AND body markdown paragraphs, lists, and callout cards simultaneously.
- **Bulletin Date Hydration**: Dates are automatically extracted from bulletin codes (`EOL-PLC-240408-1961-SCA` -> `2024-04-08T00:00:00Z`) or headers to ensure the 4 mandatory fields are 100% populated.
- **Model Range & Suffix Expansion**: Unpacks model ranges (`1756-L61 to 1756-L63`), suffixes (`FX2N-16MR/ES, -16MT/ES`), and slash-delimited models (`ModelA / ModelB`).
</details>

<details open>
<summary><b>Invariant 10: Full Website Network Map Discovery & Zero Product Category Bias</b> (Click to collapse)</summary>

- **Sitemap & robots.txt Discovery**: The crawler autonomously checks `robots.txt` for `Sitemap:` directives and standard paths (`/sitemap.xml`, `/sitemap_index.xml`) to map the entire site architecture.
- **Unrestricted Category Traversal**: Link discovery MUST NOT be restricted to URLs containing "lifecycle". It traverses the full hierarchy of industrial product categories (controllers, drives, switches, sensors, optics, power, systems) across all OT, IoT, and IT sectors without category bias.
- **Multi-Depth Queue (BFS)**: Uses a priority-ordered queue up to `--max-depth` (default: 2) and `--max-pages` (default: 25) with deterministic priority sorting (urgent notices first, product category trees second, pagination links third).
- **URL Normalization**: Strips fragments, lowercases scheme/host, and trims non-root trailing slashes to guarantee zero loop cycles.
</details>

---

## 📁 Repository Directory Structure

```text
universal-lifecycle-scraper/
├── .agents/                    # Antigravity & AI Agent Customization Root
│   ├── skills/                 # Progressive on-demand skills (runbooks)
│   │   ├── crawler-pipeline-run/
│   │   ├── vendor-onboarding/
│   │   ├── pre-commit-gatekeeper/
│   │   ├── lifecycle-data-qa/
│   │   └── gemini-llm-tuning/
│   └── rules/                  # Workspace directory rules
├── configs/
│   └── vendors.yaml            # Config-driven registry of all 140 enterprise vendors
├── docs/
│   ├── ai/
│   │   └── AI_HARNESS.md       # Comprehensive AI Harness & architectural guide
│   └── ...
├── output/                     # Persistence artifacts
│   ├── all_vendors_lifecycle.csv # Consolidated master database CSV (10 columns, no Fingerprint)
│   └── <vendor>_lifecycle.json   # Modular per-vendor JSON datasets
├── artifacts/
│   ├── runs/                   # Per-run execution traces and audit manifests
│   ├── checkpoint.json         # Atomic checkpoint file for failure resumption
│   ├── dlq.json                # Dead letter queue forensic failure logs
│   └── cache/delta_cache.json  # Incremental content hash & ETag cache
├── scraper/                    # Core Python Package
│   ├── __init__.py
│   ├── checkpoint.py           # CheckpointManager for failure recovery and resumption
│   ├── config.py               # Path resolutions & environment variables
│   ├── crawl_engine.py         # UniversalAICrawler (Crawl4AI + DOM/Apollo + HTTP fallback)
│   ├── crawler_comparison.py   # Generic IDE vs Enterprise AI Crawler comparison engine
│   ├── delta_cache.py          # DeltaCache for content hash and ETag skipping
│   ├── dlq.py                  # DeadLetterQueue for forensic failure tracking
│   ├── gemini_extractor.py     # GeminiExtractor with candidate probing & fallback
│   ├── models.py               # Pydantic ProductRecord (OS/Software support, strict non-null)
│   ├── observability.py        # PipelineMetricsCollector & AlertDispatcher
│   ├── pipeline.py             # 6-stage visible LifecyclePipeline orchestrator
│   ├── security.py             # SSRF prevention & CSV formula injection defense
│   ├── storage.py              # MasterStorageManager with atomic file swapping
│   └── vendors.py              # 140-vendor resolution & multilingual stage translation
├── scripts/
│   ├── pre_commit_check.py     # Automated 8-stage pre-commit quality gate (Ruff, Mypy, AST, Tests)
│   └── install_hooks.py        # Cross-platform Git hook installer
├── tests/                      # Enterprise Automated Test Suite (126 tests)
│   ├── test_models.py
│   ├── test_security.py
│   ├── test_storage.py
│   ├── test_vendors.py
│   ├── test_gemini_extractor.py
│   ├── test_crawl_engine.py
│   ├── test_pipeline.py
│   ├── test_e2e_pipeline.py
│   └── ...
├── .pre-commit-config.yaml     # Standard pre-commit framework config
├── cli.py                      # Production command-line interface
├── server.py                   # Interactive Web Dashboard server
├── setup_key.py                # Interactive Google Gemini key setup utility
├── requirements.txt            # Python dependencies (google-genai, pydantic, pyyaml, etc.)
└── README.md                   # Complete repository documentation
```

---

## ⚡ Standard Operating Workflows

### 1. Running Unit & Integration Tests
Execute the full test suite locally:
```bash
python -m unittest discover tests -v
```
*Requirement: All 126 tests must pass with 100% green status before any code is approved.*

### 2. Running Linters & Type Checkers
```bash
# Ruff linter
python -m ruff check .
python -m ruff check --fix .

# Mypy static type checker
python -m mypy .
```

### 3. Running Pre-Commit Quality Checks
Validate AST syntax, Ruff linter, Mypy types, secret leakage prevention, 140-vendor schema, SQL compliance, test suite, and synthetic end-to-end flow:
```bash
python scripts/pre_commit_check.py
```
*If any check fails, the pre-commit script exits with code 1 and git commits are strictly aborted.*

### 4. Installing Git Pre-Commit Hook
Install the automated gate into `.git/hooks/pre-commit`:
```bash
python scripts/install_hooks.py
```

### 5. Launching Crawler Runs
```bash
# Single vendor crawl (e.g. Mitsubishi Electric or JTEKT Toyoda)
python cli.py --vendor mitsubishi
python cli.py --vendor toyoda

# Site-wide discovery crawl
python cli.py --vendor mitsubishi --site-crawl

# Sector-specific crawl (OT, IoT, IT)
python cli.py --sector OT

# Interactive Web Dashboard
python server.py 8000
```

### 6. Token & Cost Optimization Workflows
```bash
# Cap thinking budget on Flash models (eliminates reasoning token billing)
python cli.py --vendor siemens --thinking-budget 0

# Native Prompt Caching (up to 90% input token discount on repeated context)
python cli.py --sector OT --prompt-caching

# Asynchronous Batch Mode (50% discount on BOTH input and output tokens for bulk runs)
python cli.py --all-vendors --batch-mode
```
