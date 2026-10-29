# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

---

## 🔒 Security Architecture & Guardrails

The **Universal Multi-Vendor EOL & Lifecycle AI Scraper** implements defense-in-depth safety controls:

1. **Server-Side Request Forgery (SSRF) Guard**:
   - Strictly validates all target URLs before fetching.
   - Denies requests to IPv4/IPv6 loopback, RFC 1918 private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), and AWS/GCP cloud metadata endpoints (`169.254.169.254`).
   - Resolves target hostnames via DNS and rejects requests if resolved IP maps to restricted blocks.
2. **CSV Formula Injection Shield**:
   - Sanitizes untrusted model names or descriptions that start with spreadsheet command prefixes (`=`, `+`, `-`, `@`, `\t`, `\r`) by prepending a single quote (`'`).
3. **Secret Leak Prevention**:
   - Ensures `.env` files and live API keys are blocked by `.gitignore` and flagged by pre-commit hooks.
4. **Dead Letter Queue (DLQ)**:
   - Captures forensic logs of all fetch anomalies in `artifacts/dlq.json` without storing sensitive authentication credentials.

---

## Reporting a Vulnerability

If you discover a security vulnerability, please report it via private security advisory or email the maintainers directly. Do not report security vulnerabilities via public GitHub issues.
