---
name: crawler-pipeline-run
description: >-
  Use this skill when the user asks to run, test, or trigger the multi-vendor crawler pipeline,
  execute crawls across OT, IoT, or IT vendors, perform site-wide discovery crawls, or run the web dashboard.
---

# Crawler Pipeline Runbook

This skill provides step-by-step runbook instructions for running the **Universal Multi-Vendor EOL & Lifecycle AI Scraper** across **140 enterprise vendors** (54 OT, 44 IoT, 42 IT).

---

## 🚀 Execution Modes

### Mode 1: Crawl a Single Vendor via CLI
To crawl a specific vendor (e.g., Mitsubishi Electric, JTEKT Toyoda, Siemens, Cisco, Dell):
```bash
# Mitsubishi Electric
python cli.py --vendor mitsubishi

# JTEKT Toyoda (Toyopuc PLCs)
python cli.py --vendor toyoda

# Siemens with explicit Gemini model
python cli.py --vendor siemens --model gemini-3.5-flash-lite
```

### Mode 2: Site-Wide Domain Discovery Crawl
Full-site discovery with unlimited pages (`max_pages=0`) and depth (`max_depth=0`) is enabled by default:
```bash
python cli.py --vendor mitsubishi

# To crawl entry-point URLs only (without domain recursion):
python cli.py --vendor mitsubishi --no-site-crawl

# Crawl ALL 140 enterprise vendors with 3 parallel workers:
python cli.py --all-vendors --concurrency 3
```

### Mode 3: Sector-Specific Batch Crawl
To crawl all vendors within an industrial sector:
```bash
# Operational Technology (54 vendors, including Toyoda, Siemens, Rockwell)
python cli.py --sector OT

# Internet of Things (44 vendors, including Cisco Meraki, MultiTech, Advantech)
python cli.py --sector IoT

# Enterprise IT & Networking (42 vendors, including Cisco, HPE, Dell, Fortinet)
python cli.py --sector IT
```

### Mode 4: Launch the Interactive Web Dashboard
To launch the real-time monitoring and control dashboard:
```bash
python server.py 8000
```
Navigate to `http://localhost:8000` to monitor the 6-stage stepper, view live logs, filter sectors, and trigger crawls.

---

## 💰 Token & Cost Optimization Flags
```bash
# 1. Cap thinking budget to 0 on Flash models (cuts output reasoning token charges)
python cli.py --vendor mitsubishi --thinking-budget 0

# 2. Native Prompt Caching (up to 90% discount on input tokens)
python cli.py --sector OT --prompt-caching

# 3. Asynchronous Batch API (50% discount on both input and output tokens)
python cli.py --all-vendors --batch-mode
```

---

## 🔎 100% Coverage & Strict Zero-Null Invariant
The crawler engine guarantees complete coverage with zero dropped products:
- **Mandatory 4 Fields**: `vendor_name`, `model_name`, `status`, and `stage_date_utc` are 100% non-null. Missing row dates are hydrated from bulletin publication headers or snapshot timestamps.
- **PDF Bulletin Ingestion**: Linked `.pdf` notices and discontinuation bulletins are parsed with `pypdf`, surfacing models documented exclusively in official technical circulars.
- **Pagination Discovery**: Automatic discovery and traversal of pagination links (`?page=`, `rel="next"`, `.pagination a`).
- **Hybrid Multi-Source Parsing**: Extracts simultaneously from DOM/Apollo GraphQL tables and full-text markdown paragraphs, callouts, and lists.
- **Suffix & Range Expansion**: Multi-model rows and compressed catalog strings (`FX2N-16MR/ES, -16MT/ES`, `1756-L61 to 1756-L63`) are expanded into individual product records.
- **Zero Status Limitations**: Vendor-specific lifecycle terminology (*Phase-Out Product, Classic, Delivery Release, etc.*) is strictly preserved without arbitrary status filters.
