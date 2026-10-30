"""
Configuration management for Universal Multi-Vendor EOL & Lifecycle AI Scraper.
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

# Universal Multi-Provider AI Settings (Gemini, OpenAI, Claude, Azure, AWS Bedrock, Ollama)
AI_PROVIDER = os.getenv("AI_PROVIDER", os.getenv("LLM_PROVIDER", "auto")).lower()
AI_MODEL = os.getenv("AI_MODEL", os.getenv("LLM_MODEL", ""))

# Google Gemini Settings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Default to the universally available production model gemini-3.5-flash-lite
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# OpenAI / Compatible Settings (Local Ollama, vLLM, OpenRouter)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")

# Anthropic Claude Settings
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Microsoft Azure OpenAI Settings
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

# Amazon AWS Bedrock Settings
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION_NAME = os.getenv("AWS_REGION_NAME", "us-east-1")

# Universal Multi-Provider AI Token & Cost Optimization Settings
# 1. Thinking Budget: 0 disables/minimizes reasoning tokens on reasoning models, slashing output token costs
AI_THINKING_BUDGET = int(os.getenv("AI_THINKING_BUDGET", os.getenv("GEMINI_THINKING_BUDGET", "0"))) if (os.getenv("AI_THINKING_BUDGET", os.getenv("GEMINI_THINKING_BUDGET", "0"))).isdigit() else 0
GEMINI_THINKING_BUDGET = AI_THINKING_BUDGET  # Backward compatibility alias

# 2. Prompt Caching: Reuses repetitive extraction instructions/schemas across calls (up to 90% input discount)
AI_ENABLE_PROMPT_CACHING = os.getenv("AI_ENABLE_PROMPT_CACHING", os.getenv("GEMINI_ENABLE_PROMPT_CACHING", "true")).lower() in ("true", "1", "yes")
AI_PROMPT_CACHE_TTL = os.getenv("AI_PROMPT_CACHE_TTL", os.getenv("GEMINI_PROMPT_CACHE_TTL", "3600s"))
GEMINI_ENABLE_PROMPT_CACHING = AI_ENABLE_PROMPT_CACHING  # Backward compatibility alias
GEMINI_PROMPT_CACHE_TTL = AI_PROMPT_CACHE_TTL  # Backward compatibility alias

# 3. Batch Mode: Asynchronous batch API processing with 50% discount on both input and output tokens
AI_BATCH_MODE = os.getenv("AI_BATCH_MODE", os.getenv("GEMINI_BATCH_MODE", "false")).lower() in ("true", "1", "yes")
GEMINI_BATCH_MODE = AI_BATCH_MODE  # Backward compatibility alias

# Reference Target EOL Portals
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
DEFAULT_JSON_OUTPUT = OUTPUT_DIR / "all_vendors_lifecycle.json"
DEFAULT_CSV_OUTPUT = OUTPUT_DIR / "all_vendors_lifecycle.csv"
