#!/usr/bin/env python3
"""
Installer for Enterprise Git Pre-Commit Hook.
Detects the repository root and installs the pre-commit quality gate into .git/hooks/pre-commit.
Works seamlessly on Windows, macOS, and Linux.
"""

import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def get_git_dir() -> Path:
    """Finds the .git directory for the current repository."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            check=True
        )
        git_dir_str = res.stdout.strip()
        git_dir = Path(git_dir_str)
        if not git_dir.is_absolute():
            git_dir = (BASE_DIR / git_dir).resolve()
        return git_dir
    except Exception as e:
        print(f"[ERROR] Could not locate .git directory: {e}")
        sys.exit(1)


def install_hook():
    git_dir = get_git_dir()
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_file = hooks_dir / "pre-commit"

    hook_content = """#!/usr/bin/env bash
# ==============================================================================
# Enterprise Multi-Vendor Lifecycle Scraper: Pre-Commit Quality & Integrity Gate
# ==============================================================================
set -e

# Detect working python executable (verify execution to avoid Windows Store stubs)
PY_BIN=""
for candidate in python py python3; do
    if "$candidate" -c "import sys" >/dev/null 2>&1; then
        PY_BIN="$candidate"
        break
    fi
done

if [ -z "$PY_BIN" ]; then
    echo "[!] Error: Working Python interpreter not found in PATH. Pre-commit check aborted."
    exit 1
fi

GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)

echo "[*] Running Enterprise Pre-Commit Quality Gate (AST, Ruff, Mypy, Security, 140 Vendors, DB Schema, Tests, E2E Flow)..."

# Search for pre_commit_check.py
SCRIPT_CANDIDATE_0="$GIT_ROOT/scripts/pre_commit_check.py"
SCRIPT_CANDIDATE_1="$GIT_ROOT/universal-lifecycle-scraper/scripts/pre_commit_check.py"

if [ -f "$SCRIPT_CANDIDATE_0" ]; then
    "$PY_BIN" "$SCRIPT_CANDIDATE_0"
    STATUS=$?
elif [ -f "$SCRIPT_CANDIDATE_1" ]; then
    "$PY_BIN" "$SCRIPT_CANDIDATE_1"
    STATUS=$?
else
    echo "[!] Notice: pre_commit_check.py not found in working tree. Skipping."
    exit 0
fi

if [ $STATUS -ne 0 ]; then
    echo ""
    echo "================================================================================"
    echo "  [COMMIT REJECTED] Pre-commit checks failed! You cannot commit failing code."
    echo "  Fix all Ruff, Mypy, security, schema, or test errors before committing."
    echo "================================================================================"
    exit 1
fi

exit 0
"""

    with open(hook_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(hook_content)

    # Attempt to set chmod +x on Unix/macOS/Git-Bash
    try:
        os.chmod(hook_file, 0o755)
    except Exception:
        pass

    print("\n[SUCCESS] Enterprise Git pre-commit hook installed successfully!")
    print(f"  Target: {hook_file}")
    print("  The quality gate will now automatically run before every 'git commit'.")
    print("  To run checks manually at any time, run: python scripts/pre_commit_check.py\n")


if __name__ == "__main__":
    install_hook()
