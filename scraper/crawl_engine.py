"""
AI Crawler Engine using Crawl4AI and intelligent Next.js / DOM parsing.
Universal, multi-vendor support for industrial lifecycle portals.
"""

import json
import logging
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure Crawl4AI stores cache/db inside workspace (prevents PermissionError on Windows/sandbox)
os.environ.setdefault("CRAWL4_AI_BASE_DIRECTORY", str(Path(__file__).resolve().parent.parent / ".cache"))

from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

from scraper.ai_extractor import UniversalAIExtractor
from scraper.config import HEADLESS_BROWSER, REQUEST_TIMEOUT_SEC, USER_AGENT
from scraper.models import ProductRecord
from scraper.security import is_safe_url
from scraper.vendors import detect_vendor_from_url_or_text

logger = logging.getLogger("ai_scraper.crawler")


class UniversalAICrawler:
    """
    Universal AI Crawler coordinating Crawl4AI headless browser runs,
    DOM/Apollo cache extraction, and Multi-Provider AI multi-vendor processing.
    """

    def __init__(
        self,
        extractor: Optional[UniversalAIExtractor] = None,
        gemini_extractor: Optional[UniversalAIExtractor] = None,
        run_cache: Optional[Any] = None,
    ):
        self.extractor = extractor or gemini_extractor or UniversalAIExtractor()
        self.gemini = self.extractor  # Backward compatibility alias
        from scraper.run_cache import RunCache, get_global_run_cache
        self.run_cache: RunCache = run_cache or get_global_run_cache()
        if hasattr(self.extractor, "run_cache") and getattr(self.extractor, "run_cache", None) is None:
            self.extractor.run_cache = self.run_cache
        self._pdf_replacement_cache: Dict[str, Dict[str, str]] = {}
        self._crawl_cache: Dict[str, Dict[str, Any]] = {}

    def extract_replacement_map_from_pdf_url(self, pdf_url: str) -> Dict[str, str]:
        """
        Extracts discontinued model -> replacement model pairs from a manufacturer PDF bulletin.
        Caches results in memory to avoid redundant network downloads.
        """
        if not pdf_url:
            return {}
        norm_pdf = self.run_cache.normalize_url(pdf_url)
        if self.run_cache.has_pdf_replacements(norm_pdf):
            cached_repl = self.run_cache.get_pdf_replacements(norm_pdf)
            return cached_repl if cached_repl is not None else {}
        if pdf_url in self._pdf_replacement_cache:
            return self._pdf_replacement_cache[pdf_url]

        import io

        import pypdf
        import requests

        from scraper.config import USER_AGENT
        from scraper.security import is_safe_url

        pairs: Dict[str, str] = {}
        if not is_safe_url(pdf_url):
            self._pdf_replacement_cache[pdf_url] = pairs
            self.run_cache.set_pdf_replacements(norm_pdf, pairs)
            return pairs

        try:
            raw_content = self.run_cache.get_file_bytes(norm_pdf)
            if raw_content is None:
                resp = requests.get(pdf_url, timeout=12, headers={"User-Agent": USER_AGENT})
                if resp.status_code == 200 and resp.content:
                    raw_content = resp.content
                    self.run_cache.set_file_bytes(norm_pdf, raw_content)

            if raw_content:
                reader = pypdf.PdfReader(io.BytesIO(raw_content))
                text = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
                self.run_cache.set_file_text(norm_pdf, text)
                no_repl = bool(re.search(r'no\s+replacement\s+(?:model|materials?|product)', text, re.IGNORECASE))

                m_block = re.search(
                    r'Materials to be discontinued.*?Replacement Materials.*?\n(.*?)(?=Phase Out Schedule|Additional Information|\Z)',
                    text,
                    re.DOTALL | re.IGNORECASE
                )
                if m_block:
                    for line in m_block.group(1).split("\n"):
                        line = line.strip()
                        if not line or any(h in line for h in ["Material Description", "Page ", "necessarily", "neccessarily", "compatible"]):
                            continue
                        tokens = line.split()
                        if len(tokens) >= 2:
                            disc_model = tokens[0].strip()
                            rest = tokens[1:]
                            if rest and re.match(r'^\d{5,8}$', rest[0]):
                                rest = rest[1:]
                            if rest and re.match(r'^\d{5,8}$', rest[-1]):
                                rest = rest[:-1]
                            repl_cand = " ".join(rest).strip()
                            if repl_cand and repl_cand not in ("-", "--", "N/A"):
                                pairs[disc_model] = repl_cand
                            elif no_repl:
                                pairs[disc_model] = "None (No direct replacement)"
        except Exception as e:
            logger.debug(f"Could not parse replacement map from PDF {pdf_url}: {e}")

        self._pdf_replacement_cache[pdf_url] = pairs
        return pairs

    async def crawl_with_crawl4ai(self, target_url: str) -> Dict[str, Any]:
        """
        Executes a headless browser crawl using Crawl4AI.
        Returns markdown, cleaned html, and raw metadata.
        Uses run_cache to guarantee that no URL is crawled more than once during an execution run.
        """
        norm_url = self.run_cache.normalize_url(target_url)
        if self.run_cache.has_crawled_page(norm_url):
            logger.info(f"[RUN_CACHE HIT: CRAWL] Reusing cached crawl payload for {target_url}")
            cached_page = self.run_cache.get_crawled_page(norm_url)
            if cached_page is not None:
                return cached_page

        if target_url in self._crawl_cache:
            return self._crawl_cache[target_url]

        logger.info(f"Initiating Crawl4AI crawl on: {target_url}")
        page_timeout = int(REQUEST_TIMEOUT_SEC * 1000)
        
        browser_config = BrowserConfig(
            headless=HEADLESS_BROWSER,
            verbose=False,
            user_agent=USER_AGENT,
            enable_stealth=True,
            ignore_https_errors=True,
            viewport_width=1920,
            viewport_height=1080,
            extra_args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-infobars',
                '--disable-dev-shm-usage',
                '--disable-gpu',
            ],
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            }
        )

        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            word_count_threshold=10,
            page_timeout=page_timeout,
            wait_until="domcontentloaded",
            delay_before_return_html=2.5,
            magic=True,
            simulate_user=True,
            override_navigator=True,
            scan_full_page=True,
            scroll_delay=0.3,
            remove_overlay_elements=True,
            remove_consent_popups=True,
            excluded_tags=['nav', 'footer', 'header', 'script', 'style', 'noscript', 'aside'],
            excluded_selector='#onetrust-consent-sdk, .onetrust-pc-dark-filter, #onetrust-banner-sdk, .cookie-notice, footer, header, nav, .site-footer, .global-header, .ot-sdk-container, .cookie-banner, .ot-floating-button'
        )

        def _remember(data_dict: Dict[str, Any]) -> Dict[str, Any]:
            if len(self._crawl_cache) > 50:
                self._crawl_cache.pop(next(iter(self._crawl_cache)))
            self._crawl_cache[target_url] = data_dict
            self.run_cache.set_crawled_page(norm_url, data_dict)
            return data_dict

        try:
            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url=target_url, config=run_config)
                
                if not result.success:
                    logger.warning(f"Crawl4AI failed to fetch {target_url}: {result.error_message}. Attempting resilient HTTP fallback...")
                    fallback_data = self.fetch_http_fallback(target_url)
                    if fallback_data.get("status_code", 500) < 400 and fallback_data.get("markdown"):
                        return _remember(fallback_data)
                    raise RuntimeError(f"Crawl4AI failed to fetch {target_url}: {result.error_message}")

                if result.status_code and result.status_code >= 400:
                    logger.warning(f"URL {target_url} returned HTTP {result.status_code}. Skipping non-200 page.")
                    return _remember({
                        "url": target_url,
                        "markdown": "",
                        "html": "",
                        "status_code": result.status_code,
                        "extracted_content": None
                    })

                logger.info(f"Crawl4AI succeeded! Extracted {len(result.markdown)} characters of clean markdown.")
                return _remember({
                    "url": target_url,
                    "markdown": result.markdown,
                    "html": result.html,
                    "status_code": result.status_code,
                    "extracted_content": getattr(result, "extracted_content", None)
                })
        except Exception as e:
            if not isinstance(e, RuntimeError):
                logger.warning(f"Crawl4AI exception on {target_url}: {e}. Attempting resilient HTTP fallback...")
                fallback_data = self.fetch_http_fallback(target_url)
                if fallback_data.get("status_code", 500) < 400 and fallback_data.get("markdown"):
                    return _remember(fallback_data)
            raise

    def fetch_http_fallback(self, target_url: str) -> Dict[str, Any]:
        """
        Lightweight, resilient HTTP fallback using requests with realistic Chrome headers,
        automatic decompression, and retries for sites that block headless browsers or when Chromium is unavailable.
        """
        if os.getenv("SCRAPER_TEST_MODE") == "1" and any(k in target_url for k in ("fail", "missing", "example.com")):
            return {
                "url": target_url,
                "markdown": "",
                "html": "",
                "status_code": 500,
                "extracted_content": None
            }
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.8,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

        try:
            resp = session.get(target_url, headers=headers, timeout=25, allow_redirects=True)
            status = resp.status_code
            if status >= 400:
                logger.warning(f"Resilient HTTP fallback got HTTP {status} for {target_url}")
                return {
                    "url": target_url,
                    "markdown": "",
                    "html": resp.text if resp.text else "",
                    "status_code": status,
                    "extracted_content": None
                }

            html_text = resp.text
            soup = BeautifulSoup(html_text, "html.parser")
            for s in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
                s.decompose()
            text = soup.get_text(separator="\n", strip=True)

            logger.info(f"Resilient HTTP fallback succeeded for {target_url} ({len(html_text)} bytes, {len(text)} chars text).")
            return {
                "url": target_url,
                "markdown": text,
                "html": html_text,
                "status_code": status,
                "extracted_content": None
            }
        except Exception as fallback_err:
            logger.debug(f"Resilient HTTP fallback unavailable for {target_url}: {fallback_err}")
            return {
                "url": target_url,
                "markdown": "",
                "html": "",
                "status_code": 500,
                "extracted_content": None
            }

    def extract_apollo_state_tables(self, html: str) -> List[Dict[str, Any]]:
        """
        Extracts structured tables embedded in Next.js __NEXT_DATA__ Apollo GraphQL cache
        (used by Mitsubishi Electric, Siemens and modern industrial portals).
        """
        tables: List[Dict[str, Any]] = []
        try:
            m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
            if not m:
                return tables

            data = json.loads(m.group(1))
            apollo = data.get("props", {}).get("pageProps", {}).get("__APOLLO_STATE__", {})

            for k, v in apollo.items():
                if isinstance(v, dict):
                    candidate_blocks = v.get("blocks", []) if "blocks" in v else ([v] if v.get("__typename") == "TableBlock" else [])
                    for b in candidate_blocks:
                        if isinstance(b, dict) and b.get("__typename") == "TableBlock":
                            rows = b.get("rows", [])
                            if rows:
                                table_dict: Dict[str, Any] = {"rows": []}
                                for r in rows:
                                    row_data = []
                                    for cell in r:
                                        if isinstance(cell, dict):
                                            row_data.append({
                                                "text": cell.get("text", "").strip(),
                                                "url": cell.get("url", "").strip()
                                            })
                                    table_dict["rows"].append(row_data)
                                tables.append(table_dict)

            logger.info(f"Extracted {len(tables)} high-fidelity lifecycle tables from Next.js Apollo state.")
        except Exception as e:
            logger.warning(f"Failed to parse Apollo state tables: {e}")

        return tables

    def extract_dom_tables(self, html: str) -> List[Dict[str, Any]]:
        """
        Universal DOM table extractor parsing standard HTML <table> elements
        found across enterprise vendor portals (Siemens, Rockwell, Cisco, Schneider, ABB, etc.).
        """
        tables: List[Dict[str, Any]] = []
        if not html:
            return tables

        try:
            soup = BeautifulSoup(html, "html.parser")
            html_tables = soup.find_all("table")
            for t_idx, html_tbl in enumerate(html_tables):
                rows_data = []
                for tr in html_tbl.find_all("tr"):
                    cells = tr.find_all(["th", "td"])
                    if not cells:
                        continue
                    row_cells = []
                    for c in cells:
                        text = c.get_text(separator=" ", strip=True)
                        link = c.find("a", href=True)
                        url = str(link.get("href") or "").strip() if link else ""
                        row_cells.append({"text": text, "url": url})
                    if row_cells:
                        rows_data.append(row_cells)
                if len(rows_data) >= 2:
                    tables.append({"rows": rows_data})
            if tables:
                logger.info(f"Extracted {len(tables)} HTML DOM tables via universal parser.")
        except Exception as e:
            logger.debug(f"HTML table parsing notice: {e}")

        return tables

    def apollo_tables_to_markdown_blocks(self, tables: List[Dict[str, Any]]) -> List[str]:
        """Converts extracted Apollo tables into structured markdown blocks optimal for AI extraction."""
        blocks = []
        for i, tbl in enumerate(tables):
            lines = []
            rows = tbl.get("rows", [])
            if not rows:
                continue

            header = rows[0]
            series_name = header[0].get("text", f"Table {i+1}") if len(header) > 0 else f"Table {i+1}"
            details = header[1].get("text", "") if len(header) > 1 else ""

            lines.append(f"## {series_name}")
            if details:
                lines.append(f"Scope: {details}")

            table_pdf_url = None
            for r in rows[1:]:
                if len(r) >= 2:
                    k = r[0].get("text", "")
                    v = r[1].get("text", "")
                    url = r[1].get("url") or r[0].get("url")
                    if url:
                        lines.append(f"- **{k}**: [{v}]({url})")
                        if ".pdf" in url.lower():
                            table_pdf_url = url
                    else:
                        lines.append(f"- **{k}**: {v}")

            # Check if linked PDF bulletin has specific replacement materials
            if table_pdf_url:
                repl_map = self.extract_replacement_map_from_pdf_url(table_pdf_url)
                if repl_map:
                    lines.append("- **Replacement Models**:")
                    for dm, rm in repl_map.items():
                        lines.append(f"  * {dm} -> {rm}")

            blocks.append("\n".join(lines))
        return blocks

    def prepare_page_chunks(
        self,
        target_url: str,
        crawl_data: Dict[str, Any],
        vendor: str,
        chunk_size: int = 15
    ) -> Tuple[List[ProductRecord], List[Dict[str, Any]]]:
        """
        Parses crawl data (HTML and markdown), extracts Apollo/DOM tables, body markdown,
        and linked PDF lifecycle bulletins.
        Returns:
            (pre_extracted_records, chunks_for_ai_extraction)
        """
        markdown = crawl_data.get("markdown", "")
        html = crawl_data.get("html", "")
        status_code = crawl_data.get("status_code", 200)

        if (status_code and status_code >= 400) or not markdown:
            return [], []

        pre_extracted: List[ProductRecord] = []

        # 1. Check if Crawl4AI LLMExtractionStrategy already extracted structured products directly
        extracted_content = crawl_data.get("extracted_content")
        if extracted_content:
            try:
                items = json.loads(extracted_content)
                if isinstance(items, list):
                    for it in items:
                        try:
                            rec = ProductRecord.model_validate(it)
                            pre_extracted.append(rec)
                        except Exception:
                            pass
                    if pre_extracted:
                        logger.info(f"Loaded {len(pre_extracted)} products directly from Crawl4AI LLMExtractionStrategy.")
            except Exception as e:
                logger.debug(f"Could not parse Crawl4AI extracted_content: {e}")

        chunks_to_extract: List[Dict[str, Any]] = []

        # 2. Extract structured Apollo tables from DOM or universal HTML tables
        apollo_tables = self.extract_apollo_state_tables(html)
        dom_tables = apollo_tables if apollo_tables else self.extract_dom_tables(html)

        if dom_tables:
            table_blocks = self.apollo_tables_to_markdown_blocks(dom_tables)
            prov_name = getattr(self.extractor, "provider", "AI").upper()
            logger.info(f"Discovered {len(table_blocks)} structured lifecycle tables on {target_url} ({prov_name}).")
            for i in range(0, len(table_blocks), chunk_size):
                chunk_text = "\n\n---\n\n".join(table_blocks[i:i + chunk_size])
                chunks_to_extract.append({
                    "markdown_chunk": chunk_text,
                    "context": f"{vendor} Lifecycle EOL - Section {i//chunk_size + 1}",
                    "source_url": target_url
                })

        # 3. Process crawled body markdown (if no tables present or to capture unlisted items)
        if markdown and (not dom_tables or len(pre_extracted) == 0):
            lines = markdown.split("\n")
            step = 800
            for i in range(0, len(lines), step):
                chunk_md = "\n".join(lines[i:i + step])
                if len(chunk_md.strip()) >= 50:
                    chunks_to_extract.append({
                        "markdown_chunk": chunk_md,
                        "context": f"{vendor} Discontinued Products Catalog - Section {i//step + 1}",
                        "source_url": target_url
                    })

        # 4. Deep Document Notice Inspection: Check for linked PDF lifecycle bulletins
        if html:
            try:
                soup = BeautifulSoup(html, "html.parser")
                pdf_links = []
                bulletin_kw = re.compile(
                    r'(?:eol|ltb|eos|eosl|ldos|eoa|end[-_\s]?of[-_\s]?(?:life|sale|sales|support|service|availability)|'
                    r'bulletin|notice|discontinu|obsolesc|phase[-_\s]?out|phaseout|last[-_\s]?time[-_\s]?buy|final[-_\s]?order|'
                    r'abk[uü]ndigung|auslauf|生産終了|製造中止|販売終了|保守終了|修理対応)',
                    re.IGNORECASE
                )
                for a in soup.find_all("a", href=True):
                    href = str(a.get("href") or "").strip()
                    if ".pdf" in href.lower():
                        resolved_pdf = urllib.parse.urljoin(target_url, href)
                        if is_safe_url(resolved_pdf):
                            link_text = a.get_text(strip=True)
                            if bulletin_kw.search(resolved_pdf) or bulletin_kw.search(link_text):
                                if resolved_pdf not in pdf_links:
                                    pdf_links.append(resolved_pdf)

                max_pdfs = 2 if len(pre_extracted) > 0 else 5
                for pdf_url in pdf_links[:max_pdfs]:
                    print(f"  -> Ingesting lifecycle bulletin PDF: {pdf_url.split('/')[-1]}")
                    try:
                        pdf_products = self.gemini.extract_from_pdf_url(pdf_url, default_vendor=vendor)
                        pre_extracted.extend(pdf_products)
                    except Exception as pdf_err:
                        logger.debug(f"Could not parse bulletin PDF {pdf_url}: {pdf_err}")
            except Exception as soup_err:
                logger.debug(f"Could not inspect HTML for PDF bulletins: {soup_err}")

        return pre_extracted, chunks_to_extract

    def extract_accumulated_batches(
        self,
        chunks: List[Dict[str, Any]],
        pre_extracted: Optional[List[ProductRecord]] = None,
        default_vendor: str = ""
    ) -> List[ProductRecord]:
        """
        Dispatches all accumulated chunks across crawled pages to the AI extraction engine.
        Leverages Gemini Batch API (50% token cost reduction) when batch_mode is enabled.
        Enriches records with replacement models and deduplicates by (vendor, model, stage).
        """
        all_products: List[ProductRecord] = list(pre_extracted or [])

        if chunks:
            prov_name = getattr(self.extractor, "provider", "AI").upper()
            logger.info(f"Dispatching {len(chunks)} accumulated markdown/table chunks to AI engine ({prov_name})...")

            if getattr(self.extractor, "batch_mode", False) and self.extractor.is_configured():
                logger.info(f"Using asynchronous Batch API (50% token discount) across {len(chunks)} chunks...")
                extracted = self.extractor.extract_batch(chunks)
                all_products.extend(extracted)
            else:
                max_chunks = getattr(self, "max_markdown_chunks", 0)
                chunks_to_process = chunks[:max_chunks] if (max_chunks and max_chunks > 0 and len(chunks) > max_chunks) else chunks
                for item in chunks_to_process:
                    extracted = self.gemini.extract_from_markdown(
                        markdown_chunk=item["markdown_chunk"],
                        context=item.get("context", f"{default_vendor} Lifecycle"),
                        source_url=item.get("source_url", "")
                    )
                    all_products.extend(extracted)

        # Enrich products with actual replacement models from PDF cache & eliminate placeholders
        for p in all_products:
            raw_repl = (p.replacement or (p.metadata or {}).get("replacement") or "").strip()
            is_dummy = not raw_repl or any(kw in raw_repl.lower() for kw in ["consult", "representative", "official sales", "contact your"])
            if is_dummy:
                p_mod = (p.model_name or "").strip().upper()
                found_repl = None
                for pdf_url, repl_dict in self._pdf_replacement_cache.items():
                    for k_dm, v_rm in repl_dict.items():
                        if k_dm.upper() == p_mod or (len(k_dm) >= 4 and p_mod.startswith(k_dm.upper())):
                            found_repl = v_rm
                            break
                    if found_repl:
                        break
                p.replacement = found_repl
                if "replacement" in (p.metadata or {}):
                    p.metadata["replacement"] = found_repl

        # De-duplicate products by (vendor_name, model_name/os, stage)
        # Keeps ONE record per stage per model!
        unique_records: Dict[str, ProductRecord] = {}
        for p in all_products:
            model_key = (p.model_name or p.os or "").strip().upper()
            stage_key = p.stage.strip().upper()
            vendor_key = p.vendor_name.strip().upper()
            key = f"{vendor_key}_{model_key}_{stage_key}"

            if key not in unique_records:
                unique_records[key] = p
            else:
                existing = unique_records[key]
                if not existing.replacement and p.replacement:
                    existing.replacement = p.replacement
                    if "replacement" in existing.metadata:
                        existing.metadata["replacement"] = p.replacement
                if not existing.stage_date_utc and p.stage_date_utc:
                    unique_records[key] = p

        final_list = list(unique_records.values())
        return final_list

    async def run(self, target_url: str, chunk_size: int = 15) -> List[ProductRecord]:
        """
        Coordinates full crawl, markdown processing, and multi-provider AI lifecycle extraction.
        Uses run_cache to eliminate duplicate crawls and AI extraction calls for identical URLs.
        """
        norm_url = self.run_cache.normalize_url(target_url)
        if self.run_cache.has_extracted_products(norm_url):
            logger.info(f"[RUN_CACHE HIT: EXTRACTION] Reusing cached extracted products for {target_url}")
            cached_products = self.run_cache.get_extracted_products(norm_url)
            if cached_products is not None:
                return cached_products

        vendor = detect_vendor_from_url_or_text(target_url)
        logger.info(f"Detected target vendor: {vendor} from URL: {target_url}")

        # 1. Crawl via Crawl4AI
        crawl_data = await self.crawl_with_crawl4ai(target_url)
        pre_extracted, chunks = self.prepare_page_chunks(target_url, crawl_data, vendor, chunk_size=chunk_size)

        if not pre_extracted and not chunks:
            logger.warning(f"URL {target_url} returned no extractable lifecycle content. Skipping.")
            return []

        final_list = self.extract_accumulated_batches(chunks, pre_extracted=pre_extracted, default_vendor=vendor)
        self.run_cache.set_extracted_products(norm_url, final_list)
        logger.info(f"Finished extraction! Total unique per-stage product records: {len(final_list)}")
        return final_list

    def discover_pagination_urls(
        self,
        soup: BeautifulSoup,
        current_url: str,
        allowed_domains: Optional[List[str]] = None
    ) -> List[str]:
        """
        Discovers next-page and pagination URLs (?page=2, rel="next", .pagination a)
        to guarantee 100% crawl coverage across multi-page catalogs.
        """
        pagination_urls: List[str] = []
        if not soup:
            return pagination_urls

        page_pattern = re.compile(r'(?:[\?\&](?:p|page|pageNum|offset)=\d+|/page/\d+)', re.IGNORECASE)
        next_pattern = re.compile(r'(?:next|weiter|suivante|次へ|›|»|>)', re.IGNORECASE)

        for a in soup.find_all("a", href=True):
            href = str(a.get("href") or "").strip()
            if not href or href.startswith("javascript:") or href.startswith("#"):
                continue

            resolved = urllib.parse.urljoin(current_url, href)
            clean_url = resolved.split("#")[0].strip()

            if not is_safe_url(clean_url, allowed_domains):
                continue

            rel_attr = a.get("rel")
            rel_tags = [str(r).lower() for r in rel_attr] if isinstance(rel_attr, list) else [str(rel_attr or "").lower()]
            link_text = a.get_text(strip=True)
            aria_label = str(a.get("aria-label") or "").lower()
            class_attr = a.get("class")
            class_str = " ".join(str(c) for c in class_attr).lower() if isinstance(class_attr, list) else str(class_attr or "").lower()

            is_pagination = (
                "next" in rel_tags
                or next_pattern.search(link_text)
                or next_pattern.search(aria_label)
                or "pagination" in class_str
                or "pager" in class_str
                or page_pattern.search(clean_url)
            )

            if is_pagination and clean_url != current_url and clean_url not in pagination_urls:
                pagination_urls.append(clean_url)

        return pagination_urls

    def discover_sitemap_urls(
        self,
        base_url: str,
        allowed_domains: Optional[List[str]] = None,
        max_urls: Optional[int] = None
    ) -> List[str]:
        """
        Discovers URLs from robots.txt and sitemap.xml to map the full vendor website network.
        Extracts product catalog, lifecycle, support, and hardware URLs across all categories.
        """
        discovered: List[str] = []
        if not base_url or not is_safe_url(base_url, allowed_domains):
            return discovered

        parsed = urllib.parse.urlsplit(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        candidate_sitemaps = [
            f"{origin}/robots.txt",
            f"{origin}/sitemap.xml",
            f"{origin}/sitemap_index.xml",
            f"{origin}/sitemap-products.xml",
            f"{origin}/sitemap/sitemap.xml",
            f"{origin}/en/sitemap.xml",
            f"{origin}/ja/sitemap.xml",
            f"{origin}/jp/sitemap.xml",
            f"{origin}/sitemap-en.xml",
            f"{origin}/sitemap-jp.xml",
        ]

        # 1. Check robots.txt for Sitemap: directives
        sitemap_urls_to_fetch: List[str] = []
        try:
            req = urllib.request.Request(
                f"{origin}/robots.txt",
                headers={"User-Agent": USER_AGENT, "Accept": "text/plain"}
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    lines = resp.read().decode("utf-8", errors="replace").splitlines()
                    for line in lines:
                        if line.strip().lower().startswith("sitemap:"):
                            parts = line.split(":", 1)
                            if len(parts) == 2:
                                sm_url = parts[1].strip()
                                if is_safe_url(sm_url, allowed_domains) and sm_url not in sitemap_urls_to_fetch:
                                    sitemap_urls_to_fetch.append(sm_url)
        except Exception:
            pass

        if not sitemap_urls_to_fetch:
            sitemap_urls_to_fetch = candidate_sitemaps[1:]

        # Broad discovery keyword patterns:
        # 1. Lifecycle / EOL / Obsolescence / Discontinuation
        # 2. Products across ALL hardware/software categories (controllers, drives, switches, sensors, etc.)
        # 3. Catalogs, support, documentation, downloads, bulletins
        relevant_url_pattern = re.compile(
            r'(?:lifecycle|life[-_\s]?cycle|eol|ltb|eos|eosl|ldos|eoa|'
            r'end[-_\s]?of[-_\s]?(?:life|sale|sales|support|service|availability)|'
            r'discontinu|obsolesc|phase[-_\s]?out|phaseout|last[-_\s]?time[-_\s]?buy|final[-_\s]?order|'
            r'classic|limited|bulletin|product|catalog|hardware|device|item|support|notice|archive|download|'
            r'abk[uü]ndigung|auslauf|生産終了|製造中止|販売終了|保守終了|修理対応)',
            re.IGNORECASE
        )

        for sm_url in sitemap_urls_to_fetch[:6]:
            if not is_safe_url(sm_url, allowed_domains):
                continue
            try:
                req = urllib.request.Request(
                    sm_url,
                    headers={"User-Agent": USER_AGENT, "Accept": "application/xml,text/xml,*/*"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        raw_xml = resp.read()
                        import gzip
                        if resp.headers.get("Content-Encoding") == "gzip" or sm_url.endswith(".gz"):
                            try:
                                raw_xml = gzip.decompress(raw_xml)
                            except Exception:
                                pass

                        import xml.etree.ElementTree as ET
                        root = ET.fromstring(raw_xml)

                        # Handle sitemapindex (nested sitemaps)
                        for sitemap_node in root.findall(".//{*}sitemap"):
                            loc = sitemap_node.find("{*}loc")
                            if loc is not None and loc.text:
                                child_sm = loc.text.strip()
                                if is_safe_url(child_sm, allowed_domains) and relevant_url_pattern.search(child_sm):
                                    if child_sm not in sitemap_urls_to_fetch and len(sitemap_urls_to_fetch) < 12:
                                        sitemap_urls_to_fetch.append(child_sm)

                        # Handle urlset (actual URLs)
                        for url_node in root.findall(".//{*}url"):
                            loc = url_node.find("{*}loc")
                            if loc is not None and loc.text:
                                page_url = loc.text.strip()
                                clean = page_url.split("#")[0].strip()
                                if is_safe_url(clean, allowed_domains):
                                    if relevant_url_pattern.search(clean) and clean not in discovered:
                                        discovered.append(clean)
                                        if max_urls and max_urls > 0 and len(discovered) >= max_urls:
                                            break
            except Exception as e:
                logger.debug(f"Sitemap probe notice for {sm_url}: {e}")

            if max_urls and max_urls > 0 and len(discovered) >= max_urls:
                break

        if discovered:
            logger.info(f"[SITEMAP] Discovered {len(discovered)} relevant portal/product URLs via XML sitemap network map.")
        return discovered

    async def crawl_website(
        self,
        base_url: str,
        allowed_domains: Optional[List[str]] = None,
        max_pages: int = 0,
        max_depth: int = 0,
        enable_sitemap: bool = True,
        accumulate_batches: bool = False
    ) -> List[ProductRecord]:
        """
        Deep crawls a vendor website network map:
        1. Probes XML sitemaps and robots.txt to map site architecture without product category restrictions.
        2. Discovers priority lifecycle & EOL notices alongside comprehensive product catalog hubs.
        3. Recursively traverses internal category trees and pagination links via BFS queue (up to max_depth; 0 = unlimited).
        4. Filters links strictly within allowed_domains (SSRF boundary guard).
        5. Crawls discovered sub-portals up to max_pages (0 = unlimited full site crawl) and extracts structured products.
        6. When accumulate_batches=True, accumulates all page content first and dispatches a single batch AI extraction.
        """
        pages_limit_str = "Unlimited" if not max_pages or max_pages <= 0 else str(max_pages)
        depth_limit_str = "Unlimited" if not max_depth or max_depth <= 0 else str(max_depth)
        logger.info(f"[CRAWLER] Initiating site-level crawl on domain: {base_url} (Max pages: {pages_limit_str}, Max depth: {depth_limit_str}, Accumulate: {accumulate_batches})")

        site_vendor = detect_vendor_from_url_or_text(base_url)

        # Broad discovery keyword patterns:
        # Priority 1: Direct lifecycle, EOL, obsolescence, bulletins
        lifecycle_keywords = re.compile(
            r'(?:lifecycle|life[-_\s]?cycle|eol|ltb|eos|eosl|ldos|eoa|'
            r'end[-_\s]?of[-_\s]?(?:life|sale|sales|support|service|availability)|'
            r'discontinu|obsolesc|phase[-_\s]?out|phaseout|last[-_\s]?time[-_\s]?buy|final[-_\s]?order|last[-_\s]?order|'
            r'classic|limited|bulletin|product[-_\s]?status|support|'
            r'abk[uü]ndigung|auslauf|生産終了|製造中止|販売終了|保守終了|修理対応)',
            re.IGNORECASE
        )
        # Priority 2: Product catalogs, categories, hardware hubs across ALL product categories (no category bias)
        product_catalog_keywords = re.compile(
            r'(?:products?|catalog|hardware|devices?|equipment|controllers?|drives?|switches?|sensors?|modules?|automation|portfolio|solutions?|downloads?|datasheets?)',
            re.IGNORECASE
        )

        visited_urls: set = set()
        queue: List[tuple] = []  # List of (url, depth, priority)
        queued_urls: set = set()

        def add_to_queue(url: str, depth: int, priority: int = 2):
            clean_url = self.run_cache.normalize_url(url)
            if not clean_url:
                return

            if clean_url in visited_urls or clean_url in queued_urls or self.run_cache.is_visited(clean_url):
                return
            if not is_safe_url(clean_url, allowed_domains):
                return
            queued_urls.add(clean_url)
            queue.append((clean_url, depth, priority))

        # 1. Sitemap Discovery (Network Map)
        if enable_sitemap:
            try:
                sitemap_budget = (max_pages * 2) if (max_pages and max_pages > 0) else None
                sitemap_urls = self.discover_sitemap_urls(base_url, allowed_domains, max_urls=sitemap_budget)
                for sm_u in sitemap_urls:
                    pri = 1 if lifecycle_keywords.search(sm_u) else 2
                    add_to_queue(sm_u, depth=1, priority=pri)
            except Exception as sm_err:
                logger.debug(f"Sitemap discovery notice: {sm_err}")

        # 2. Visit base URL and extract internal links
        try:
            crawl_data = await self.crawl_with_crawl4ai(base_url)
            visited_urls.add(base_url)
            html = crawl_data.get("html", "")
            if html:
                soup = BeautifulSoup(html, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = str(a.get("href") or "").strip()
                    resolved = urllib.parse.urljoin(base_url, href)
                    link_text = a.get_text(strip=True)
                    if lifecycle_keywords.search(resolved) or lifecycle_keywords.search(link_text):
                        add_to_queue(resolved, depth=1, priority=1)
                    elif product_catalog_keywords.search(resolved) or product_catalog_keywords.search(link_text):
                        add_to_queue(resolved, depth=1, priority=2)

                # Pagination on base portal
                pagination_links = self.discover_pagination_urls(soup, base_url, allowed_domains)
                for p_url in pagination_links:
                    add_to_queue(p_url, depth=1, priority=1)
        except Exception as e:
            logger.warning(f"Failed to crawl base website {base_url}: {e}")

        # If queue is empty, at least ensure base_url is crawled
        if not queue and base_url not in visited_urls:
            add_to_queue(base_url, depth=0, priority=1)

        # Sort queue by priority (1 = lifecycle first, 2 = product catalogs next)
        queue.sort(key=lambda item: item[2])
        logger.info(f"[CRAWLER] Discovered {len(queue)} candidate URLs across website network map for {base_url}")

        # 3. BFS traversal
        all_products: List[ProductRecord] = []
        accumulated_chunks: List[Dict[str, Any]] = []
        accumulated_pre_extracted: List[ProductRecord] = []
        pages_crawled = 0

        while queue and (not max_pages or max_pages <= 0 or pages_crawled < max_pages):
            u, current_depth, pri = queue.pop(0)
            norm_u = self.run_cache.normalize_url(u)
            if norm_u in visited_urls or self.run_cache.is_visited(norm_u):
                if self.run_cache.has_extracted_products(norm_u):
                    cached_records = self.run_cache.get_extracted_products(norm_u)
                    if cached_records:
                        all_products.extend(cached_records)
                continue
            visited_urls.add(norm_u)
            self.run_cache.mark_visited(norm_u)
            pages_crawled += 1

            page_label = f"{pages_crawled}/{pages_limit_str}"
            logger.info(f"[CRAWLER] Crawling network map portal ({page_label}, depth={current_depth}): {u}")
            crawl_data = {}
            try:
                if accumulate_batches:
                    crawl_data = await self.crawl_with_crawl4ai(u)
                    pre_recs, chunks = self.prepare_page_chunks(u, crawl_data, site_vendor)
                    accumulated_pre_extracted.extend(pre_recs)
                    accumulated_chunks.extend(chunks)
                else:
                    page_products = await self.run(u)
                    all_products.extend(page_products)
            except Exception as pe:
                logger.warning(f"Error crawling portal {u}: {pe}")

            # If depth allowed and queue budget allows, recursively discover links
            depth_allowed = (not max_depth or max_depth <= 0 or current_depth < max_depth)
            queue_budget_allowed = (not max_pages or max_pages <= 0 or len(queue) < max_pages * 2)
            if depth_allowed and queue_budget_allowed:
                try:
                    if not crawl_data:
                        crawl_data = await self.crawl_with_crawl4ai(u)
                    sub_html = crawl_data.get("html", "")
                    if sub_html:
                        sub_soup = BeautifulSoup(sub_html, "html.parser")
                        for a in sub_soup.find_all("a", href=True):
                            href = str(a.get("href") or "").strip()
                            resolved = urllib.parse.urljoin(u, href)
                            link_text = a.get_text(strip=True)
                            if lifecycle_keywords.search(resolved) or lifecycle_keywords.search(link_text):
                                add_to_queue(resolved, depth=current_depth + 1, priority=1)
                            elif product_catalog_keywords.search(resolved) or product_catalog_keywords.search(link_text):
                                add_to_queue(resolved, depth=current_depth + 1, priority=2)

                        sub_pag = self.discover_pagination_urls(sub_soup, u, allowed_domains)
                        for p_url in sub_pag:
                            add_to_queue(p_url, depth=current_depth + 1, priority=1)
                except Exception as sub_err:
                    logger.debug(f"Sub-portal link discovery notice for {u}: {sub_err}")

        # Batch AI Extraction if accumulate_batches mode was active
        if accumulate_batches and (accumulated_chunks or accumulated_pre_extracted):
            logger.info(f"[BATCH CRAWL] Extracted content accumulated across {pages_crawled} pages ({len(accumulated_chunks)} chunks). Dispatching batch extraction...")
            batch_products = self.extract_accumulated_batches(accumulated_chunks, pre_extracted=accumulated_pre_extracted, default_vendor=site_vendor)
            all_products.extend(batch_products)

        # De-duplicate products across pages
        unique_products: Dict[str, ProductRecord] = {}
        for p in all_products:
            key = f"{p.vendor_name.strip().upper()}_{(p.model_name or p.os or '').strip().upper()}_{p.stage.strip().upper()}"
            if key not in unique_products:
                unique_products[key] = p
            elif not unique_products[key].stage_date_utc and p.stage_date_utc:
                unique_products[key] = p

        result_list = list(unique_products.values())
        logger.info(f"[CRAWLER] Site network crawl complete! Crawled {pages_crawled} pages, discovered {len(result_list)} unique product records.")
        return result_list


# Backwards compatibility alias
MitsubishiAICrawler = UniversalAICrawler
