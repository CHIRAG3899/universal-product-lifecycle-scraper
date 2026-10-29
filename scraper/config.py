"""
Configuration management for Mitsubishi EOL AI Scraper.
Supports environment variables (.env), CLI flags, and sensible defaults.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Load .env if present
load_dotenv(BASE_DIR / ".env")

# Google Gemini Settings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Default to the universally available production model gemini-3.5-flash-lite
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# Gemini Token & Cost Optimization Settings
# 1. Thinking Budget: 0 disables/minimizes reasoning tokens on Flash models, slashing output token costs
GEMINI_THINKING_BUDGET = int(os.getenv("GEMINI_THINKING_BUDGET", "0")) if os.getenv("GEMINI_THINKING_BUDGET", "0").isdigit() else 0
# 2. Prompt Caching: Reuses repetitive extraction instructions/schemas across calls (up to 90% input discount)
GEMINI_ENABLE_PROMPT_CACHING = os.getenv("GEMINI_ENABLE_PROMPT_CACHING", "true").lower() in ("true", "1", "yes")
GEMINI_PROMPT_CACHE_TTL = os.getenv("GEMINI_PROMPT_CACHE_TTL", "3600s")
# 3. Batch Mode: Asynchronous batch API processing with 50% discount on both input and output tokens
GEMINI_BATCH_MODE = os.getenv("GEMINI_BATCH_MODE", "false").lower() in ("true", "1", "yes")

# Mitsubishi Target EOL Portals
MITSUBISHI_EOL_URLS = [
    # Primary European Factory Automation EOL portal (comprehensive Next.js / GraphQL portal)
    "https://se-fa.mitsubishielectric.com/fa/se_en/support/product-life-cycle-stage-eol",
    # Nordic regional mirror
    "https://no-fa.mitsubishielectric.com/fa/no_en/support/Product-Life-Cycle-Information",
]

# Crawler Settings
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT_SEC = 30
HEADLESS_BROWSER = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")

# Default export locations
DEFAULT_JSON_OUTPUT = OUTPUT_DIR / "mitsubishi_eol_products.json"
DEFAULT_CSV_OUTPUT = OUTPUT_DIR / "mitsubishi_eol_products.csv"
