"""
DOM Table Scraping Strategy.

Parses structured HTML and client-side rendered DOM tables across enterprise
lifecycle hubs (e.g. Cisco EOL listing, Meraki, Juniper, SonicWall, Fortinet,
Honeywell Productivity, Teltonika MediaWiki tables).
Supports column index or header mapping, quote sanitization, and state journaling.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from dateutil import parser as date_parser

from scraper.config import HEADLESS_BROWSER
from scraper.dlq import DeadLetterQueue
from scraper.models import ProductRecord, is_valid_product_model
from scraper.security import validate_safe_css_selector
from scraper.state import VendorRunState
from scraper.strategies.base import (
    BaseScrapingStrategy,
    is_likely_date_str,
    sanitize_alias_text,
    split_model_identifiers,
)

logger = logging.getLogger("ai_scraper.strategies.dom_table")


class DomTableStrategy(BaseScrapingStrategy):
    """
    Generic Strategy for DOM & HTML Tabular Lifecycle Pages:
    1. Fetches target URL using Crawl4AI (with optional JS wait_for).
    2. Identifies table structures and maps columns (by selector, header name, or column index).
    3. Iterates over rows, creating sanitized ProductRecord instances.
    4. Automatically records progress in VendorRunState and avoids duplicate models.
    """

    @staticmethod
    def _parse_pdf_discontinued_table(pdf_url: str) -> List[Tuple[str, Optional[str]]]:
        """Downloads and extracts discontinued models and replacements from an EOL notice PDF."""
        try:
            import io
            import urllib.request

            import pypdf

            req = urllib.request.Request(
                pdf_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            reader = pypdf.PdfReader(io.BytesIO(data))
            text = ""
            for p in reader.pages:
                text += "\n" + (p.extract_text() or "")
            lines = text.splitlines()
            records: List[Tuple[str, Optional[str]]] = []
            in_table = False
            for line in lines:
                line_s = line.strip()
                if any(k in line_s for k in ("Materials to be discontinued", "Material Description")):
                    in_table = True
                    continue
                if any(k in line_s for k in ("Phase Out Schedule", "Additional Information", "Customer Action", "Total number of materials")):
                    in_table = False
                    continue
                if in_table and line_s:
                    mats = re.findall(r"\b([A-Z0-9]{2,12}\s*[-_][A-Z0-9\-_/]+|[A-Z]{2,5}[0-9]{2,8}[A-Z0-9\-_]*)\b", line_s)
                    if mats:
                        discont_m = mats[0].replace(" ", "")
                        repl_m = mats[1].replace(" ", "") if len(mats) > 1 and not mats[1].isdigit() else None
                        records.append((discont_m, repl_m))
            return records
        except Exception as e:
            logger.debug(f"Failed to parse PDF table from {pdf_url}: {e}")
            return []

    def _parse_direct_pdf_bulletin(
        self,
        pdf_url: str,
        vendor_name: str,
        category_name: str,
        state: VendorRunState,
    ) -> List[ProductRecord]:
        """
        Downloads and parses structured product bulletins in PDF format (e.g. Emerson Fisher Discontinued Products Bulletin).
        Extracts discontinued / limited availability hardware models, replacement recommendations, and milestone dates.
        """
        records: List[ProductRecord] = []
        try:
            import io
            import urllib.request

            import pypdf

            req = urllib.request.Request(
                pdf_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = resp.read()

            reader = pypdf.PdfReader(io.BytesIO(data))
            current_status = "Discontinued"
            in_concerned_products_sec = False
            concerned_models: List[str] = []
            statement_status: Optional[str] = None
            statement_date: Optional[str] = None

            # First pass: check for statement-based sections (e.g. ABB Product types concerned)
            all_text_lines: List[str] = []
            for p in reader.pages:
                txt = p.extract_text() or ""
                all_text_lines.extend(txt.splitlines())

            for line in all_text_lines:
                line_s = line.strip()
                line_low = line_s.lower()

                # Filter footers / metadata
                if any(k in line_low for k in (
                    "document id", "security level", "external en", "all rights reserved",
                    "copyright", "lang page", "rev date"
                )):
                    continue

                if "product types concerned" in line_low or "concerned products" in line_low:
                    in_concerned_products_sec = True
                    continue
                elif in_concerned_products_sec and any(
                    k in line_low for k in ("current life cycle status", "life cycle plan", "product availability", "recommended actions")
                ):
                    in_concerned_products_sec = False

                if in_concerned_products_sec and line_s:
                    if not line_s.startswith("*") and not line_s.lower().startswith("note:"):
                        # Unbundle slashed models e.g. ACS550-01/-02 -> ACS550-01, ACS550-02
                        parts = line_s.split("/")
                        if len(parts) > 1:
                            base = parts[0].strip()
                            m = re.match(r'^(.*?)(\-?[A-Za-z0-9]+)$', base)
                            if m:
                                prefix = m.group(1)
                                concerned_models.append(base)
                                for sub in parts[1:]:
                                    sub_c = sub.strip(" -/")
                                    if sub_c:
                                        new_m = f"{prefix}{sub_c}" if prefix.endswith("-") else f"{prefix}-{sub_c}"
                                        concerned_models.append(new_m)
                        else:
                            clean_tok = line_s.strip()
                            if is_valid_product_model(clean_tok):
                                concerned_models.append(clean_tok)

                if "limited life cycle phase" in line_low or "limited phase" in line_low:
                    statement_status = "Limited"
                    m_dt = re.search(r'since\s+(\d{1,2}\.\d{1,2}\.\d{4}|\d{4})', line_s, re.I)
                    if m_dt:
                        try:
                            from dateutil import parser as dt_p
                            parsed_dt = dt_p.parse(m_dt.group(1), fuzzy=True)
                            statement_date = parsed_dt.strftime("%Y-%m-%d") + "T00:00:00Z"
                        except Exception:
                            pass
                elif "obsolete phase" in line_low or "transferred to the obsolete" in line_low:
                    if not statement_status:
                        statement_status = "Obsolete"

            if concerned_models:
                eff_status = statement_status or "Discontinued"
                for cm in list(dict.fromkeys(concerned_models)):
                    if is_valid_product_model(cm) and not state.is_model_seen(cm):
                        rec = self.create_sanitized_record(
                            vendor_name=vendor_name,
                            raw_model=cm,
                            raw_alias=None,
                            raw_status=eff_status,
                            raw_date=statement_date,
                            source_url=pdf_url,
                            category=category_name,
                            raw_replacement=None,
                        )
                        if rec:
                            records.append(rec)
                            state.record_model(rec.model_name)

            # Second pass: Table-based bulletins (e.g. Emerson Fisher Discontinued Products Bulletin)
            for page in reader.pages[1:]:
                text = page.extract_text() or ""
                for line in text.splitlines():
                    line_s = line.strip()
                    line_low = line_s.lower()

                    # Skip footers / metadata
                    if any(k in line_low for k in (
                        "document id", "security level", "external en", "all rights reserved",
                        "copyright", "lang page", "rev date"
                    )):
                        continue

                    if "Table 1. Limited" in line_s:
                        current_status = "Limited Availability"
                        continue
                    elif "Table 2. Discontinued" in line_s:
                        current_status = "Discontinued"
                        continue

                    # Skip headers / page numbers / footers
                    if not line_s or line_s.isdigit() or any(
                        h in line_s for h in [
                            "Discontinued Products Product Bulletin", "D104336X012",
                            "Product Description", "Fisher Product Description",
                            "Restrictions on Use", "Recommended Replacement"
                        ]
                    ):
                        continue

                    parts = re.split(r'\s{2,}|\t+', line_s)
                    if len(parts) >= 2:
                        raw_m, raw_rem = parts[0], " ".join(parts[1:])
                    else:
                        m_first = re.match(r'^([A-Za-z0-9\-_/\s,]+?)\s{2,}(.*)$', line_s)
                        if not m_first:
                            m_first = re.match(r'^([A-Z0-9]{2,15}(?:,\s*[A-Z0-9]{2,15})*|\d{3,4}(?:,\s*\d{3,4})*(?:\s+Series)?)\s+(.*)$', line_s)
                        if m_first:
                            raw_m, raw_rem = m_first.group(1), m_first.group(2)
                        else:
                            continue

                    dt_str = None
                    m_yr = re.search(r'\b(19\d\d|20\d\d)\b', raw_rem)
                    if m_yr:
                        dt_str = f"{m_yr.group(1)}-01-01T00:00:00Z"

                    repl_str = None
                    m_repl = re.search(r'(?:Preferred Product|Recommended Replacement|Buyout|None|Direct replacement)[^:]*?([A-Za-z0-9\-_/,\s]+)$', raw_rem)
                    if m_repl and m_repl.group(1).strip().lower() not in ("none", "- - -"):
                        repl_candidate = m_repl.group(1).strip()
                        if not any(k in repl_candidate.lower() for k in ("nuclear", "only", "after application")):
                            repl_str = repl_candidate

                    # Clean model part
                    m_clean = re.sub(r'\s+Series\b', '', raw_m, flags=re.I).strip()
                    sub_items = [m.strip() for m in re.split(r'[,;]+', m_clean) if m.strip()]
                    for item in sub_items:
                        # Extract model token and potential description
                        m_match = re.match(r'^([A-Za-z0-9\-_/]+)\s*(.*?)$', item)
                        if not m_match:
                            continue
                        mod_name, mod_desc = m_match.group(1), m_match.group(2).strip()
                        if len(mod_name) < 2 or len(mod_name) > 30:
                            continue
                        if any(k in mod_name.lower() for k in ("table", "page", "date", "valve", "actuator", "product", "bulletin", "discontinued", "limited")):
                            continue

                        alias_text = mod_desc if mod_desc else raw_rem[:60].strip()
                        if alias_text in ("- - -", "None", ""):
                            alias_text = None

                        if is_valid_product_model(mod_name) and not state.is_model_seen(mod_name):
                            rec = self.create_sanitized_record(
                                vendor_name=vendor_name,
                                raw_model=mod_name,
                                raw_alias=alias_text,
                                raw_status=current_status,
                                raw_date=dt_str,
                                source_url=pdf_url,
                                category=category_name,
                                raw_replacement=repl_str,
                            )
                            if rec:
                                records.append(rec)
                                state.record_model(rec.model_name)

            logger.info(f"[DOM TABLE PDF] Successfully parsed {len(records)} records from {pdf_url}")
        except Exception as pdf_err:
            logger.warning(f"[DOM TABLE PDF] Failed to parse PDF bulletin {pdf_url}: {pdf_err}")

        return records

    async def execute(
        self,
        entry_point: Dict[str, Any],
        vendor_cfg: Dict[str, Any],
        crawler: Any,
        state: VendorRunState,
        dlq: Optional[DeadLetterQueue] = None,
        max_pages: int = 0,
        batch_size: Optional[int] = None,
        all_batches: bool = False,
    ) -> List[ProductRecord]:
        vendor_name = vendor_cfg.get("name", "Unknown Vendor")
        vendor_id = vendor_cfg.get("id", "vendor")
        url = str(entry_point.get("url", "")).strip()
        if not url:
            return []

        # Only skip if the unit was previously completed with authentic records extracted
        kb_meta = state.knowledge_base.get(url.strip().lower(), {})
        prev_records = kb_meta.get("records_count", 0)
        if state.is_unit_completed(url) and prev_records > 0:
            logger.info(f"[DOM TABLE] Skipping previously completed entry point ({prev_records} records harvested): {url}")
            return []

        category_name = entry_point.get("category", vendor_cfg.get("sector", "IT"))
        crawler_mode = str(entry_point.get("crawler_mode", "auto")).lower()

        # Handle direct PDF bulletins natively (e.g. Emerson Discontinued Products Bulletin)
        if url.lower().endswith(".pdf") or crawler_mode == "pdf":
            logger.info(f"[*] [DOM TABLE] Directly parsing manufacturer PDF bulletin: {url}")
            pdf_records = self._parse_direct_pdf_bulletin(
                pdf_url=url,
                vendor_name=vendor_name,
                category_name=category_name,
                state=state
            )
            return pdf_records

        selectors = entry_point.get("selectors", {})
        table_selector = selectors.get("table", "table")
        if not validate_safe_css_selector(table_selector):
            table_selector = "table"
        row_selector = selectors.get("row", "tr")
        if not validate_safe_css_selector(row_selector):
            row_selector = "tr"
        wait_selector = selectors.get("wait_for")
        if wait_selector and not validate_safe_css_selector(wait_selector):
            wait_selector = None
        col_map = entry_point.get("columns", {})

        browser_cfg = BrowserConfig(headless=HEADLESS_BROWSER, verbose=False, user_agent_mode="random")
        run_cfg = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            magic=True,
            simulate_user=True,
            wait_for=f"css:{wait_selector}" if wait_selector and not wait_selector.startswith("css:") else (wait_selector or "css:body"),
            page_timeout=30000,
            wait_for_timeout=10000 if wait_selector else 4000,
            delay_before_return_html=3.5,
        )

        records: List[ProductRecord] = []
        consecutive_errors = 0

        html: Optional[str] = None
        crawler_mode = str(entry_point.get("crawler_mode", "auto")).lower()

        # 1. Fast direct HTTP fetch if configured
        if crawler_mode == "http":
            try:
                import urllib.request
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    html = resp.read().decode("utf-8", errors="replace")
            except Exception as http_err:
                logger.warning(f"  [!] Direct HTTP fetch failed for {url}: {http_err}")

        # 2. Headless Chromium via Crawl4AI
        if not html:
            try:
                logger.info(f"[*] [DOM TABLE] Fetching lifecycle table from {url}")
                async with AsyncWebCrawler(config=browser_cfg) as web_crawler:
                    res = await web_crawler.arun(url=url, config=run_cfg)
                    if res.success and res.html:
                        html = res.html
                    else:
                        logger.warning(f"  [!] AsyncWebCrawler fetch returned empty/failed: {res.error_message}")
            except Exception as crawl_err:
                logger.warning(f"  [!] AsyncWebCrawler exception for {url}: {crawl_err}")

        # 3. Resilient HTTP fallback if browser failed or timed out
        if not html:
            try:
                logger.info(f"[*] [DOM TABLE] Attempting resilient HTTP fallback for {url}")
                import urllib.request
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    html = resp.read().decode("utf-8", errors="replace")
            except Exception as fb_err:
                logger.warning(f"  [!] Resilient HTTP fallback failed for {url}: {fb_err}")

        if not html:
            consecutive_errors += 1
            if dlq:
                dlq.record_failure(
                    url=url,
                    vendor_id=vendor_id,
                    error_type="FetchFailed",
                    message="Failed to fetch HTML via both headless browser and HTTP fallback",
                )
            return []

        try:
            soup = BeautifulSoup(html, "html.parser")

            # Check if entry point specifies item-level list selector (e.g. li, div cards)
            item_selector = selectors.get("item") or selectors.get("item_selector")
            if item_selector:
                items = soup.select(item_selector)
                for it in items:
                    # Check for rich accordion / labeled sections inside item (e.g. Omron Robotics)
                    sec_divs = it.find_all("div", class_=lambda c: c and "flex" in c and "col" in c)
                    if sec_divs:
                        sec_map = {}
                        pdf_url = None
                        for d in sec_divs:
                            txt = d.get_text("\n", strip=True)
                            lines = [line.strip() for line in txt.splitlines() if line.strip()]
                            if len(lines) >= 2:
                                lbl = lines[0].lower()
                                sec_map[lbl] = lines[1:]
                            pdf_a = d.find("a", href=lambda h: h and ".pdf" in h.lower())
                            if pdf_a and not pdf_url:
                                pdf_url = pdf_a.get("href")

                        prod_name = sec_map.get("product name", [""])[0]
                        raw_models = sec_map.get("models", [])
                        if not raw_models and prod_name:
                            raw_models = [prod_name]

                        # Filter label noise from models
                        sub_models = []
                        for m in raw_models:
                            if any(kw in m.lower() for kw in ("last order", "last shipment", "support end", "replacement", "resources", "eol", "ordered")):
                                continue
                            if is_likely_date_str(m):
                                continue
                            sub_models.append(m)

                        repl_list = sec_map.get("replacement", [])
                        card_repl = repl_list[0] if repl_list else None
                        support_end = sec_map.get("support end", [None])[0]
                        last_order = sec_map.get("last order date", [None])[0]

                        card_href = pdf_url or url
                        if str(card_href).startswith("/"):
                            from urllib.parse import urljoin
                            card_href = urljoin(url, str(card_href))

                        for single_m in sub_models:
                            if not is_valid_product_model(single_m):
                                continue
                            if support_end:
                                rec_eos = self.create_sanitized_record(
                                    vendor_name=vendor_name,
                                    raw_model=single_m,
                                    raw_alias=prod_name if prod_name != single_m else None,
                                    raw_status="End of Support",
                                    raw_date=support_end,
                                    source_url=str(card_href),
                                    category=category_name,
                                    raw_replacement=card_repl,
                                    extra_meta={"source": "dom_accordion", "entry_point": entry_point.get("name")},
                                )
                                if rec_eos:
                                    records.append(rec_eos)
                                    state.record_model(rec_eos.model_name)
                            if last_order:
                                rec_ltb = self.create_sanitized_record(
                                    vendor_name=vendor_name,
                                    raw_model=single_m,
                                    raw_alias=prod_name if prod_name != single_m else None,
                                    raw_status="End of Sale (EOS)",
                                    raw_date=last_order,
                                    source_url=str(card_href),
                                    category=category_name,
                                    raw_replacement=card_repl,
                                    extra_meta={"source": "dom_accordion", "entry_point": entry_point.get("name")},
                                )
                                if rec_ltb:
                                    records.append(rec_ltb)
                                    state.record_model(rec_ltb.model_name)
                        continue

                    model_sel = selectors.get("model")
                    if model_sel:
                        m_el = it.select_one(model_sel) or (it if it.name == model_sel else None)
                    else:
                        m_el = it.select_one("a") or it
                    if not m_el:
                        continue

                    status_sel = selectors.get("status")
                    s_el = it.select_one(status_sel) if status_sel else None
                    raw_status = str((s_el.get_text(strip=True) or s_el.get("title", "") if s_el else "") or selectors.get("default_status", "Active"))

                    rep_sel = selectors.get("replacement")
                    r_el = it.select_one(rep_sel) if rep_sel else None
                    raw_rep = r_el.get_text(strip=True) if r_el else None

                    # Remove child elements from m_el to prevent model name contamination
                    if s_el and s_el != m_el:
                        try:
                            s_el.extract()
                        except Exception:
                            pass
                    if r_el and r_el != m_el:
                        try:
                            r_el.extract()
                        except Exception:
                            pass

                    # Decompose screen-reader labels or commercial status spans inside m_el
                    for vh in m_el.find_all(class_=lambda c: c and any(k in str(c).lower() for k in ("visually-hidden", "sr-only", "commercial-status"))):
                        try:
                            vh.decompose()
                        except Exception:
                            pass

                    raw_m = m_el.get_text(strip=True)
                    if not raw_m:
                        continue

                    # Sanitize boilerplate status phrases, trademark glyphs, zero-width spaces, and quotes
                    raw_m = re.sub(r'\s*Denotes\s+(?:legacy|new|product)\s+.*$', '', raw_m, flags=re.I).strip()
                    raw_m = re.sub(r'[\u2122\u00ae\u00a9\u200b\ufeff]', '', raw_m)
                    raw_m = raw_m.replace('\u2013', '-').replace('\u2014', '-').replace('"', '').replace("'", "")
                    raw_m = re.sub(r'\s+', ' ', raw_m).strip()

                    # Reject non-product service agreements and warranty plans
                    if any(sp in raw_m.lower() for sp in ("service plan", "warranty", "service agreement", "maintenance agreement")):
                        continue

                    href = m_el.get("href") or it.get("href") or url
                    if str(href).startswith("/"):
                        from urllib.parse import urljoin
                        href = urljoin(url, str(href))

                    if "|" in raw_m:
                        parts = [p.strip() for p in raw_m.split("|") if p.strip()]
                        m_prefix = re.match(r"^([A-Za-z0-9_\-\s]+?\s+)(?=[A-Za-z0-9_\-]+$)", parts[0])
                        prefix_str = m_prefix.group(1) if m_prefix else ""
                        sub_models = []
                        for idx, p in enumerate(parts):
                            if idx > 0 and prefix_str and not p.lower().startswith(prefix_str.strip().lower()):
                                sub_models.append(f"{prefix_str}{p}")
                            else:
                                sub_models.append(p)
                    else:
                        sub_models = [raw_m]

                    for single_m in sub_models:
                        if not single_m or not is_valid_product_model(single_m):
                            continue
                        rec = self.create_sanitized_record(
                            vendor_name=vendor_name,
                            raw_model=single_m,
                            raw_alias=None,
                            raw_status=raw_status,
                            raw_date=None,
                            source_url=str(href),
                            category=category_name,
                            raw_replacement=raw_rep,
                            extra_meta={"source": "dom_item_list", "entry_point": entry_point.get("name")},
                        )
                        if rec:
                            records.append(rec)
                            state.record_model(rec.model_name)

                state.mark_unit_completed(url)
                return records

            tables: List[Any] = list(soup.select(table_selector))
            if not tables:
                tables = [soup]

            page_milestones: List[Dict[str, Any]] = []

            for table in tables:
                rows = table.select(row_selector)
                if not rows:
                    continue

                # 1. Discover column indexes dynamically from <th> header row if available
                auto_m_idx: Optional[int] = None
                auto_a_idx: Optional[int] = None
                auto_r_idx: Optional[int] = None
                auto_s_idx: Optional[int] = None
                auto_announcement_idx: Optional[int] = None
                auto_bulletin_idx: Optional[int] = None
                auto_milestones: List[Dict[str, Any]] = []

                th_cells = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]

                # Check if this table is a page-level Milestone Definition table (e.g. Milestone, Definition, Date)
                is_milestone_table = (
                    any("milestone" in h or "definition" in h for h in th_cells)
                    and not any(any(k in h for k in ("part number", "sku", "model", "catalog", "pid")) for h in th_cells)
                )
                if is_milestone_table:
                    for r in rows:
                        m_cells = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
                        if len(m_cells) >= 2:
                            ms_name = m_cells[0].lower()
                            ms_date = m_cells[-1]
                            if any(k in ms_name for k in ("end of sale", "end-of-sale", "last order", "last time buy", "end of life", "eol")):
                                page_milestones.append({"status": "End of Sale (EOS)", "date": ms_date})
                            elif any(k in ms_name for k in ("app. sw", "application sw", "app sw", "sw support")):
                                page_milestones.append({"status": "End of SW Support", "date": ms_date})
                            elif any(k in ms_name for k in ("last date of support", "end of support", "end-of-support", "end of service")):
                                page_milestones.append({"status": "End of Support", "date": ms_date})
                            elif any(k in ms_name for k in ("sw maintenance", "engineering")):
                                page_milestones.append({"status": "End of Engineering", "date": ms_date})
                    # Skip parsing this table as product models
                    continue

                # Pattern A: Multi-row Discontinuation Notice Table (e.g. Mitsubishi An, AnS, QnA, F1, FX series)
                has_discont_notice = any(
                    "production discontinuation in" in r.get_text().lower() or "discontinuation in" in r.get_text().lower()
                    for r in rows
                )
                if has_discont_notice:
                    for dr in rows:
                        d_cells = [c.get_text(" ", strip=True) for c in dr.find_all(["td", "th"])]
                        if len(d_cells) >= 2:
                            c0, c1 = d_cells[0], d_cells[1]
                            m_date = re.search(r'discontinuation\s+in\s+([A-Za-z]+\s+\d{4})', c0, re.I)
                            dt_str = None
                            if m_date:
                                try:
                                    dt = date_parser.parse(m_date.group(1), default=datetime(2000, 1, 1))
                                    dt_str = dt.strftime("%Y-%m-%d") + "T00:00:00Z"
                                except Exception:
                                    pass
                            ser_raw = c0.split("-")[0].strip()
                            if not ser_raw:
                                ser_raw = c0.split(",")[0].strip()
                            ser_name = ser_raw if "series" in ser_raw.lower() else f"{ser_raw} Series"

                            clean_c1 = re.sub(r'Example of Main units\s*(?:\([^)]*\))?:?', '', c1, flags=re.I)
                            clean_c1 = re.sub(r'(?:Expansion units|Modules|Expansion modules|Later discontiunued[^:]*):?', ',', clean_c1, flags=re.I)
                            raw_tokens = [t.strip() for t in re.split(r'[,;\s]+', clean_c1) if t.strip()]
                            disallowed_tokens = {"example", "of", "main", "units", "modules", "cpu", "cpus", "later", "discontinued", "expansion", "complete", "series", "and"}
                            for tok in raw_tokens:
                                tok_clean = tok.strip(".:,;()")
                                if len(tok_clean) >= 2 and tok_clean.lower() not in disallowed_tokens:
                                    if is_valid_product_model(tok_clean):
                                        rec = self.create_sanitized_record(
                                            vendor_name=vendor_name,
                                            raw_model=tok_clean,
                                            raw_alias=ser_name,
                                            raw_status="Discontinued",
                                            raw_date=dt_str,
                                            source_url=url,
                                            category=category_name,
                                        )
                                        if rec:
                                            records.append(rec)
                                            state.record_model(rec.model_name)
                    continue

                # Pattern B: Discontinued Inverter / Main series table (e.g. Mitsubishi Table 27)
                hdr_text_first = rows[0].get_text(" ", strip=True).lower()
                if "main series" in hdr_text_first and "example of main units" in hdr_text_first:
                    for dr in rows[1:]:
                        c_cells = [c.get_text(" ", strip=True) for c in dr.find_all(["td", "th"])]
                        if len(c_cells) >= 2:
                            ser_name = c_cells[0].strip()
                            raw_tokens = [t.strip() for t in re.split(r'[,;\n\r]+', c_cells[1]) if t.strip()]
                            for tok in raw_tokens:
                                tok_clean = re.sub(r'\s*\([^)]*\)', '', tok).strip().strip(".:,;()")
                                if len(tok_clean) >= 2 and len(tok_clean) <= 40 and is_valid_product_model(tok_clean):
                                    rec = self.create_sanitized_record(
                                        vendor_name=vendor_name,
                                        raw_model=tok_clean,
                                        raw_alias=ser_name,
                                        raw_status="Discontinued",
                                        raw_date=None,
                                        source_url=url,
                                        category=category_name,
                                    )
                                    if rec:
                                        records.append(rec)
                                        state.record_model(rec.model_name)
                    continue

                # Pattern C: Vertical Card Tables (Single or Multiple stacked cards)
                has_card_markers = any(
                    any(k in r.get_text().lower() for k in ("affects the following", "includes the following", "includes complete serie", "includes following", "includes:", "see pdf"))
                    for r in rows
                )
                if has_card_markers:
                    card_chunks: List[List[Any]] = []
                    current_card: List[Any] = []
                    for dr in rows:
                        card_cells = [c.get_text(" ", strip=True) for c in dr.find_all(["td", "th"])]
                        if len(card_cells) >= 2:
                            c1_low = card_cells[1].lower()
                            c0_low = card_cells[0].lower()
                            is_new_card = (
                                any(k in c1_low for k in ("affects the following", "includes the following", "includes complete serie", "includes following", "includes:", "see pdf"))
                                or ("series" in c0_low and not any(k in c0_low for k in ("end of life", "last time buy", "end of service", "document", "manual", "replacement")))
                                or (not current_card and not any(k in c0_low for k in ("end of life", "last time buy", "end of service", "document", "manual", "replacement")))
                            )
                            if is_new_card and current_card:
                                card_chunks.append(current_card)
                                current_card = []
                        current_card.append(dr)
                    if current_card:
                        card_chunks.append(current_card)

                    for chunk in card_chunks:
                        if not chunk:
                            continue
                        hdr_row = chunk[0]
                        hdr_cells = [c.get_text(" ", strip=True) for c in hdr_row.find_all(["td", "th"])]
                        if len(hdr_cells) < 2:
                            continue
                        raw_ser = hdr_cells[0].strip()
                        models_cell = hdr_cells[1].strip()

                        # Collect milestone dates and pdf links from data rows in this card
                        ms_pairs: List[Tuple[str, Optional[str]]] = []
                        pdf_urls: List[str] = []
                        for dr in chunk[1:]:
                            for a in dr.find_all("a"):
                                h = a.get("href")
                                if h and ".pdf" in h.lower():
                                    pdf_urls.append(h)
                            d_cells = [c.get_text(" ", strip=True) for c in dr.find_all(["td", "th"])]
                            if len(d_cells) >= 2:
                                d_name = d_cells[0].strip()
                                d_val = d_cells[1].strip()
                                d_low = d_name.lower()
                                if any(k in d_low for k in ("end of life", "eol", "last time buy", "ltb", "end of service", "eos", "discontinued", "obsolete", "phase-out")) and not any(k in d_low for k in ("document", "manual", "file", "guide", "download")):
                                    dt_parsed = None
                                    if is_likely_date_str(d_val):
                                        try:
                                            dt_obj = date_parser.parse(d_val, fuzzy=True)
                                            dt_parsed = dt_obj.strftime("%Y-%m-%d") + "T00:00:00Z"
                                        except Exception:
                                            pass
                                    ms_pairs.append((d_name, dt_parsed))
                        if not ms_pairs:
                            ms_pairs = [("Discontinued", None)]

                        # Clean series name to use as family/series alias (e.g. MELIPC series)
                        clean_ser = raw_ser
                        clean_ser = re.sub(r'\s*-\s*(?:Wireless LAN Communication unit|General-Purpose Inverters|DeviceNet Modules|Ethernet Modules|SD Memory Card).*', '', clean_ser, flags=re.I).strip()
                        clean_alias = clean_ser if clean_ser else None

                        # Check if models_cell points to PDF
                        if "see pdf" in models_cell.lower() and pdf_urls:
                            pdf_recs = self._parse_pdf_discontinued_table(pdf_urls[0])
                            for m_name, repl in pdf_recs:
                                if is_valid_product_model(m_name):
                                    for ms_name, ms_date in ms_pairs:
                                        rec = self.create_sanitized_record(
                                            vendor_name=vendor_name,
                                            raw_model=m_name,
                                            raw_alias=clean_alias,
                                            raw_status=ms_name,
                                            raw_date=ms_date,
                                            source_url=url,
                                            category=category_name,
                                            raw_replacement=repl,
                                        )
                                        if rec:
                                            records.append(rec)
                                            state.record_model(rec.model_name)
                        else:
                            # Clean and split models_cell
                            sub_txt = re.sub(r'^(?:affects the following models?:?|includes the following modules?:?|includes complete serie:?|includes following cpu\'?s?:?|includes following models?:?|includes:?)\s*', '', models_cell, flags=re.I)
                            parts = [p.strip() for p in re.split(r'[,;]|\band\b|&', sub_txt) if p.strip()]
                            valid_chunk_models: List[str] = []
                            for p in parts:
                                p_clean = re.sub(r'^(?:example of main units.*?:|includes complete serie:?|st1 complete series\s*-\s*)', '', p, flags=re.I).strip()
                                p_clean = p_clean.strip(".:,;()")
                                if len(p_clean) >= 2 and len(p_clean) <= 45 and not any(kw in p_clean.lower() for kw in ('following', 'affect', 'complete', 'pdf', 'description')):
                                    if is_valid_product_model(p_clean):
                                        valid_chunk_models.append(p_clean)

                            if not valid_chunk_models:
                                cand_root = re.sub(r'[\s\-]+(?:Complete\s+)?(?:Series|Serie)\b.*$', '', raw_ser, flags=re.I).strip()
                                cand_root = re.sub(r'\s*-\s*General-Purpose Inverters.*', '', cand_root, flags=re.I).strip()
                                candidate = f"{cand_root} Series" if cand_root and not cand_root.lower().endswith("series") else cand_root
                                if candidate and is_valid_product_model(candidate):
                                    valid_chunk_models.append(candidate)

                            for p_clean in valid_chunk_models:
                                for ms_name, ms_date in ms_pairs:
                                    rec = self.create_sanitized_record(
                                        vendor_name=vendor_name,
                                        raw_model=p_clean,
                                        raw_alias=clean_alias if clean_alias and clean_alias.lower() != p_clean.lower() else None,
                                        raw_status=ms_name,
                                        raw_date=ms_date,
                                        source_url=url,
                                        category=category_name,
                                    )
                                    if rec:
                                        records.append(rec)
                                        state.record_model(rec.model_name)
                    continue

                if th_cells:
                    for idx, h in enumerate(th_cells):
                        if any(k in h for k in ("tsb", "bulletin", "advisory")) and "date" not in h:
                            auto_bulletin_idx = idx

                        if any(k in h for k in ("part number", "part #", "sku", "model", "catalog", "reference", "product number", "pid", "article number", "article #", "mlfb", "形式", "モデル形式", "型式", "形名", "品番")) and "replacement" not in h and "successor" not in h and "推奨代替" not in h:
                            if auto_m_idx is None or "part" in h or "sku" in h or "article" in h or "形式" in h or "型式" in h:
                                auto_m_idx = idx
                        elif any(k in h for k in ("product", "related product", "discontinued product", "製品名")) and auto_m_idx is None and "replacement" not in h and "successor" not in h and "description" not in h and "推奨代替" not in h:
                            auto_m_idx = idx

                        if any(k in h for k in ("announcement", "notice date", "announced date", "bulletin date")):
                            auto_announcement_idx = idx

                        if any(k in h for k in ("description", "product name", "title", "シリーズ名", "品名", "適用コントローラ")) and not any(k in h for k in ("replacement", "successor", "date", "announcement", "year", "month", "sku", "model", "article", "形式", "型式")):
                            if auto_a_idx is None or "description" in h or "シリーズ名" in h:
                                auto_a_idx = idx
                        elif "製品名" in h and auto_m_idx is not None and auto_m_idx != idx:
                            auto_a_idx = idx

                        if any(k in h for k in ("replacement", "successor", "migration", "alternative", "preferred product", "推奨代替", "代替シリーズ", "代替品", "後継")):
                            if not any(k in h for k in ("要領書", "マニュアル", "manual", "procedure", "guide", "instruction", "置換要領書")):
                                if any(k in h for k in ("part", "sku", "model", "number", "no", "pid", "mlfb", "製品", "機種", "シリーズ")):
                                    auto_r_idx = idx
                                elif auto_r_idx is None and "description" not in h:
                                    auto_r_idx = idx

                        if any(k in h for k in ("lifecycle status", "status", "phase", "state", "状態")):
                            auto_s_idx = idx

                        is_prod_col = any(k in h for k in ("part", "sku", "model", "catalog", "pid", "product", "description", "article", "mlfb", "形式", "製品名", "シリーズ名"))
                        if not is_prod_col:
                            if any(k in h for k in ("last order", "end of sale", "end-of-sale", "retirement date", "last time buy", "end of life", "eol date", "discontinued", "discontinuation", "support discontinuation", "product discontinuation", "phase out", "phase-out", "製造中止", "生産終了", "製造終了", "販売終了", "生産中止")):
                                auto_milestones.append({"status": "Discontinued", "date": idx})
                            elif any(k in h for k in ("end of support", "end-of-support", "end of service", "eos date", "last day of support", "修理対応期限", "修理品対応期限", "保守終了", "サポート終了")):
                                auto_milestones.append({"status": "End of Support", "date": idx})
                            elif any(k in h for k in ("end of engineering", "end-of-engineering")):
                                auto_milestones.append({"status": "End of Engineering", "date": idx})

                # Disallow alias column matching the exact same column as model
                if auto_a_idx == auto_m_idx:
                    auto_a_idx = None

                # Explicit col_map config overrides dynamic auto-discovery
                m_idx = col_map.get("model", auto_m_idx if auto_m_idx is not None else 0)
                a_idx = col_map.get("aliases") if "aliases" in col_map else (auto_a_idx if not col_map else None)
                r_idx = col_map.get("replacement") if "replacement" in col_map else (auto_r_idx if not col_map else None)
                default_status = col_map.get("default_status") or entry_point.get("default_status")

                active_rowspans: Dict[int, Dict[str, Any]] = {}
                data_rows = rows[1:] if th_cells else rows
                for r in data_rows:
                    raw_tds = r.find_all(["td", "th"])
                    if not raw_tds and not active_rowspans:
                        continue

                    # Reconstruct row grid cells and elements taking into account active rowspans & colspans
                    cells: List[str] = []
                    td_elements: List[Any] = []
                    raw_td_idx = 0
                    current_col = 0

                    while raw_td_idx < len(raw_tds) or current_col in active_rowspans:
                        if current_col in active_rowspans:
                            span_data = active_rowspans[current_col]
                            cells.append(span_data["text"])
                            td_elements.append(span_data["elem"])
                            span_data["remaining"] -= 1
                            if span_data["remaining"] <= 0:
                                del active_rowspans[current_col]
                            current_col += 1
                            continue

                        if raw_td_idx >= len(raw_tds):
                            break

                        td = raw_tds[raw_td_idx]
                        raw_td_idx += 1

                        try:
                            r_span = int(td.get("rowspan", 1) or 1)
                        except (ValueError, TypeError):
                            r_span = 1
                        try:
                            c_span = int(td.get("colspan", 1) or 1)
                        except (ValueError, TypeError):
                            c_span = 1

                        c_text = td.get_text(strip=True)
                        for _ in range(c_span):
                            cells.append(c_text)
                            td_elements.append(td)
                            if r_span > 1:
                                active_rowspans[current_col] = {
                                    "remaining": r_span - 1,
                                    "text": c_text,
                                    "elem": td,
                                }
                            current_col += 1

                    if len(cells) < 2:
                        continue

                    raw_m = cells[m_idx] if len(cells) > m_idx else ""
                    raw_a = cells[a_idx] if a_idx is not None and len(cells) > a_idx else None

                    # Reject attribute and document metadata rows in vertical/card tables
                    m_lower = raw_m.strip().lower()
                    if any(k in m_lower for k in (
                        "end of life", "last time buy", "end of service", "end of support",
                        "end of life document", "replacement manual", "instruction manual",
                        "user manual", "operating manual"
                    )):
                        continue

                    # Strip lead-in descriptions from model cell (e.g. "Includes the following models: Q173DCPU" -> "Q173DCPU")
                    raw_m = re.sub(
                        r'^(?:includes|affects|example of|applies to)[^:]*:\s*',
                        '',
                        raw_m,
                        flags=re.IGNORECASE
                    ).strip()
                    raw_m = re.sub(
                        r'\b(?:includes complete serie|includes the following models?|includes the following modules?|affects the following models?|affects following models?):\s*',
                        '',
                        raw_m,
                        flags=re.IGNORECASE
                    ).strip()

                    if raw_a:
                        raw_a = re.sub(
                            r'^(?:includes|affects|example of|applies to)[^:]*:\s*',
                            '',
                            raw_a,
                            flags=re.IGNORECASE
                        ).strip()
                        raw_a = re.sub(
                            r'\b(?:includes complete serie|includes the following models?|includes the following modules?|affects the following models?|affects following models?):\s*',
                            '',
                            raw_a,
                            flags=re.IGNORECASE
                        ).strip()

                    # Extract replacement links if present
                    raw_r = None
                    if r_idx is not None and len(td_elements) > r_idx:
                        r_el = td_elements[r_idx]
                        r_links = [a.get_text(strip=True) for a in r_el.find_all("a") if a.get_text(strip=True)]
                        if r_links:
                            raw_r = ", ".join(dict.fromkeys(r_links))
                        elif len(cells) > r_idx:
                            raw_r = cells[r_idx]

                    # Extract per-row authentic product link if present
                    row_url = url
                    if len(td_elements) > m_idx:
                        m_a = td_elements[m_idx].find("a", href=True)
                        if m_a and m_a.get("href"):
                            h_link = str(m_a["href"]).strip()
                            if h_link.startswith("/"):
                                from urllib.parse import urljoin
                                h_link = urljoin(url, h_link)
                            if h_link.startswith("http"):
                                row_url = h_link

                    row_extra_meta: Dict[str, Any] = {}
                    ann_idx = col_map.get("announcement_date", auto_announcement_idx)
                    if ann_idx is not None and len(cells) > ann_idx:
                        ann_raw = cells[ann_idx].strip()
                        if ann_raw and is_likely_date_str(ann_raw):
                            try:
                                dt_ann = date_parser.parse(ann_raw, fuzzy=True)
                                row_extra_meta["announcement_date_utc"] = dt_ann.strftime("%Y-%m-%d") + "T00:00:00Z"
                            except Exception:
                                pass

                    b_idx = col_map.get("bulletin", auto_bulletin_idx)
                    if b_idx is not None and len(cells) > b_idx:
                        b_val = sanitize_alias_text(cells[b_idx])
                        if b_val:
                            row_extra_meta["bulletin_id"] = b_val

                    if raw_a and is_likely_date_str(raw_a):
                        if "announcement_date_utc" not in row_extra_meta:
                            try:
                                dt_ann = date_parser.parse(raw_a, fuzzy=True)
                                row_extra_meta["announcement_date_utc"] = dt_ann.strftime("%Y-%m-%d") + "T00:00:00Z"
                            except Exception:
                                pass
                        raw_a = None

                    if not raw_m or not raw_m.strip():
                        continue

                    # Resolve status column or default
                    if "status" in col_map:
                        if isinstance(col_map["status"], int):
                            raw_s = cells[col_map["status"]] if len(cells) > col_map["status"] else (default_status or "Discontinued")
                        else:
                            raw_s = str(col_map["status"])
                    elif auto_s_idx is not None and len(cells) > auto_s_idx:
                        raw_s = cells[auto_s_idx]
                    else:
                        raw_s = str(default_status or "Discontinued")

                    # Resolve date column
                    d_idx = col_map.get("stage_date_utc") if "stage_date_utc" in col_map else col_map.get("date")
                    if d_idx is not None and isinstance(d_idx, int) and len(cells) > d_idx:
                        raw_d = cells[d_idx]
                    else:
                        raw_d = None

                    # Split bundled models preserving parenthesized arguments (e.g. "MS220-8-HW, MS220-8P-HW" or "LIC-MI-L (1D, 1YR)")
                    raw_models = split_model_identifiers(raw_m)
                    if not raw_models:
                        continue

                    # Support multi-milestone extraction (e.g. End of Sale + End of Support dates)
                    milestones_cfg = col_map.get("milestones") or auto_milestones or page_milestones
                    if not milestones_cfg:
                        milestones = [{"status": raw_s, "date": raw_d}]
                    else:
                        milestones = []
                        for ms in milestones_cfg:
                            ms_st = ms.get("status")
                            if isinstance(ms_st, int) and len(cells) > ms_st:
                                ms_st = cells[ms_st]
                            ms_st = str(ms_st or default_status or "Discontinued")

                            ms_dt = ms.get("date")
                            if isinstance(ms_dt, int) and len(cells) > ms_dt:
                                ms_dt = cells[ms_dt]
                            elif not isinstance(ms_dt, str):
                                ms_dt = None

                            milestones.append({"status": ms_st, "date": ms_dt})

                    for single_m in raw_models:
                        clean_m = sanitize_alias_text(single_m) or ""
                        for ms in milestones:
                            rec = self.create_sanitized_record(
                                vendor_name=vendor_name,
                                raw_model=clean_m,
                                raw_alias=raw_a,
                                raw_status=str(ms.get("status") or default_status),
                                raw_date=ms.get("date"),
                                source_url=row_url,
                                category=category_name,
                                raw_replacement=raw_r,
                                extra_meta=row_extra_meta,
                            )
                            if rec:
                                records.append(rec)
                                state.record_model(rec.model_name)

            state.mark_unit_completed(url)
            state.total_records += len(records)
            state.save()
            logger.info(f"[+] [DOM TABLE] Harvested {len(records)} products from {url}")

        except Exception as e:
            logger.error(f"[!] [DOM TABLE] Error crawling table at {url}: {e}")
            if dlq:
                dlq.record_failure(
                    url=url,
                    vendor_id=vendor_id,
                    error_type=type(e).__name__,
                    message=str(e),
                )

        return records
