---
name: crawler-pipeline-run
description: >-
  Use this skill when the user asks to run, test, or trigger the multi-vendor crawler pipeline,
  execute crawls across OT, IoT, or IT vendors, perform site-wide discovery crawls, or run the web dashboard.
---

# Crawler Pipeline Runbook

This skill provides step-by-step runbook instructions for running the **Universal Multi-Vendor EOL & Lifecycle AI Scraper** across **219 enterprise vendors** spanning Operational Technology (OT), Internet of Things (IoT), Information Technology (IT), and Internet of Medical Things (IoMT).

---

## 🚀 Execution Modes

### Mode 1: Crawl a Single Vendor via CLI
To crawl a specific vendor (e.g., Rockwell Automation, Siemens, Cisco, Dell, Mitsubishi Electric, Moxa):
```bash
# Rockwell Automation (Allen-Bradley)
python cli.py --vendor rockwell_automation

# Siemens
python cli.py --vendor siemens

# Cisco Systems
python cli.py --vendor cisco

# Mitsubishi Electric
python cli.py --vendor mitsubishi
```

### Mode 2: Sector-Specific Batch Crawl
To crawl all vendors within an industrial sector:
```bash
# Operational Technology (74 vendors: Siemens, Rockwell, ABB, Schneider, Omron, WAGO, Phoenix Contact)
python cli.py --sector OT

# Internet of Things (66 vendors: STMicroelectronics, TI, NXP, Advantech, Moxa, Particle)
python cli.py --sector IoT

# Enterprise IT & Networking (53 vendors: Cisco, Juniper, HPE, Dell, Fortinet, Arista, IBM)
python cli.py --sector IT

# Internet of Medical Things (26 vendors: Smiths Medical, Hillrom, GE HealthCare, Philips, Dräger)
python cli.py --sector IoMT
```

### Mode 3: Crawl All Vendors with High-Throughput HTTP/2 & Staging Buffer
```bash
# High-speed crawl across all 219 vendors with 3 parallel workers and SQLite buffer staging
python cli.py --all-vendors --concurrency 3
```

### Mode 4: Launch the Interactive Web Dashboard
```bash
python server.py 8000
```
Navigate to `http://localhost:8000` to monitor the 6-stage lifecycle pipeline, track live crawl metrics, filter sectors, and inspect staged records.

---

## 💰 Performance & Cost Optimization Flags
```bash
# 1. Zero-Thinking Fast Path: Minimizes reasoning tokens on structural data extraction
python cli.py --vendor mitsubishi --thinking-budget 0

# 2. Native Prompt Caching: Slashing input token costs by up to 90%
python cli.py --sector OT --prompt-caching

# 3. Asynchronous Batch API: 50% discount on both input and output tokens for large PDF bulletins
python cli.py --all-vendors --batch-mode
```

---

## 🔎 Data Quality Invariants & Data Contract
- **Dual CSV Separation**: Outputs are strictly partitioned into `output/eol_products_lifecycle.csv` and `output/active_products_lifecycle.csv`.
- **6 Canonical Status ENUMs**: Every vendor status is mapped to `Active`, `Active Mature`, `Phase Out`, `End of Sale`, `End of Support`, or `Obsolete`.
- **One Record Per Canonical Status**: Exactly one row per `(vendor_name, model_name, canonical_status)` combination.
- **Latest Date Retention**: When milestone duplicates collide, the record with the latest date is preserved and secondary attributes are merged.
- **Zero Date Leaks**: `aliases` and `replacement` columns strictly contain genuine product models and reject calendar dates or narrative boilerplate.
