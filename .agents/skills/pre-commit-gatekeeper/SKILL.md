---
name: pre-commit-gatekeeper
description: >-
  Use this skill when testing code integrity, running pre-commit checks, troubleshooting
  failed commits, installing Git hooks, or auditing Ruff, Mypy, secret scanning, and AST compilation.
---

# Pre-Commit Quality Gatekeeper Runbook

This skill outlines the operation, execution, and troubleshooting procedures for the repository's **8-stage enterprise pre-commit quality gate** ([`scripts/pre_commit_check.py`](scripts/pre_commit_check.py)) and Git hook ([`scripts/install_hooks.py`](scripts/install_hooks.py)).

> [!IMPORTANT]
> **Strict Commit Blocking ("Don't commit if they don't pass")**:
> Any failure in Ruff linting, Mypy static typing, unit tests, secret scanning, or database invariants **strictly aborts `git commit` with exit code 1**. Commits are never permitted on failing code.

---

## 🛠️ Running the Pre-Commit Gateway

To execute the entire 8-stage gate manually:
```bash
python scripts/pre_commit_check.py
```

### Running Individual Linters & Static Analysis
```bash
# 1. Ruff linter & auto-fix
python -m ruff check .
python -m ruff check --fix .

# 2. Mypy static type checker
python -m mypy .

# 3. Full unit and regression test suite
python -m unittest discover tests -v
```

---

## 🚦 The 8 Quality Gate Stages

| Stage | Check Description | Tool / Guard | Failure Criteria & Mitigation |
|---|---|---|---|
| **Check 1** | **AST Python Syntax & Compilation** | `ast.parse()`, `py_compile` | Fails if any Python file has invalid syntax, missing colons, or unparseable blocks across all 35+ files. |
| **Check 2** | **Ruff Linter & Style Quality Gate** | `ruff check .` | **Strict Commit Blocker**: Fails on any lint rule violation, unused import, undefined variable, or style defect. Run `ruff check --fix .` to auto-resolve. |
| **Check 3** | **Mypy Static Type Checker & Annotations** | `mypy .` | **Strict Commit Blocker**: Fails on any type signature mismatch, `NoneType` attribute access, or invalid return type across all 33+ source files. |
| **Check 4** | **Security & Secret Leak Guard** | Regex & IP parser | Fails if `.env` is staged, if unmasked API keys (`AIzaSy...`) or private keys are found in tracked files, or if SSRF private IP risks are present. |
| **Check 5** | **140-Vendor Config Integrity** | `vendors.yaml` schema validator | Fails if `configs/vendors.yaml` has syntax errors, missing fields, invalid domain whitelists, or forbidden `default_os`/`default_firmware`. |
| **Check 6** | **Database Schema & Zero-Null Invariant** | Schema & null auditor | Fails if `all_vendors_lifecycle.csv` contains `Fingerprint`, has literal `"N/A"`, or if any of the **4 mandatory fields** (`vendor_name`, `model_name`, `status`, `stage_date_utc`) are null or empty. |
| **Check 7** | **Comprehensive Test Suite** | `unittest` (126 tests) | Fails if any unit, edge-case, or integration test fails. Run `python -m unittest discover tests -v` to debug. |
| **Check 8** | **End-to-End Synthetic Flow** | `LifecyclePipeline` sandbox | Fails if pipeline components fail to execute Discovery, Extraction, Normalisation, Sanitisation, Deduplication, and Export with synthetic data. |

---

## 🔧 Installing or Reinstalling Git Hooks

If the pre-commit hook is missing from `.git/hooks/pre-commit`:
```bash
python scripts/install_hooks.py
```

This writes an executable Git hook script into `.git/hooks/pre-commit` which automatically executes `scripts/pre_commit_check.py` on `git commit`, rejecting any commit with code 1 if any check fails.
