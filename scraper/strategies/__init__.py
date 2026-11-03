"""
Enterprise Pluggable Scraping Strategy Framework.

Exposes canonical scraping strategies across enterprise lifecycle architectures:
- SearchPortalStrategy: Parameterized queries, family prefix harvesting, CSS row selectors.
- DomTableStrategy: Static and client-rendered HTML table parsing with column mapping.
- SitemapStrategy: XML sitemap and sitemap index traversal with PDP regex filtering.
- RestApiStrategy: Structured JSON/REST API consumption with direct schema validation.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, Optional

from scraper.strategies.base import BaseScrapingStrategy
from scraper.strategies.dom_table import DomTableStrategy
from scraper.strategies.rest_api import RestApiStrategy
from scraper.strategies.search_portal import SearchPortalStrategy
from scraper.strategies.sitemap import SitemapStrategy

logger = logging.getLogger("ai_scraper.strategies")

_STRATEGY_REGISTRY: Dict[str, Callable[[], BaseScrapingStrategy]] = {
    "search_portal": SearchPortalStrategy,
    "lifecycle_search": SearchPortalStrategy,
    "dom_table": DomTableStrategy,
    "html_table": DomTableStrategy,
    "html_filterable_table": DomTableStrategy,
    "filterable_table": DomTableStrategy,
    "html_notice_index": DomTableStrategy,
    "dated_eol_notice_index": DomTableStrategy,
    "notice_index": DomTableStrategy,
    "accordion": DomTableStrategy,
    "dom_accordion": DomTableStrategy,
    "table": DomTableStrategy,
    "sitemap": SitemapStrategy,
    "sitemap_index": SitemapStrategy,
    "rest_api": RestApiStrategy,
    "json_api": RestApiStrategy,
    "api": RestApiStrategy,
}


def get_strategy(strategy_name: Optional[str] = None) -> BaseScrapingStrategy:
    """
    Resolves the appropriate ScrapingStrategy instance based on configured strategy name
    or crawler_type identifier. Defaults to DomTableStrategy if unspecified.
    """
    key = str(strategy_name or "dom_table").strip().lower()
    strategy_cls = _STRATEGY_REGISTRY.get(key, DomTableStrategy)
    return strategy_cls()


__all__ = [
    "BaseScrapingStrategy",
    "SearchPortalStrategy",
    "DomTableStrategy",
    "SitemapStrategy",
    "RestApiStrategy",
    "get_strategy",
]
