"""
Universal Multi-Provider AI Lifecycle Extractor.
High-level generic extractor interface supporting pluggable LLM backends:
Google Gemini, OpenAI, Anthropic Claude, Microsoft Azure OpenAI, AWS Bedrock, and Local Ollama.
"""

from scraper.gemini_extractor import (
    GeminiExtractor,
    LLMExtractor,
    UniversalAIExtractor,
    _gemini_item_to_product_record,
    clean_token_efficient_markdown,
    extract_text_from_pdf_bytes,
)
from scraper.models import (
    GeminiExtractionBatch,
    GeminiProductItem,
    ProductRecord,
    extract_date_from_bulletin_code,
    is_valid_product_model,
    normalize_firmware_version,
    parse_to_utc_iso,
)
from scraper.providers import (
    DEFAULT_MODELS,
    SUPPORTED_PROVIDERS,
    detect_provider_from_model,
    normalize_provider_name,
    resolve_provider_and_model,
)
from scraper.vendors import normalize_stage_name

# Canonical Generic Aliases
AIExtractor = UniversalAIExtractor
EnterpriseAIExtractor = UniversalAIExtractor

__all__ = [
    "AIExtractor",
    "LLMExtractor",
    "UniversalAIExtractor",
    "EnterpriseAIExtractor",
    "GeminiExtractor",
    "GeminiProductItem",
    "GeminiExtractionBatch",
    "ProductRecord",
    "DEFAULT_MODELS",
    "SUPPORTED_PROVIDERS",
    "resolve_provider_and_model",
    "detect_provider_from_model",
    "normalize_provider_name",
    "normalize_stage_name",
    "normalize_firmware_version",
    "is_valid_product_model",
    "parse_to_utc_iso",
    "extract_date_from_bulletin_code",
    "clean_token_efficient_markdown",
    "extract_text_from_pdf_bytes",
    "_gemini_item_to_product_record",
]
