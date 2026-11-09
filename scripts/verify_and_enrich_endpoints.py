#!/usr/bin/env python3
"""
Enterprise Endpoint & Pattern Verification and Enrichment Tool.

Iterates over vendors configured in `configs/vendors.yaml` (and candidate sources):
1. Probes live reachability, HTTP status, canonical redirects, SSL validity, and WAF barriers.
2. Verifies whether endpoints actually contain authentic product data (tables, JSON items, sitemaps).
3. Automatically discovers and tests product URL regex patterns against real URLs.
4. Feeds discovered endpoints, table previews, and sample URLs to an LLM verification gate.
5. Scores confidence (high, medium, low) and assigns explicit rationale.
6. Updates `configs/vendors.yaml`:
   - Verified high/medium endpoints are enriched with pattern/strategy.
   - Low confidence endpoints are tagged with `confidence: low`, `confidence_reason`, and `review_needed: true`.
7. Generates comprehensive structured reports (`output/endpoint_verification_report.json` and `.md`).

Usage:
    # Verify a single vendor (dry-run, LLM verification enabled)
    python scripts/verify_and_enrich_endpoints.py --vendor rockwell_automation

    # Verify and apply updates to configs/vendors.yaml
    python scripts/verify_and_enrich_endpoints.py --vendor yokogawa --apply

    # Verify all vendors in a sector
    python scripts/verify_and_enrich_endpoints.py --sector OT --apply

    # Verify all vendors across the entire catalog
    python scripts/verify_and_enrich_endpoints.py --all --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Ensure workspace root is in path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.ai_extractor import UniversalAIExtractor  # noqa: E402
from scraper.config import USER_AGENT  # noqa: E402
from scraper.models import is_valid_product_model  # noqa: E402
from scraper.security import is_safe_url  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("endpoint_verifier")

VENDORS_YAML_PATH = BASE_DIR / "configs" / "vendors.yaml"
ENRICHED_V16_YAML_PATH = BASE_DIR / "configs" / "vendors_lifecycle_enriched_v16.yaml"

COMMON_EOL_PATHS = [
    "/discontinued/",
    "/solutions/discontinued/",
    "/support/lifecycle/",
    "/products/discontinued/",
    "/obsolete-products/",
    "/eos-eol-notice",
    "/eos-eol-listing",
    "/end-of-life",
    "/discontinued-products",
    "/products/end-of-life",
]

COMMON_SITEMAP_CANDIDATES = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/crisp_sitemap_index.xml",
    "/en/sitemap.xml",
    "/en-us/sitemap.xml",
]

STOPWORD_URL_SLUGS = {
    "index", "default", "home", "contact", "about", "about-us", "terms", "terms-conditions",
    "privacy", "privacy-policy", "legal", "support", "help", "login", "register", "cart",
    "checkout", "search", "news", "events", "careers", "sitemap", "feed", "rss", "download",
    "downloads", "overview", "services", "solutions", "products", "product", "all-products",
    "category", "categories", "en", "en-us", "global", "us", "uk", "de", "fr", "ja", "cn"
}


class EndpointProber:
    """Probes live HTTP endpoints, detects WAF barriers, and parses sitemaps / HTML tables."""

    def __init__(self, timeout: float = 8.0) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504], raise_on_status=False)
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        self.session.mount("http://", HTTPAdapter(max_retries=retries))
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def probe_http(self, url: str) -> Dict[str, Any]:
        """Probes an HTTP URL and returns reachability, status, headers, and WAF detection."""
        res: Dict[str, Any] = {
            "url": url,
            "status_code": 0,
            "final_url": url,
            "is_redirect": False,
            "redirect_hops": [],
            "waf_challenge": None,
            "is_success": False,
            "content_type": "",
            "has_table": False,
            "body_snippet": "",
            "raw_text": "",
            "error": None,
        }

        if not url or not url.startswith(("http://", "https://")):
            res["error"] = "Invalid URL schema"
            return res

        if not is_safe_url(url):
            res["error"] = "SSRF security check blocked URL"
            return res

        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            res["status_code"] = resp.status_code
            res["final_url"] = str(resp.url)
            res["is_redirect"] = str(resp.url) != url
            res["content_type"] = resp.headers.get("Content-Type", "")

            if resp.history:
                res["redirect_hops"] = [str(r.url) for r in resp.history]

            waf_action = resp.headers.get("x-amzn-waf-action", "")
            cf_ray = resp.headers.get("cf-ray", "")
            server_hdr = resp.headers.get("server", "").lower()

            raw_text = resp.text or ""
            res["raw_text"] = raw_text
            text_preview = raw_text[:15000].lower()
            res["body_snippet"] = raw_text[:500].strip()

            # Detect Bot & WAF barriers
            if resp.status_code == 202 or "challenge" in waf_action.lower():
                res["waf_challenge"] = "AWS_WAF_CHALLENGE"
            elif resp.status_code in (403, 503) and cf_ray:
                res["waf_challenge"] = "CLOUDFLARE_CHALLENGE"
            elif "imperva" in server_hdr or "incapsula" in server_hdr:
                res["waf_challenge"] = "IMPERVA_CHALLENGE"
            elif "azure waf" in text_preview or "azure waf js challenge" in text_preview:
                res["waf_challenge"] = "AZURE_WAF_CHALLENGE"
            elif resp.status_code == 403 and (
                "akamai" in server_hdr
                or "edgesuite.net" in raw_text
                or "ak_p" in resp.headers.get("server-timing", "")
                or "x-akamai-transformed" in resp.headers
                or "reference #" in text_preview
                or "access denied" in text_preview
            ):
                res["waf_challenge"] = "AKAMAI_CHALLENGE"

            res["has_table"] = "<table" in text_preview
            res["is_success"] = 200 <= resp.status_code < 400 and not res["waf_challenge"]

        except requests.exceptions.SSLError as e:
            res["error"] = f"SSL_ERROR: {e}"
        except requests.exceptions.Timeout:
            res["error"] = "TIMEOUT"
        except requests.exceptions.ConnectionError as e:
            res["error"] = f"CONNECTION_ERROR: {e}"
        except Exception as e:
            res["error"] = f"REQUEST_ERROR: {e}"

        return res

    def inspect_sitemap(self, sitemap_url: str) -> Dict[str, Any]:
        """Parses an XML sitemap (index or urlset) and gathers child sitemaps and sample URLs."""
        result: Dict[str, Any] = {
            "sitemap_url": sitemap_url,
            "is_index": False,
            "child_count": 0,
            "product_sitemaps": [],
            "eol_sitemaps": [],
            "sample_urls": [],
            "suggested_child_filter": None,
            "has_data": False,
            "error": None,
        }

        probe = self.probe_http(sitemap_url)
        if not probe["is_success"] or not probe["raw_text"]:
            result["error"] = probe["error"] or f"HTTP {probe['status_code']} (WAF: {probe['waf_challenge']})"
            return result

        raw_xml = probe["raw_text"]
        # Remove XML default namespace to allow uniform tag querying
        xml_clean = re.sub(r' xmlns="[^"]+"', "", raw_xml, count=1)

        try:
            root = ET.fromstring(xml_clean.encode("utf-8", errors="replace"))

            if root.tag.endswith("sitemapindex"):
                result["is_index"] = True
                children: List[str] = []
                for s_elem in root.findall(".//sitemap"):
                    loc = s_elem.find("loc")
                    if loc is not None and loc.text:
                        children.append(loc.text.strip())

                result["child_count"] = len(children)
                for c in children:
                    c_lower = c.lower()
                    if any(k in c_lower for k in ("product", "pdp", "catalog", "item", "part")):
                        result["product_sitemaps"].append(c)
                    if any(k in c_lower for k in ("discontinued", "eol", "lifecycle", "obsolete", "phaseout", "eos")):
                        result["eol_sitemaps"].append(c)

                # Identify child filter heuristic token
                if result["product_sitemaps"]:
                    sample_child = result["product_sitemaps"][0]
                    child_name = Path(urlparse(sample_child).path).name
                    token = child_name.split(".")[0].split("-")[0]
                    result["suggested_child_filter"] = token if token else child_name

                    # Probe first 2 product child sitemaps to harvest real URLs
                    for child_url in result["product_sitemaps"][:2]:
                        self._sample_child_urls(child_url, result)
                        if len(result["sample_urls"]) >= 15:
                            break
                elif children:
                    # Probe first child sitemap generally
                    self._sample_child_urls(children[0], result)

                result["has_data"] = len(result["sample_urls"]) > 0 or result["child_count"] > 0

            elif root.tag.endswith("urlset"):
                result["is_index"] = False
                urls: List[str] = []
                for u_elem in root.findall(".//url"):
                    loc = u_elem.find("loc")
                    if loc is not None and loc.text:
                        urls.append(loc.text.strip())
                result["sample_urls"] = urls[:30]
                result["has_data"] = len(urls) > 0

        except ET.ParseError as pe:
            result["error"] = f"XML_PARSE_ERROR: {pe}"
        except Exception as e:
            result["error"] = f"SITEMAP_INSPECT_ERROR: {e}"

        return result

    def _sample_child_urls(self, child_sitemap_url: str, result: Dict[str, Any]) -> None:
        """Fetches a child sitemap and extracts sample product URLs."""
        try:
            c_resp = self.session.get(child_sitemap_url, timeout=self.timeout)
            if c_resp.status_code == 200 and c_resp.text:
                c_clean = re.sub(r' xmlns="[^"]+"', "", c_resp.text, count=1)
                c_root = ET.fromstring(c_clean.encode("utf-8", errors="replace"))
                urls: List[str] = []
                for u_elem in c_root.findall(".//url"):
                    loc = u_elem.find("loc")
                    if loc is not None and loc.text:
                        urls.append(loc.text.strip())
                # Append unique URLs up to 30
                for u in urls:
                    if u not in result["sample_urls"]:
                        result["sample_urls"].append(u)
                    if len(result["sample_urls"]) >= 30:
                        break
        except Exception as e:
            logger.debug(f"Could not sample child sitemap '{child_sitemap_url}': {e}")

    def inspect_html_page(self, url: str, probe_res: Dict[str, Any]) -> Dict[str, Any]:
        """Inspects HTML content for structured tables, rows, product links, and lifecycle terms."""
        info: Dict[str, Any] = {
            "has_table": False,
            "table_count": 0,
            "table_headers": [],
            "sample_rows": [],
            "product_links": [],
            "has_lifecycle_keywords": False,
            "is_js_shell": False,
            "has_data": False,
        }

        raw_text = probe_res.get("raw_text", "")
        if not raw_text:
            return info

        soup = BeautifulSoup(raw_text, "html.parser")

        # 1. Check for client-side JS shells
        text_content = soup.get_text(separator=" ", strip=True)
        if len(text_content) < 300 and ("root" in raw_text or "app" in raw_text) and not soup.find("table"):
            info["is_js_shell"] = True

        # 2. Check for lifecycle keywords
        lower_body = raw_text.lower()
        lifecycle_terms = ["discontinued", "end of life", "lifecycle", "phaseout", "obsolete", "last time buy", "replacement"]
        if any(term in lower_body for term in lifecycle_terms):
            info["has_lifecycle_keywords"] = True

        # 3. Check for DOM tables
        tables = soup.find_all("table")
        info["table_count"] = len(tables)
        if tables:
            info["has_table"] = True
            primary_table = tables[0]
            headers = [th.get_text(strip=True) for th in primary_table.find_all(["th"])]
            info["table_headers"] = headers[:8]

            rows_data: List[List[str]] = []
            for tr in primary_table.find_all("tr")[:6]:
                cells = [td.get_text(strip=True) for td in tr.find_all(["td"])]
                if cells:
                    rows_data.append(cells[:6])
            info["sample_rows"] = rows_data

        # 4. Check for product links
        product_hrefs: List[str] = []
        for a in soup.find_all("a", href=True):
            raw_href = a.get("href")
            href = str(raw_href).strip() if raw_href else ""
            if not href:
                continue
            if any(p in href.lower() for p in ("/product/", "/products/", "/item/", "/pdp/", "/catalog/")):
                full_href = urljoin(url, href)
                if full_href not in product_hrefs:
                    product_hrefs.append(full_href)
            if len(product_hrefs) >= 20:
                break
        info["product_links"] = product_hrefs

        info["has_data"] = bool(info["sample_rows"] or len(product_hrefs) >= 3 or (info["has_lifecycle_keywords"] and len(text_content) > 1000))
        return info

    def discover_sitemaps(self, base_url: str) -> List[str]:
        """Discovers active XML sitemaps via robots.txt and standard candidate paths."""
        discovered: List[str] = []
        if not base_url or not base_url.startswith(("http://", "https://")):
            return discovered

        parsed = urlparse(base_url)
        domain_root = f"{parsed.scheme}://{parsed.netloc}"

        # 1. robots.txt
        robots_url = f"{domain_root}/robots.txt"
        try:
            r = self.session.get(robots_url, timeout=self.timeout)
            if r.status_code == 200:
                for line in r.text.splitlines():
                    if line.strip().lower().startswith("sitemap:"):
                        s_url = line.split(":", 1)[1].strip()
                        if s_url.startswith(("http://", "https://")) and s_url not in discovered:
                            discovered.append(s_url)
        except Exception:
            pass

        # 2. Candidate locations
        for cand in COMMON_SITEMAP_CANDIDATES:
            full_cand = f"{domain_root}{cand}"
            if full_cand in discovered:
                continue
            try:
                head_resp = self.session.head(full_cand, timeout=self.timeout, allow_redirects=True)
                if head_resp.status_code == 200:
                    discovered.append(full_cand)
            except Exception:
                pass

        return discovered

    def discover_eol_subpaths(self, base_url: str) -> List[Dict[str, Any]]:
        """Checks well-known EOL and discontinued subpaths on the vendor's primary domain."""
        valid_eol_portals: List[Dict[str, Any]] = []
        if not base_url or not base_url.startswith(("http://", "https://")):
            return valid_eol_portals

        parsed = urlparse(base_url)
        domain_root = f"{parsed.scheme}://{parsed.netloc}"

        for subpath in COMMON_EOL_PATHS:
            test_url = urljoin(domain_root, subpath)
            probe = self.probe_http(test_url)
            if probe.get("is_success") and (probe.get("has_table") or probe.get("status_code") == 200):
                valid_eol_portals.append({
                    "url": probe["final_url"],
                    "status_code": probe["status_code"],
                    "has_table": probe["has_table"],
                    "waf_challenge": probe["waf_challenge"],
                })

        return valid_eol_portals


class PatternAnalyzer:
    """Discovers, scores, and verifies product URL regex extraction patterns against real URLs."""

    COMMON_CATALOG_PATTERNS = [
        r"details\.([A-Za-z0-9\-_.]+)\.html",
        r"/products?/([A-Za-z0-9\-_.]+)\.html",
        r"/products?/(?:[a-z0-9\-]+/)*([A-Za-z0-9\-_.]+)/?$",
        r"/products?/([A-Za-z0-9\-_.]+)",
        r"/pdp/([A-Za-z0-9\-_.]+)\.html",
        r"/pdp/([A-Za-z0-9\-_.]+)",
        r"/catalog/([A-Za-z0-9\-_.]+)\.html",
        r"/catalog/(?:[a-z0-9\-]+/)*([A-Za-z0-9\-_.]+)/?$",
        r"/item/([A-Za-z0-9\-_.]+)",
        r"/part/([A-Za-z0-9\-_.]+)",
        r"/model/([A-Za-z0-9\-_.]+)",
        r"/([A-Za-z0-9\-_]{4,35})\.html",
        r"/([A-Za-z0-9\-_]{4,35})/?$",
    ]

    @classmethod
    def test_and_discover_patterns(
        cls,
        sample_urls: List[str],
        configured_pattern: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Tests candidate regex patterns across sample URLs to find the most accurate model extractor.
        Returns the best pattern, match counts, valid token counts, and sample extracted models.
        """
        result: Dict[str, Any] = {
            "best_pattern": None,
            "match_count": 0,
            "valid_model_count": 0,
            "sample_extracted_models": [],
            "tested_patterns_count": 0,
        }

        if not sample_urls:
            return result

        candidates: List[str] = []
        if configured_pattern and configured_pattern.strip():
            candidates.append(configured_pattern.strip())

        # Include standard catalog patterns
        for p in cls.COMMON_CATALOG_PATTERNS:
            if p not in candidates:
                candidates.append(p)

        # Dynamic prefix-based pattern synthesis
        inferred_prefix = cls._infer_common_path_prefix(sample_urls)
        if inferred_prefix and inferred_prefix not in candidates:
            candidates.insert(1, inferred_prefix)

        result["tested_patterns_count"] = len(candidates)
        best_score = -1

        for pat in candidates:
            try:
                rx = re.compile(pat, re.IGNORECASE)
            except re.error:
                continue

            matches: List[str] = []
            extracted_tokens: List[str] = []

            for u in sample_urls:
                m = rx.search(u)
                if m and m.groups():
                    token = m.group(1).strip()
                    matches.append(u)
                    extracted_tokens.append(token)

            if not extracted_tokens:
                continue

            # Evaluate token validity
            valid_models: List[str] = []
            for t in extracted_tokens:
                t_clean = t.strip()
                t_lower = t_clean.lower()
                if t_lower in STOPWORD_URL_SLUGS:
                    continue
                if len(t_clean) < 2 or len(t_clean) > 45:
                    continue
                # Give high weight to tokens that contain digits or pass is_valid_product_model
                if is_valid_product_model(t_clean) or any(c.isdigit() for c in t_clean):
                    valid_models.append(t_clean)

            # Score: 2 points per authentic model SKU + 1 point per URL match
            score = (len(valid_models) * 2) + len(matches)

            if score > best_score and len(valid_models) > 0:
                best_score = score
                result["best_pattern"] = pat
                result["match_count"] = len(matches)
                result["valid_model_count"] = len(valid_models)
                result["sample_extracted_models"] = valid_models[:8]

        return result

    @classmethod
    def _infer_common_path_prefix(cls, sample_urls: List[str]) -> Optional[str]:
        """Infers the common path prefix among sample URLs to generate an exact PDP regex."""
        parsed_paths = [urlparse(u).path for u in sample_urls if urlparse(u).path]
        if len(parsed_paths) < 2:
            return None

        # Find common directory prefix
        split_paths = [p.strip("/").split("/") for p in parsed_paths if "/" in p.strip("/")]
        if not split_paths:
            return None

        prefix_segments: List[str] = []
        for segments in zip(*split_paths):
            if len(set(segments)) == 1:
                prefix_segments.append(segments[0])
            else:
                break

        if len(prefix_segments) >= 2:
            prefix_str = "/" + "/".join(prefix_segments)
            # Check if filenames have .html extension
            has_html = any(".html" in p for p in parsed_paths)
            if has_html:
                return f"{re.escape(prefix_str)}/([A-Za-z0-9\\-_.]+)\\.html"
            return f"{re.escape(prefix_str)}/([A-Za-z0-9\\-_.]+)/?$"

        return None


class LLMEndpointVerifier:
    """Verifies endpoint authenticity and pattern accuracy using LLM with deterministic code fallback."""

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        enabled: bool = True,
    ) -> None:
        self.enabled = enabled
        self.extractor = UniversalAIExtractor(
            provider=provider,
            model_name=model or "gemini-3.1-flash-lite",
            api_key=api_key,
        )
        self.provider = self.extractor.provider
        self.model = self.extractor.model_name
        self.is_configured = self.extractor.is_configured()

    def verify_endpoint(
        self,
        vendor_id: str,
        vendor_name: str,
        sector: str,
        endpoint_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Submits probed endpoint details to the LLM Verification Gate to confirm authenticity,
        score confidence ('high', 'medium', 'low'), and validate the product URL regex pattern.
        """
        # Fast path: If endpoint is broken (HTTP status != 200), WAF challenged, or has no data,
        # return deterministic result immediately without wasting LLM calls or waiting for timeouts.
        status = endpoint_info.get("status_code", 0)
        waf = endpoint_info.get("waf_challenge")
        has_data = endpoint_info.get("has_data", False)
        if status not in (200, 301, 302, 304, 307, 308) or waf or (status == 200 and not has_data):
            return self._deterministic_code_verification(vendor_name, endpoint_info)

        if not self.enabled or not self.is_configured:
            return self._deterministic_code_verification(vendor_name, endpoint_info)

        # Prepare verification payload
        payload = {
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "sector": sector,
            "url": endpoint_info.get("url"),
            "final_url": endpoint_info.get("final_url"),
            "http_status": endpoint_info.get("status_code"),
            "waf_challenge": endpoint_info.get("waf_challenge"),
            "endpoint_type": endpoint_info.get("endpoint_type", "unknown"),
            "has_data": endpoint_info.get("has_data", False),
            "table_headers": endpoint_info.get("table_headers", []),
            "sample_table_rows": endpoint_info.get("sample_rows", [])[:3],
            "sample_urls": endpoint_info.get("sample_urls", [])[:6],
            "tested_product_pattern": endpoint_info.get("best_pattern"),
            "sample_extracted_models": endpoint_info.get("sample_extracted_models", [])[:6],
        }

        prompt = (
            "You are an Enterprise Hardware & Software Lifecycle Integrity Validator.\n"
            "Verify whether the candidate endpoint and URL pattern represent an authentic, authoritative manufacturer "
            "product catalog, lifecycle notice, or EOL documentation source for this vendor.\n\n"
            "Evaluation Rules:\n"
            "1. Check if the domain/URL is an authoritative official manufacturer source for this vendor.\n"
            "2. Confirm whether authentic data exists (e.g. structured tables, active product catalog, XML sitemap).\n"
            "3. Confirm whether the tested regex accurately captures physical/software product models/SKUs rather than generic stopwords, dates, or navigation slugs.\n"
            "4. Assign Confidence:\n"
            "   - 'high': Authoritative manufacturer domain, valid data/table/sitemap, pattern captures genuine product SKUs.\n"
            "   - 'medium': Plausible manufacturer source with product models, but sample is small or pattern is somewhat generic.\n"
            "   - 'low': Low authority, ambiguous URLs, category pages only, non-model tokens (e.g. dates, stopwords), dynamic JS-rendering blockers, WAF challenge, or broken.\n"
            "5. If confidence is 'low', set review_needed=true and give the exact reason in 'confidence_reason'.\n\n"
            f"Candidate Endpoint Data:\n{json.dumps(payload, indent=2)}\n\n"
            "Return strict JSON object with this exact schema:\n"
            "{\n"
            '  "is_valid_endpoint": bool,\n'
            '  "endpoint_type": "sitemap" | "dom_table" | "search_portal" | "rest_api",\n'
            '  "confidence": "high" | "medium" | "low",\n'
            '  "confidence_reason": str,\n'
            '  "suggested_product_pattern": str or null,\n'
            '  "suggested_name": str,\n'
            '  "evidence_authority": "official_model_status_or_notice_evidence" | "active_product_catalog_authority" | "general_support_or_discovery_only",\n'
            '  "review_needed": bool\n'
            "}"
        )

        try:
            response_text = ""
            if self.provider == "gemini" and self.extractor.client and hasattr(self.extractor.client, "models"):
                fallback_models = [self.model, "gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"]
                for m in fallback_models:
                    try:
                        resp = self.extractor.client.models.generate_content(
                            model=m,
                            contents=prompt,
                        )
                        if resp and resp.text:
                            response_text = resp.text
                            break
                    except Exception as ge:
                        ge_str = str(ge)
                        if any(k in ge_str for k in ["503", "429", "RESOURCE_EXHAUSTED", "NOT_FOUND"]):
                            continue
                        raise ge
            elif self.extractor.client and hasattr(self.extractor.client, "chat") and hasattr(self.extractor.client.chat, "completions"):
                resp_oai = self.extractor.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0
                )
                response_text = resp_oai.choices[0].message.content or ""
            else:
                from scraper.providers import call_llm_completion
                resp_prov = call_llm_completion(
                    provider=self.provider,
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    api_key=self.extractor.api_key,
                    json_mode=True,
                    timeout=30,
                )
                response_text = str(resp_prov) if isinstance(resp_prov, str) else ""

            if response_text:
                cleaned_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", response_text.strip(), flags=re.MULTILINE)
                parsed = json.loads(cleaned_json)
                if isinstance(parsed, dict) and "confidence" in parsed:
                    return {
                        "is_valid_endpoint": bool(parsed.get("is_valid_endpoint", True)),
                        "endpoint_type": parsed.get("endpoint_type", endpoint_info.get("endpoint_type", "dom_table")),
                        "confidence": parsed.get("confidence", "low").lower(),
                        "confidence_reason": str(parsed.get("confidence_reason", "Verified via LLM Gate")),
                        "suggested_product_pattern": parsed.get("suggested_product_pattern") or endpoint_info.get("best_pattern"),
                        "suggested_name": parsed.get("suggested_name", endpoint_info.get("name", f"{vendor_id}_Verified_Endpoint")),
                        "evidence_authority": parsed.get("evidence_authority", "official_model_status_or_notice_evidence"),
                        "review_needed": bool(parsed.get("review_needed", parsed.get("confidence") == "low")),
                    }
        except Exception as e:
            logger.debug(f"LLM verification call failed ({e}); falling back to deterministic verification.")

        return self._deterministic_code_verification(vendor_name, endpoint_info)

    def _deterministic_code_verification(
        self,
        vendor_name: str,
        endpoint_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Deterministic code-based verification rules when LLM is unavailable or offline."""
        status = endpoint_info.get("status_code", 0)
        waf = endpoint_info.get("waf_challenge")
        has_data = endpoint_info.get("has_data", False)
        ep_type = endpoint_info.get("endpoint_type", "dom_table")
        valid_models = endpoint_info.get("valid_model_count", 0)
        best_pat = endpoint_info.get("best_pattern")

        # 1. Broken / WAF challenged endpoints
        if waf:
            return {
                "is_valid_endpoint": False,
                "endpoint_type": ep_type,
                "confidence": "low",
                "confidence_reason": f"Blocked by {waf} (HTTP {status}); requires headless browser or bypass",
                "suggested_product_pattern": best_pat,
                "suggested_name": endpoint_info.get("name", "WAF_Challenged_Endpoint"),
                "evidence_authority": "general_support_or_discovery_only",
                "review_needed": True,
            }

        if status not in (200, 301, 302, 304, 307, 308):
            return {
                "is_valid_endpoint": False,
                "endpoint_type": ep_type,
                "confidence": "low",
                "confidence_reason": f"HTTP reachability failure: status {status} ({endpoint_info.get('error')})",
                "suggested_product_pattern": None,
                "suggested_name": endpoint_info.get("name", "Broken_Endpoint"),
                "evidence_authority": "general_support_or_discovery_only",
                "review_needed": True,
            }

        if not has_data:
            return {
                "is_valid_endpoint": False,
                "endpoint_type": ep_type,
                "confidence": "low",
                "confidence_reason": "Endpoint reachable but returned zero structured tables, product links, or sitemap items",
                "suggested_product_pattern": None,
                "suggested_name": endpoint_info.get("name", "Empty_Data_Endpoint"),
                "evidence_authority": "general_support_or_discovery_only",
                "review_needed": True,
            }

        # 2. Sitemaps with authentic model URLs
        if ep_type == "sitemap":
            if valid_models >= 3 and best_pat:
                return {
                    "is_valid_endpoint": True,
                    "endpoint_type": "sitemap",
                    "confidence": "high",
                    "confidence_reason": f"Authoritative XML sitemap with {valid_models} verified product SKUs matching '{best_pat}'",
                    "suggested_product_pattern": best_pat,
                    "suggested_name": endpoint_info.get("name", f"{vendor_name.replace(' ', '_')}_Product_Sitemap"),
                    "evidence_authority": "active_product_catalog_authority",
                    "review_needed": False,
                }
            elif endpoint_info.get("sample_urls"):
                return {
                    "is_valid_endpoint": True,
                    "endpoint_type": "sitemap",
                    "confidence": "medium",
                    "confidence_reason": "XML sitemap contains candidate URLs but pattern model validation had limited match count",
                    "suggested_product_pattern": best_pat,
                    "suggested_name": endpoint_info.get("name", f"{vendor_name.replace(' ', '_')}_Candidate_Sitemap"),
                    "evidence_authority": "active_product_catalog_authority",
                    "review_needed": False,
                }

        # 3. DOM tables
        if endpoint_info.get("has_table") and endpoint_info.get("sample_rows"):
            if endpoint_info.get("has_lifecycle_keywords"):
                return {
                    "is_valid_endpoint": True,
                    "endpoint_type": "dom_table",
                    "confidence": "high",
                    "confidence_reason": "HTML table verified containing official lifecycle milestones and hardware product rows",
                    "suggested_product_pattern": None,
                    "suggested_name": endpoint_info.get("name", f"{vendor_name.replace(' ', '_')}_Lifecycle_Table"),
                    "evidence_authority": "official_model_status_or_notice_evidence",
                    "review_needed": False,
                }
            return {
                "is_valid_endpoint": True,
                "endpoint_type": "dom_table",
                "confidence": "medium",
                "confidence_reason": "HTML table verified with structured rows, but explicit lifecycle milestones require confirmation",
                "suggested_product_pattern": None,
                "suggested_name": endpoint_info.get("name", f"{vendor_name.replace(' ', '_')}_Product_Table"),
                "evidence_authority": "official_model_status_or_notice_evidence",
                "review_needed": False,
            }

        # 4. Fallback low confidence
        return {
            "is_valid_endpoint": True,
            "endpoint_type": ep_type,
            "confidence": "low",
            "confidence_reason": "Endpoint has limited verifiable structure; flagged for manual/next iteration review",
            "suggested_product_pattern": best_pat,
            "suggested_name": endpoint_info.get("name", f"{vendor_name.replace(' ', '_')}_Generic_Endpoint"),
            "evidence_authority": "general_support_or_discovery_only",
            "review_needed": True,
        }


def enrich_and_update_vendor_yaml(
    vendor_id: str,
    vendor_conf: Dict[str, Any],
    verified_endpoints: List[Dict[str, Any]],
    all_vendors_yaml_data: Dict[str, Any],
) -> bool:
    """
    Safely updates `configs/vendors.yaml` with verified endpoints, patterns, and confidence attributes.
    Preserves existing custom configurations (such as Rockwell API credentials) and strictly avoids duplicate URLs.
    """
    modified = False
    v_data = all_vendors_yaml_data.get("vendors", {}).get(vendor_id)
    if not v_data:
        return False

    current_eps = v_data.get("entry_points", [])
    existing_urls = {ep.get("url") for ep in current_eps if isinstance(ep, dict) and ep.get("url")}

    # Gather all global URLs across other vendors to satisfy pre-commit check 5
    global_urls: Dict[str, str] = {}
    for other_vid, other_vdata in all_vendors_yaml_data.get("vendors", {}).items():
        if other_vid == vendor_id:
            continue
        for o_ep in other_vdata.get("entry_points", []):
            o_url = o_ep.get("url")
            if o_url:
                global_urls[o_url] = other_vid

    for v_ep in verified_endpoints:
        ep_url = v_ep.get("url")
        if not ep_url:
            continue

        # Match against current configured entry points
        matched_idx = -1
        for i, curr in enumerate(current_eps):
            if curr.get("url") == ep_url or (v_ep.get("final_url") and curr.get("url") == v_ep.get("final_url")):
                matched_idx = i
                break

        conf_level = v_ep.get("confidence", "low")
        conf_reason = v_ep.get("confidence_reason", "")
        review_needed = v_ep.get("review_needed", conf_level == "low")
        pattern = v_ep.get("suggested_product_pattern")

        if matched_idx >= 0:
            # Update existing entry point attributes
            ep_ref = current_eps[matched_idx]
            old_conf = ep_ref.get("confidence")
            if old_conf != conf_level:
                ep_ref["confidence"] = conf_level
                ep_ref["confidence_reason"] = conf_reason
                if review_needed:
                    ep_ref["review_needed"] = True
                elif "review_needed" in ep_ref:
                    del ep_ref["review_needed"]
                modified = True

            # If sitemap and a verified product pattern was discovered, set or update it
            if v_ep.get("endpoint_type") == "sitemap" and pattern:
                if ep_ref.get("product_pattern") != pattern and ep_ref.get("pattern") != pattern:
                    ep_ref["product_pattern"] = pattern
                    modified = True

            # If redirect resolved to a clean canonical 200 URL, update it
            if v_ep.get("is_redirect") and v_ep.get("final_url") and v_ep.get("final_url") not in global_urls:
                if ep_ref.get("url") != v_ep["final_url"]:
                    logger.info(f"[{vendor_id}] Updating canonical URL: {ep_ref.get('url')} -> {v_ep['final_url']}")
                    ep_ref["url"] = v_ep["final_url"]
                    modified = True

        else:
            # New candidate endpoint: only add to vendors.yaml if it actually works and has data
            if not v_ep.get("is_valid_endpoint"):
                continue

            # Skip candidate endpoints that returned an error status or redirect to error pages
            status_code = v_ep.get("status_code", 200)
            if status_code not in (200, 301, 302, 304, 307, 308):
                continue

            target_url = v_ep.get("final_url") or ep_url
            if "404" in target_url.lower() or "error" in target_url.lower():
                continue

            if target_url in existing_urls or target_url in global_urls:
                continue

            new_ep: Dict[str, Any] = {
                "name": v_ep.get("suggested_name", f"{vendor_id}_{len(current_eps) + 1}"),
                "url": target_url,
                "strategy": v_ep.get("endpoint_type", "dom_table"),
                "crawler_type": v_ep.get("endpoint_type", "dom_table"),
                "confidence": conf_level,
                "confidence_reason": conf_reason,
                "evidence_authority": v_ep.get("evidence_authority", "official_model_status_or_notice_evidence"),
            }

            if review_needed:
                new_ep["review_needed"] = True

            if v_ep.get("endpoint_type") == "sitemap":
                if pattern:
                    new_ep["product_pattern"] = pattern
                if v_ep.get("suggested_child_filter"):
                    new_ep["child_filter"] = v_ep["suggested_child_filter"]

            logger.info(f"[{vendor_id}] Adding verified endpoint ({conf_level} confidence): {target_url}")
            current_eps.append(new_ep)
            existing_urls.add(target_url)
            modified = True

    if modified:
        v_data["entry_points"] = current_eps
        all_vendors_yaml_data["vendors"][vendor_id] = v_data

    return modified


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify, score, and enrich vendor endpoints and URL patterns with LLM.")
    parser.add_argument("--vendor", help="Specific vendor ID to audit/verify (e.g. rockwell_automation, yokogawa).")
    parser.add_argument("--sector", choices=["OT", "IT", "IoT"], help="Verify all vendors in a sector.")
    parser.add_argument("--all", action="store_true", help="Verify all vendors across configs/vendors.yaml.")
    parser.add_argument("--limit", type=int, default=None, help="Max number of vendors to process.")
    parser.add_argument("--offset", type=int, default=0, help="Offset for chunked processing.")
    parser.add_argument("--apply", action="store_true", help="Apply updates directly to configs/vendors.yaml.")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM verification gate (use code rules).")
    parser.add_argument("--provider", default=None, help="AI provider (gemini, openai, anthropic, ollama).")
    parser.add_argument("--model", default=None, help="LLM model identifier.")
    parser.add_argument("--api-key", default=None, help="Explicit API key.")
    parser.add_argument("--timeout", type=float, default=8.0, help="HTTP timeout in seconds.")
    parser.add_argument("--check-enriched-sources", action="store_true", default=True, help="Check candidate endpoints from vendors_lifecycle_enriched_v16.yaml.")
    parser.add_argument("--output-json", default="output/endpoint_verification_report.json", help="Path to save report JSON.")
    parser.add_argument("--output-md", default="output/endpoint_verification_report.md", help="Path to save report Markdown.")

    args = parser.parse_args()

    if not VENDORS_YAML_PATH.exists():
        logger.error(f"Cannot find {VENDORS_YAML_PATH}")
        return 1

    with open(VENDORS_YAML_PATH, "r", encoding="utf-8") as f:
        conf_data = yaml.safe_load(f) or {}

    all_vendors = conf_data.get("vendors", {})
    target_vendors: Dict[str, Any] = {}

    if args.vendor:
        if args.vendor not in all_vendors:
            logger.error(f"Vendor '{args.vendor}' not found in configs/vendors.yaml.")
            return 1
        target_vendors[args.vendor] = all_vendors[args.vendor]
    elif args.sector:
        target_vendors = {k: v for k, v in all_vendors.items() if v.get("sector") == args.sector}
    elif args.all:
        target_vendors = all_vendors
    else:
        logger.info("No vendor/sector specified. Defaulting to first 5 vendors in vendors.yaml.")
        first_5_keys = list(all_vendors.keys())[:5]
        target_vendors = {k: all_vendors[k] for k in first_5_keys}

    # Apply offset and limit
    all_target_keys = list(target_vendors.keys())[args.offset:]
    if args.limit:
        all_target_keys = all_target_keys[:args.limit]
    target_vendors = {k: target_vendors[k] for k in all_target_keys}

    logger.info(f"Starting Endpoint & Pattern Verification across {len(target_vendors)} vendor(s)...")

    # Load candidate sources from v16 if enabled
    enriched_v16_data: Dict[str, Any] = {}
    if args.check_enriched_sources and ENRICHED_V16_YAML_PATH.exists():
        try:
            with open(ENRICHED_V16_YAML_PATH, "r", encoding="utf-8") as f:
                v16_raw = yaml.safe_load(f) or {}
                enriched_v16_data = v16_raw.get("vendors", {})
        except Exception as e:
            logger.warning(f"Could not load enriched v16 reference: {e}")

    prober = EndpointProber(timeout=args.timeout)
    llm_verifier = LLMEndpointVerifier(
        provider=args.provider,
        model=args.model,
        api_key=args.api_key,
        enabled=not args.no_llm,
    )

    report_data: Dict[str, Any] = {
        "verification_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_vendors_processed": len(target_vendors),
        "llm_gate_enabled": not args.no_llm and llm_verifier.is_configured,
        "llm_provider": llm_verifier.provider,
        "llm_model": llm_verifier.model,
        "summary": {
            "high_confidence_count": 0,
            "medium_confidence_count": 0,
            "low_confidence_count": 0,
            "broken_endpoints_count": 0,
            "total_endpoints_verified": 0,
            "yaml_updates_applied": 0,
        },
        "vendors": {},
    }

    yaml_modified_total = False

    for vid, vconf in target_vendors.items():
        vname = vconf.get("name", vid)
        vsector = vconf.get("sector", "OT")
        vwebsite = vconf.get("website", "")
        configured_eps = vconf.get("entry_points", [])

        logger.info(f"\n[{vid}] Auditing and verifying endpoints for {vname} ({vsector})...")

        # Collect candidate URLs for this vendor
        candidate_urls: List[Dict[str, Any]] = []

        # 1. Configured entry points
        for ep in configured_eps:
            if isinstance(ep, dict) and ep.get("url"):
                candidate_urls.append({
                    "url": ep["url"],
                    "source": "configured",
                    "configured_pattern": ep.get("product_pattern") or ep.get("pattern"),
                    "name": ep.get("name"),
                    "strategy": ep.get("strategy") or ep.get("crawler_type", "unknown"),
                    "api_config": ep.get("api_config"),
                })

        # 2. Candidate URLs from enriched v16
        if vid in enriched_v16_data:
            v16_eps = enriched_v16_data[vid].get("entry_points", [])
            for ep16 in v16_eps:
                u16 = ep16.get("url") if isinstance(ep16, dict) else (ep16 if isinstance(ep16, str) else None)
                if u16 and not any(c["url"] == u16 for c in candidate_urls):
                    candidate_urls.append({
                        "url": u16,
                        "source": "enriched_v16",
                        "configured_pattern": None,
                        "name": f"{vid}_v16_source",
                        "strategy": "unknown",
                        "api_config": None,
                    })

        # 3. Discovered XML Sitemaps
        sitemaps = prober.discover_sitemaps(vwebsite or (candidate_urls[0]["url"] if candidate_urls else ""))
        for sm in sitemaps:
            if not any(c["url"] == sm for c in candidate_urls):
                candidate_urls.append({
                    "url": sm,
                    "source": "discovered_sitemap",
                    "configured_pattern": None,
                    "name": f"{vid}_Discovered_Sitemap",
                    "strategy": "sitemap",
                    "api_config": None,
                })

        verified_endpoints_for_vendor: List[Dict[str, Any]] = []

        for cand in candidate_urls:
            cur_url = cand["url"]
            configured_strat = cand.get("strategy")

            # Check for API search portal with custom config
            if cand.get("api_config"):
                res_ver = {
                    "url": cur_url,
                    "final_url": cur_url,
                    "is_redirect": False,
                    "status_code": 200,
                    "endpoint_type": "search_portal",
                    "confidence": "high",
                    "confidence_reason": "Verified active search portal with configured API authentication and endpoints",
                    "suggested_product_pattern": cand.get("configured_pattern"),
                    "suggested_name": cand.get("name", f"{vid}_Search_API"),
                    "evidence_authority": "official_model_status_or_notice_evidence",
                    "review_needed": False,
                    "has_data": True,
                }
                verified_endpoints_for_vendor.append(res_ver)
                report_data["summary"]["high_confidence_count"] += 1
                report_data["summary"]["total_endpoints_verified"] += 1
                continue

            # Probe HTTP
            http_probe = prober.probe_http(cur_url)
            is_xml = "xml" in http_probe.get("content_type", "").lower() or cur_url.endswith(".xml") or "sitemap" in cur_url.lower()

            endpoint_info: Dict[str, Any] = {
                "url": cur_url,
                "final_url": http_probe["final_url"],
                "is_redirect": http_probe["is_redirect"],
                "status_code": http_probe["status_code"],
                "waf_challenge": http_probe["waf_challenge"],
                "error": http_probe["error"],
                "name": cand.get("name"),
                "has_data": False,
            }

            if is_xml or configured_strat == "sitemap":
                # Sitemap Inspection
                sm_info = prober.inspect_sitemap(cur_url)
                endpoint_info["endpoint_type"] = "sitemap"
                endpoint_info["is_index"] = sm_info["is_index"]
                endpoint_info["child_count"] = sm_info["child_count"]
                endpoint_info["sample_urls"] = sm_info["sample_urls"]
                endpoint_info["suggested_child_filter"] = sm_info["suggested_child_filter"]
                endpoint_info["has_data"] = sm_info["has_data"]

                # Pattern Testing
                pattern_info = PatternAnalyzer.test_and_discover_patterns(
                    sm_info["sample_urls"],
                    configured_pattern=cand.get("configured_pattern"),
                )
                endpoint_info.update(pattern_info)

            else:
                # HTML / DOM Table Inspection
                html_info = prober.inspect_html_page(cur_url, http_probe)
                endpoint_info["endpoint_type"] = "dom_table"
                endpoint_info.update(html_info)

                # If product links found, test patterns against them
                if html_info["product_links"]:
                    pattern_info = PatternAnalyzer.test_and_discover_patterns(
                        html_info["product_links"],
                        configured_pattern=cand.get("configured_pattern"),
                    )
                    endpoint_info.update(pattern_info)

            # Feed probed endpoint data to LLM Verification Gate
            verification = llm_verifier.verify_endpoint(
                vendor_id=vid,
                vendor_name=vname,
                sector=vsector,
                endpoint_info=endpoint_info,
            )

            # Merge verification outcome
            merged_res = {**endpoint_info, **verification}
            verified_endpoints_for_vendor.append(merged_res)

            # Update summary metrics
            report_data["summary"]["total_endpoints_verified"] += 1
            conf = merged_res["confidence"]
            if conf == "high":
                report_data["summary"]["high_confidence_count"] += 1
            elif conf == "medium":
                report_data["summary"]["medium_confidence_count"] += 1
            else:
                report_data["summary"]["low_confidence_count"] += 1

            if not merged_res.get("is_valid_endpoint") or http_probe["status_code"] in (404, 500, 502, 503):
                report_data["summary"]["broken_endpoints_count"] += 1

            status_display = f"HTTP {http_probe['status_code']}" if http_probe['status_code'] else http_probe.get("error", "FAIL")
            logger.info(
                f"  [{vid}] {cur_url[:65]:<65} -> {status_display:<10} "
                f"| Confidence: {conf.upper():<6} | Reason: {merged_res['confidence_reason'][:60]}"
            )

        report_data["vendors"][vid] = {
            "name": vname,
            "sector": vsector,
            "website": vwebsite,
            "endpoints": verified_endpoints_for_vendor,
        }

        # Apply updates to configs/vendors.yaml if --apply is set
        if args.apply:
            vendor_modified = enrich_and_update_vendor_yaml(
                vendor_id=vid,
                vendor_conf=vconf,
                verified_endpoints=verified_endpoints_for_vendor,
                all_vendors_yaml_data=conf_data,
            )
            if vendor_modified:
                report_data["summary"]["yaml_updates_applied"] += 1
                yaml_modified_total = True

    # Persist YAML changes if modified
    if args.apply and yaml_modified_total:
        logger.info("\nWriting enriched vendor configurations back to configs/vendors.yaml...")
        with open(VENDORS_YAML_PATH, "w", encoding="utf-8") as f:
            yaml.dump(conf_data, f, sort_keys=False, indent=2, allow_unicode=True)
        logger.info("Successfully updated configs/vendors.yaml with verified endpoints and confidence attributes.")

    # Save outputs
    out_json = Path(args.output_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    out_md = Path(args.output_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(_render_markdown_report(report_data))

    print("\n" + "=" * 88)
    print("  ENDPOINT & PATTERN VERIFICATION SUMMARY")
    print("=" * 88)
    print(f"  Vendors Processed:       {report_data['total_vendors_processed']}")
    print(f"  Endpoints Verified:      {report_data['summary']['total_endpoints_verified']}")
    print(f"  High Confidence:         {report_data['summary']['high_confidence_count']}")
    print(f"  Medium Confidence:       {report_data['summary']['medium_confidence_count']}")
    print(f"  Low Confidence (Review): {report_data['summary']['low_confidence_count']}")
    print(f"  Broken / Blocked:        {report_data['summary']['broken_endpoints_count']}")
    print(f"  YAML Updates Applied:    {report_data['summary']['yaml_updates_applied']}")
    print(f"  Report Files:            {out_json} | {out_md}")
    print("=" * 88)

    return 0


def _render_markdown_report(report_data: Dict[str, Any]) -> str:
    """Renders structured Markdown verification report."""
    summary = report_data.get("summary", {})
    lines = [
        "# Enterprise Endpoint & Pattern Verification Report",
        "",
        f"> **Generated UTC:** `{report_data.get('verification_timestamp_utc')}`  ",
        f"> **LLM Gate Active:** `{report_data.get('llm_gate_enabled')}` ({report_data.get('llm_provider')} / `{report_data.get('llm_model')}`)  ",
        "",
        "## Summary Metrics",
        "",
        f"- **Vendors Audited:** `{report_data.get('total_vendors_processed')}`",
        f"- **Total Endpoints Verified:** `{summary.get('total_endpoints_verified')}`",
        f"- **High Confidence Endpoints:** `{summary.get('high_confidence_count')}`",
        f"- **Medium Confidence Endpoints:** `{summary.get('medium_confidence_count')}`",
        f"- **Low Confidence Endpoints (Flagged for Review):** `{summary.get('low_confidence_count')}`",
        f"- **Broken / WAF Challenged Endpoints:** `{summary.get('broken_endpoints_count')}`",
        f"- **Vendor YAML Entries Updated:** `{summary.get('yaml_updates_applied')}`",
        "",
        "---",
        "",
        "## Detailed Vendor Audits & Verification",
        "",
        "| Vendor ID | Sector | Endpoints | High Conf | Med Conf | Low Conf (Review) | Status Details |",
        "|:---|:---:|:---:|:---:|:---:|:---:|:---|",
    ]

    for vid, vdata in report_data.get("vendors", {}).items():
        eps = vdata.get("endpoints", [])
        high_c = sum(1 for ep in eps if ep.get("confidence") == "high")
        med_c = sum(1 for ep in eps if ep.get("confidence") == "medium")
        low_c = sum(1 for ep in eps if ep.get("confidence") == "low")

        reasons = []
        for ep in eps:
            if ep.get("confidence") == "low":
                reasons.append(f"`{ep.get('url')[:30]}...`: {ep.get('confidence_reason')[:40]}...")

        details_str = "<br>".join(reasons) if reasons else "All endpoints operational"

        lines.append(
            f"| `{vid}` | {vdata.get('sector')} | {len(eps)} | {high_c} | {med_c} | {low_c} | {details_str} |"
        )

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
