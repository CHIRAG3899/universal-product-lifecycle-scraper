"""
Multi-Provider LLM Abstraction Layer.
Enables plug-and-play AI extraction across:
  - Google Gemini (native GenAI SDK with Prompt Caching, Thinking Budget, Batch API)
  - OpenAI (gpt-4o, gpt-4o-mini, o1, o3)
  - Anthropic Claude (claude-3-5-sonnet, claude-3-5-haiku)
  - Microsoft Azure OpenAI (azure/<deployment>)
  - Amazon AWS Bedrock (bedrock/<model-id>)
  - Local / Ollama / vLLM / OpenRouter (OpenAI-compatible)
"""

import logging
import os
from typing import Dict, Optional, Tuple

logger = logging.getLogger("ai_scraper.providers")

SUPPORTED_PROVIDERS = (
    "gemini",
    "openai",
    "anthropic",
    "claude",
    "azure",
    "aws",
    "bedrock",
    "ollama",
    "local",
    "openrouter",
    "auto",
)

DEFAULT_MODELS: Dict[str, str] = {
    "gemini": "gemini-3.5-flash-lite",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-20241022",
    "claude": "claude-3-5-haiku-20241022",
    "azure": "azure/gpt-4o-mini",
    "aws": "bedrock/anthropic.claude-3-5-haiku-20241022-v1:0",
    "bedrock": "bedrock/anthropic.claude-3-5-haiku-20241022-v1:0",
    "ollama": "ollama/llama3.2",
    "local": "ollama/llama3.2",
    "openrouter": "openrouter/google/gemini-2.5-flash",
}


def normalize_provider_name(provider: Optional[str]) -> str:
    """Normalizes provider alias string to standard identifier."""
    if not provider:
        return "auto"
    p = provider.strip().lower()
    if p in ("claude", "anthropic"):
        return "anthropic"
    if p in ("aws", "bedrock", "aws_bedrock"):
        return "bedrock"
    if p in ("azure", "azure_openai"):
        return "azure"
    if p in ("ollama", "local"):
        return "ollama"
    if p in ("google", "gemini", "google_gemini"):
        return "gemini"
    return p


def detect_provider_from_model(model_name: Optional[str]) -> Optional[str]:
    """Infers AI provider from common model naming conventions."""
    if not model_name:
        return None
    m = model_name.strip().lower()
    if m.startswith("gemini-") or m.startswith("models/gemini"):
        return "gemini"
    if m.startswith("gpt-") or m.startswith("o1-") or m.startswith("o3-") or m.startswith("text-embedding-"):
        return "openai"
    if m.startswith("claude-"):
        return "anthropic"
    if m.startswith("azure/"):
        return "azure"
    if m.startswith("bedrock/"):
        return "bedrock"
    if m.startswith("ollama/"):
        return "ollama"
    if m.startswith("openrouter/"):
        return "openrouter"
    return None


def resolve_provider_and_model(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Tuple[str, str, Optional[str]]:
    """
    Deterministically resolves the active AI provider, model name, and API key.

    Resolution Priority:
    1. Explicit arguments passed to constructor / CLI (`--provider`, `--model`, `--api-key`)
    2. Model prefix inference (e.g. `gpt-4o` -> openai, `claude-3-5` -> anthropic)
    3. Global environment configuration (`AI_PROVIDER`, `AI_MODEL`)
    4. Auto-detection based on configured API keys in environment
    5. Default to `gemini` with `gemini-3.5-flash-lite`
    """
    explicit_provider = bool(provider and provider.strip() and provider.strip().lower() != "auto")
    req_provider = normalize_provider_name(provider) if explicit_provider else "auto"
    req_model = (model or "").strip()

    # Step 1: Infer provider from model name if provider was not explicitly passed
    if not explicit_provider and req_model:
        inferred = detect_provider_from_model(req_model)
        if inferred:
            req_provider = inferred

    # Step 2: Check AI_PROVIDER from env if still auto
    if req_provider in ("auto", ""):
        env_prov = normalize_provider_name(os.getenv("AI_PROVIDER", "auto"))
        if env_prov not in ("auto", ""):
            req_provider = env_prov

    # Step 3: Auto-detect provider based on active environment API keys if still auto
    if req_provider in ("auto", ""):
        if api_key and (api_key.startswith("sk-ant-") or "claude" in api_key.lower()):
            req_provider = "anthropic"
        elif api_key and (api_key.startswith("sk-") or api_key.startswith("sess-")):
            req_provider = "openai"
        elif api_key:
            req_provider = "gemini"
        elif os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_API_KEY") != "your_gemini_api_key_here":
            req_provider = "gemini"
        elif os.getenv("OPENAI_API_KEY"):
            req_provider = "openai"
        elif os.getenv("ANTHROPIC_API_KEY"):
            req_provider = "anthropic"
        elif os.getenv("AZURE_OPENAI_API_KEY"):
            req_provider = "azure"
        elif os.getenv("AWS_ACCESS_KEY_ID"):
            req_provider = "bedrock"
        else:
            req_provider = "gemini"

    # Step 4: Resolve model name
    final_model = req_model
    if not final_model:
        env_model = (os.getenv("AI_MODEL", "")).strip()
        if env_model:
            inferred_prov = detect_provider_from_model(env_model)
            if inferred_prov == req_provider or not inferred_prov:
                final_model = env_model

    if not final_model:
        if req_provider == "gemini":
            final_model = os.getenv("GEMINI_MODEL", "") or DEFAULT_MODELS["gemini"]
        else:
            final_model = DEFAULT_MODELS.get(req_provider, "gemini-3.5-flash-lite")

    # Step 5: Resolve API key for the chosen provider
    final_key = api_key
    if not final_key:
        if req_provider == "gemini":
            final_key = os.getenv("GEMINI_API_KEY", "")
        elif req_provider == "openai":
            final_key = os.getenv("OPENAI_API_KEY", "")
        elif req_provider == "anthropic":
            final_key = os.getenv("ANTHROPIC_API_KEY", "")
        elif req_provider == "azure":
            final_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        elif req_provider == "bedrock":
            final_key = os.getenv("AWS_ACCESS_KEY_ID", "")

    return req_provider, final_model, final_key
