# Enterprise Security & Threat Defense

## 1. Threat Defense Overview

The Universal Lifecycle Scraper operates in mission-critical IT/OT environments where scraped data directly influences vulnerability management, asset obsolescence planning, and supply chain security. The system implements multi-layered security controls to protect the harness and downstream enterprise data stores.

---

## 2. Server-Side Request Forgery (SSRF) Defense (`scraper/security.py`)

All network requests issued by the crawler, HTTP fallbacks, and endpoint auditors are gated by `is_safe_url`:

1. **Dangerous Scheme Neutralization**:
   - Only `http` and `https` schemes are permitted. Schemes such as `file://`, `gopher://`, `ftp://`, `data:`, or `javascript:` are immediately rejected.
2. **Private & Loopback Address Blocking**:
   - Resolves DNS hostnames and verifies that the destination IP does NOT fall into RFC 1918 private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.0/8`), or link-local ranges (`169.254.0.0/16`).
3. **Cloud Metadata Defense**:
   - Requests targeting cloud provider metadata services (e.g., `169.254.169.254`, `metadata.google.internal`) are blocked.
4. **Domain Scope Enforcement**:
   - In single-vendor mode, URLs must match the vendor's declared `allowed_domains` list in `configs/vendors.yaml`.

---

## 3. CSV Formula Injection Defense

When datasets are opened in spreadsheet tools (Microsoft Excel, LibreOffice Calc, Google Sheets), cell values starting with special execution characters can trigger dynamic formula execution or data exfiltration.

The sanitizer `sanitize_csv_cell` neutralizes dangerous prefixes:
- If a string begins with `=`, `+`, `-`, or `@`, the prefix is neutralized (prefixed with `'` or stripped depending on field type).
- Cell contents are bounded to maximum field length limits to prevent buffer overflow attacks or memory exhaustion.

---

## 4. Input Sanitization & Threat Inspection

Every extracted token (model name, alias, vendor, status, replacement) undergoes automated inspection for injection attacks via `inspect_security_threats`:

1. **SQL Injection (SQLi)**:
   - Detects SQL keywords in conjunction with malicious payload signatures (e.g. `UNION SELECT`, `DROP TABLE`, `' OR '1'='1`).
2. **Cross-Site Scripting (XSS)**:
   - Blocks `<script>`, `javascript:`, `onerror=`, `onload=`, and HTML event injection vectors.
3. **Path Traversal**:
   - Detects `../`, `..\\`, and absolute path manipulation attempts.
4. **Command Injection**:
   - Blocks shell metacharacters (`;`, `|`, `&`, `` ` ``, `$()`) in values passed to OS-level utilities.

---

## 5. Credential Hygiene & API Key Isolation

1. **Zero Hardcoded Secrets**:
   - API keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) are read strictly from environment variables or local `.env` files.
   - `.env` is permanently excluded via `.gitignore`.
2. **Pre-Commit Secret Scanning**:
   - Step 3 of `pre_commit_check.py` scans all committed code for leaked keys, tokens, or private credentials.

