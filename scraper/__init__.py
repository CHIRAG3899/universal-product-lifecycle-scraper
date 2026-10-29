"""
Universal Multi-Vendor End of Lifecycle (EOL) AI Scraper Package.
Powered by Crawl4AI and Google Gemini.
"""

from scraper.crawl_engine import MitsubishiAICrawler, UniversalAICrawler
from scraper.gemini_extractor import GeminiExtractor
from scraper.models import ProductRecord, ScrapedDataset, parse_to_utc_iso
from scraper.pipeline import LifecyclePipeline
from scraper.vendors import VENDOR_PROFILES, detect_vendor_from_url_or_text, normalize_stage_name

__all__ = [
    "ProductRecord",
    "ScrapedDataset",
    "parse_to_utc_iso",
    "GeminiExtractor",
    "UniversalAICrawler",
    "MitsubishiAICrawler",
    "LifecyclePipeline",
    "detect_vendor_from_url_or_text",
    "normalize_stage_name",
    "VENDOR_PROFILES"
]
