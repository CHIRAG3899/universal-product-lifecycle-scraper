"""
AI Crawler Engine using Crawl4AI and intelligent Next.js / DOM parsing.
Universal, multi-vendor support for industrial lifecycle portals.
"""

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

from scraper.config import HEADLESS_BROWSER, REQUEST_TIMEOUT_SEC, USER_AGENT
from scraper.gemini_extractor import GeminiExtractor
from scraper.models import ProductRecord
from scraper.security import is_safe_url
from scraper.vendors import detect_vendor_from_url_or_text

logger = logging.getLogger("ai_scraper.crawler")


class UniversalAICrawler:
    """
    Universal AI Crawler coordinating Crawl4AI headless browser runs,
    DOM/Apollo cache extraction, and Google Gemini AI multi-vendor processing.
    """

    def __init__(self, gemini_extractor: Optional[GeminiExtractor] = None):
        self.gemini = gemini_extractor or GeminiExtractor()
        self._pdf_replacement_cache: Dict[str, Dict[str, str]] = {}

    def extract_replacement_map_from_pdf_url(self, pdf_url: str) -> Dict[str, str]:
        """
        Extracts discontinued model -> replacement model pairs from a manufacturer PDF bulletin.
        Caches results in memory to avoid redundant network downloads.
        """
        if not pdf_url:
            return {}
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
            return pairs

        try:
            resp = requests.get(pdf_url, timeout=12, headers={"User-Agent": USER_AGENT})
            if resp.status_code == 200 and resp.content:
                reader = pypdf.PdfReader(io.BytesIO(resp.content))
                text = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
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
        """
        logger.info(f"Initiating Crawl4AI crawl on: {target_url}")
        page_timeout = int(REQUEST_TIMEOUT_SEC * 1000)
        
        browser_config = BrowserConfig(
            headless=HEADLESS_BROWSER,
            verbose=False,
            user_agent=USER_AGENT
        )

        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            word_count_threshold=10,
            page_timeout=page_timeout,
            wait_until="domcontentloaded",
            delay_before_return_html=0.5,
            remove_overlay_elements=False,
            remove_consent_popups=False,
            excluded_tags=['nav', 'footer', 'header', 'script', 'style', 'noscript', 'aside'],
            excluded_selector='#onetrust-consent-sdk, .onetrust-pc-dark-filter, #onetrust-banner-sdk, .cookie-notice, footer, header, nav, .site-footer, .global-header, .ot-sdk-container, .cookie-banner, .ot-floating-button'
        )

        try:
            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url=target_url, config=run_config)
                
                if not result.success:
                    logger.warning(f"Crawl4AI failed to fetch {target_url}: {result.error_message}. Attempting resilient HTTP fallback...")
                    fallback_data = self.fetch_http_fallback(target_url)
                    if fallback_data.get("status_code", 500) < 400 and fallback_data.get("markdown"):
                        return fallback_data
                    raise RuntimeError(f"Crawl4AI failed to fetch {target_url}: {result.error_message}")

                if result.status_code and result.status_code >= 400:
                    logger.warning(f"URL {target_url} returned HTTP {result.status_code}. Skipping non-200 page.")
                    return {
                        "url": target_url,
                        "markdown": "",
                        "html": "",
                        "status_code": result.status_code,
                        "extracted_content": None
                    }

                logger.info(f"Crawl4AI succeeded! Extracted {len(result.markdown)} characters of clean markdown.")
                return {
                    "url": target_url,
                    "markdown": result.markdown,
                    "html": result.html,
                    "status_code": result.status_code,
                    "extracted_content": getattr(result, "extracted_content", None)
                }
        except Exception as e:
            if not isinstance(e, RuntimeError):
                logger.warning(f"Crawl4AI exception on {target_url}: {e}. Attempting resilient HTTP fallback...")
                fallback_data = self.fetch_http_fallback(target_url)
                if fallback_data.get("status_code", 500) < 400 and fallback_data.get("markdown"):
                    return fallback_data
            raise

    def fetch_http_fallback(self, target_url: str) -> Dict[str, Any]:
        """
        Lightweight, resilient HTTP fallback using urllib with realistic Chrome headers
        for sites that block headless browsers or when Chromium is unavailable.
        """
        try:
            req = urllib.request.Request(
                target_url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                }
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                status = resp.status
                raw_bytes = resp.read()
                import gzip
                if resp.headers.get("Content-Encoding") == "gzip":
                    try:
                        raw_bytes = gzip.decompress(raw_bytes)
                    except Exception:
                        pass
                html_text = raw_bytes.decode("utf-8", errors="replace")

                # Basic clean text conversion via BeautifulSoup
                soup = BeautifulSoup(html_text, "html.parser")
                for s in soup(["script", "style", "nav", "footer", "header"]):
                    s.decompose()
                text = soup.get_text(separator="\n", strip=True)

                logger.info(f"Resilient HTTP fallback succeeded for {target_url} ({len(html_text)} bytes).")
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
        """Converts extracted Apollo tables into structured markdown blocks optimal for Gemini."""
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

    async def run(self, target_url: str, chunk_size: int = 15) -> List[ProductRecord]:
        """
        Coordinates full crawl, markdown processing, and Gemini AI multi-vendor extraction.
        """
        vendor = detect_vendor_from_url_or_text(target_url)
        logger.info(f"Detected target vendor: {vendor} from URL: {target_url}")

        # 1. Crawl via Crawl4AI
        crawl_data = await self.crawl_with_crawl4ai(target_url)
        markdown = crawl_data.get("markdown", "")
        html = crawl_data.get("html", "")
        status_code = crawl_data.get("status_code", 200)

        if (status_code and status_code >= 400) or not markdown:
            logger.warning(f"URL {target_url} returned HTTP {status_code} with no usable content. Skipping.")
            return []

        all_products: List[ProductRecord] = []

        # Check if Crawl4AI LLMExtractionStrategy already extracted structured products directly
        extracted_content = crawl_data.get("extracted_content")
        if extracted_content:
            try:
                items = json.loads(extracted_content)
                if isinstance(items, list):
                    for it in items:
                        try:
                            rec = ProductRecord.model_validate(it)
                            all_products.append(rec)
                        except Exception:
                            pass
                    if all_products:
                        logger.info(f"Loaded {len(all_products)} products directly from Crawl4AI LLMExtractionStrategy.")
            except Exception as e:
                logger.debug(f"Could not parse Crawl4AI extracted_content: {e}")

        # 2. Extract structured Apollo tables from DOM or universal HTML tables if present
        apollo_tables = self.extract_apollo_state_tables(html)
        dom_tables = apollo_tables if apollo_tables else self.extract_dom_tables(html)

        if dom_tables:
            table_blocks = self.apollo_tables_to_markdown_blocks(dom_tables)
            print(f"  -> Discovered {len(table_blocks)} structured lifecycle tables. Processing with Gemini AI...")
            logger.info(f"Processing {len(table_blocks)} product lifecycle tables with Gemini AI...")

            if getattr(self.gemini, "batch_mode", False) and self.gemini.is_configured() and len(table_blocks) > chunk_size:
                logger.info(f"Using Gemini Batch API (50% token discount) across {len(table_blocks)} tables...")
                batch_chunks = [
                    {
                        "markdown_chunk": "\n\n---\n\n".join(table_blocks[i:i + chunk_size]),
                        "context": f"{vendor} Lifecycle EOL - Section {i//chunk_size + 1}",
                        "source_url": target_url
                    }
                    for i in range(0, len(table_blocks), chunk_size)
                ]
                extracted = self.gemini.extract_batch(batch_chunks)
                all_products.extend(extracted)
            else:
                for i in range(0, len(table_blocks), chunk_size):
                    chunk_text = "\n\n---\n\n".join(table_blocks[i:i + chunk_size])
                    extracted = self.gemini.extract_from_markdown(
                        markdown_chunk=chunk_text,
                        context=f"{vendor} Lifecycle EOL - Section {i//chunk_size + 1}",
                        source_url=target_url
                    )
                    all_products.extend(extracted)

        # 3. Process crawled body markdown (essential when no tables present or to capture unlisted items)
        if markdown and (not dom_tables or len(all_products) == 0):
            lines = markdown.split("\n")
            step = 800
            md_chunks = []
            for i in range(0, len(lines), step):
                chunk_md = "\n".join(lines[i:i + step])
                if len(chunk_md.strip()) >= 50:
                    md_chunks.append({
                        "markdown_chunk": chunk_md,
                        "context": f"{vendor} Discontinued Products Catalog - Section {i//step + 1}",
                        "source_url": target_url
                    })

            if getattr(self.gemini, "batch_mode", False) and self.gemini.is_configured() and len(md_chunks) > 1:
                logger.info(f"Using Gemini Batch API across {len(md_chunks)} markdown chunks...")
                extracted = self.gemini.extract_batch(md_chunks)
                all_products.extend(extracted)
            else:
                max_chunks = getattr(self, "max_markdown_chunks", 0)
                if max_chunks and max_chunks > 0 and len(md_chunks) > max_chunks:
                    logger.warning(
                        f"Markdown catalog exceeds {max_chunks} chunks ({len(md_chunks)} found). "
                        f"Processing first {max_chunks} chunks. Use --batch-mode for unlimited processing."
                    )
                    chunks_to_process = md_chunks[:max_chunks]
                else:
                    chunks_to_process = md_chunks
                for item in chunks_to_process:
                    extracted = self.gemini.extract_from_markdown(
                        markdown_chunk=item["markdown_chunk"],
                        context=item["context"],
                        source_url=item["source_url"]
                    )
                    all_products.extend(extracted)

        # 4. Deep Document Notice Inspection: Check for linked PDF lifecycle bulletins
        if html:
            try:
                soup = BeautifulSoup(html, "html.parser")
                pdf_links = []
                bulletin_kw = re.compile(r'(?:eol|ltb|eos|bulletin|notice|discontinu|obsolesc|abk[uü]ndigung)', re.IGNORECASE)
                for a in soup.find_all("a", href=True):
                    href = str(a.get("href") or "").strip()
                    if ".pdf" in href.lower():
                        resolved_pdf = urllib.parse.urljoin(target_url, href)
                        if is_safe_url(resolved_pdf):
                            link_text = a.get_text(strip=True)
                            if bulletin_kw.search(resolved_pdf) or bulletin_kw.search(link_text):
                                if resolved_pdf not in pdf_links:
                                    pdf_links.append(resolved_pdf)

                # Ingest PDF notices: prioritize if table yielded no records, or check top 2 bulletins
                max_pdfs = 2 if len(all_products) > 0 else 5
                for pdf_url in pdf_links[:max_pdfs]:
                    print(f"  -> Ingesting lifecycle bulletin PDF: {pdf_url.split('/')[-1]}")
                    try:
                        pdf_products = self.gemini.extract_from_pdf_url(pdf_url, default_vendor=vendor)
                        all_products.extend(pdf_products)
                    except Exception as pdf_err:
                        logger.debug(f"Could not parse bulletin PDF {pdf_url}: {pdf_err}")
            except Exception as soup_err:
                logger.debug(f"Could not inspect HTML for PDF bulletins: {soup_err}")

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
                # If existing has no replacement but new record has one, copy it
                if not existing.replacement and p.replacement:
                    existing.replacement = p.replacement
                    if "replacement" in existing.metadata:
                        existing.metadata["replacement"] = p.replacement
                # Prefer the record that has a populated UTC date
                if not existing.stage_date_utc and p.stage_date_utc:
                    unique_records[key] = p

        final_list = list(unique_records.values())
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
            r'(?:lifecycle|eol|ltb|eos|discontinu|obsolesc|phase-out|bulletin|product|catalog|hardware|device|item|support|notice|archive|download)',
            re.IGNORECASE
        )

        for sm_url in sitemap_urls_to_fetch[:3]:
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
                                    if child_sm not in sitemap_urls_to_fetch and len(sitemap_urls_to_fetch) < 6:
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
        enable_sitemap: bool = True
    ) -> List[ProductRecord]:
        """
        Deep crawls a vendor website network map:
        1. Probes XML sitemaps and robots.txt to map site architecture without product category restrictions.
        2. Discovers priority lifecycle & EOL notices alongside comprehensive product catalog hubs.
        3. Recursively traverses internal category trees and pagination links via BFS queue (up to max_depth; 0 = unlimited).
        4. Filters links strictly within allowed_domains (SSRF boundary guard).
        5. Crawls discovered sub-portals up to max_pages (0 = unlimited full site crawl) and extracts structured products.
        """
        pages_limit_str = "Unlimited" if not max_pages or max_pages <= 0 else str(max_pages)
        depth_limit_str = "Unlimited" if not max_depth or max_depth <= 0 else str(max_depth)
        logger.info(f"[CRAWLER] Initiating site-level crawl on domain: {base_url} (Max pages: {pages_limit_str}, Max depth: {depth_limit_str})")

        # Broad discovery keyword patterns:
        # Priority 1: Direct lifecycle, EOL, obsolescence, bulletins
        lifecycle_keywords = re.compile(
            r'(?:lifecycle|life-cycle|eol|ltb|eos|discontinu|obsolescen|phase-out|bulletin|product-status|support|abk[uü]ndigung|生産終了)',
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
            clean_url = url.split("#")[0].strip()
            if not clean_url:
                return
            try:
                parsed = urllib.parse.urlsplit(clean_url)
                netloc = parsed.netloc.lower()
                scheme = parsed.scheme.lower()
                path = parsed.path
                if path.endswith("/") and path.count("/") > 1:
                    path = path.rstrip("/")
                clean_url = urllib.parse.urlunsplit((scheme, netloc, path, parsed.query, ""))
            except Exception:
                pass

            if clean_url in visited_urls or clean_url in queued_urls:
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
        pages_crawled = 0

        while queue and (not max_pages or max_pages <= 0 or pages_crawled < max_pages):
            u, current_depth, pri = queue.pop(0)
            if u in visited_urls:
                continue
            visited_urls.add(u)
            pages_crawled += 1

            page_label = f"{pages_crawled}/{pages_limit_str}"
            logger.info(f"[CRAWLER] Crawling network map portal ({page_label}, depth={current_depth}): {u}")
            try:
                page_products = await self.run(u)
                all_products.extend(page_products)
            except Exception as pe:
                logger.warning(f"Error crawling portal {u}: {pe}")

            # If depth allowed and queue budget allows, recursively discover links
            depth_allowed = (not max_depth or max_depth <= 0 or current_depth < max_depth)
            queue_budget_allowed = (not max_pages or max_pages <= 0 or len(queue) < max_pages * 2)
            if depth_allowed and queue_budget_allowed:
                try:
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
