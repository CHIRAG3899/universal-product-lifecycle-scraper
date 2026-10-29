# Contributing to Universal Multi-Vendor EOL & Lifecycle AI Scraper

Thank you for contributing to the **Universal Multi-Vendor EOL & Lifecycle AI Scraper**! This project provides enterprise-grade, observable, and reproducible product lifecycle tracking across 140+ manufacturers in Operational Technology (OT), Internet of Things (IoT), and Enterprise IT.

---

## 🏛️ Architecture Invariants

All contributions must strictly adhere to the project's core invariants:

1. **Vendor-Specific Status (Zero Artificial Enums)**:
   - Always preserve the exact manufacturer status string (*Phase-Out*, *Delivery Release*, *Classic*, *Discontinued*, *End of Support*, etc.). Do not normalize or map to an artificial enum.
2. **Strict Non-Null Invariant**:
   - `vendor_name`, `status`, and `stage_date_utc` **must never be null or empty**.
   - `stage_date_utc` must strictly conform to ISO 8601 UTC format (`YYYY-MM-DDTHH:MM:SSZ`).
   - For hardware records, `model_name` is mandatory. For Operating Systems and Software lifecycles (e.g. Windows 7, RHEL, Ubuntu), `model_name` may be empty/blank, with the OS specified in `os` or `category`.
3. **Master Database Schema (10 Columns)**:
   - Exactly 10 columns: `vendor_name`, `model_name`, `status`, `stage_date_utc`, `source_url`, `os`, `firmware`, `category`, `replacement`, `metadata`.
   - The internal deduplication `fingerprint` column must never be exposed in `output/all_vendors_lifecycle.csv`.
4. **SSRF Guard & Domain Safety**:
   - Every network request must validate domain whitelists and block private/loopback/metadata IP ranges (`127.0.0.0/8`, `10.0.0.0/8`, `169.254.169.254`, `::1`).
5. **Zero Category Bias**:
   - Vendor entry points must be broad top-level portals or master lifecycle listings. Do not target single sub-category hardware models (e.g. avoid `/switches/industrial-ethernet-switches/`).

---

## 🚀 Setting Up Development Environment

```bash
# 1. Clone the repository
git clone https://github.com/your-org/universal-lifecycle-scraper.git
cd universal-lifecycle-scraper

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
pip install ruff mypy pytest types-PyYAML

# 4. Install Git Pre-Commit Hooks
python scripts/install_hooks.py
```

---

## 🛡️ Running Pre-Commit Quality Gate

Before submitting a Pull Request, run the 8-stage automated quality gate:

```bash
python scripts/pre_commit_check.py
```

This gate runs:
- Stage 1: AST Compilation & Syntax Integrity
- Stage 2: Ruff Linter & Formatting Check
- Stage 3: Mypy Static Type Checking
- Stage 4: Secret Leak & SSRF Guard Verification
- Stage 5: Multi-Vendor Catalog & Key Collision Scanner
- Stage 6: Database Schema & Zero-Null Compliance Check
- Stage 7: Full Unit Test Suite (135+ tests)
- Stage 8: Synthetic End-to-End Pipeline Verification

---

## ➕ Adding a New Vendor

1. Open [`configs/vendors.yaml`](configs/vendors.yaml).
2. Append the vendor configuration with unique ID, sector (`OT`, `IoT`, or `IT`), domain whitelist, and top-level entry points:
   ```yaml
     acme_corp:
       id: acme_corp
       name: Acme Corporation
       sector: OT
       website: https://www.acme.com
       allowed_domains:
       - acme.com
       entry_points:
       - name: Acme_Lifecycle_Portal
         url: https://www.acme.com/support/lifecycle
         region: Global
         crawler_type: dom_table
   ```
3. Run `python scripts/pre_commit_check.py` to verify that there are zero key collisions or domain conflicts.
