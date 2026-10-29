"""
Universal Multi-Vendor Product Lifecycle Intelligence Scraper Package.
Pluggable multi-provider architecture supporting headless crawling and structured AI extraction.
"""

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
]
