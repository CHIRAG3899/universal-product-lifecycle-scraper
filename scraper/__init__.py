"""
Universal Multi-Vendor Product Lifecycle Intelligence Scraper Package.
Pluggable multi-provider architecture supporting headless crawling and structured AI extraction.
"""

from scraper.adapters import (
    FrameworkAdapter,
    LangChainToolAdapter,
    LifecyclePlugin,
    get_framework_adapter,
)
from scraper.ai_extractor import (
    AIExtractor,
    GeminiExtractor,
    LLMExtractor,
    UniversalAIExtractor,
)
from scraper.crawl_engine import MitsubishiAICrawler, UniversalAICrawler
from scraper.models import ProductRecord, ScrapedDataset, parse_to_utc_iso
from scraper.pipeline import LifecyclePipeline
from scraper.providers import DEFAULT_MODELS, SUPPORTED_PROVIDERS, resolve_provider_and_model
from scraper.security import (
    SecurityThreatError,
    detect_command_injection,
    detect_nosql_injection,
    detect_path_traversal,
    detect_sql_injection,
    detect_xss,
    inspect_security_threats,
)
from scraper.vendors import VENDOR_PROFILES, detect_vendor_from_url_or_text, normalize_stage_name

__all__ = [
    "ProductRecord",
    "ScrapedDataset",
    "parse_to_utc_iso",
    "AIExtractor",
    "UniversalAIExtractor",
    "LLMExtractor",
    "GeminiExtractor",
    "UniversalAICrawler",
    "MitsubishiAICrawler",
    "LifecyclePipeline",
    "detect_vendor_from_url_or_text",
    "normalize_stage_name",
    "VENDOR_PROFILES",
    "SUPPORTED_PROVIDERS",
    "DEFAULT_MODELS",
    "resolve_provider_and_model",
    "FrameworkAdapter",
    "LifecyclePlugin",
    "LangChainToolAdapter",
    "get_framework_adapter",
    "SecurityThreatError",
    "detect_sql_injection",
    "detect_xss",
    "detect_path_traversal",
    "detect_command_injection",
    "detect_nosql_injection",
    "inspect_security_threats",
]
