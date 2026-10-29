"""
Google Gemini AI Extractor for Multi-Vendor EOL & Product Lifecycle Intelligence.
Leverages Google GenAI SDK (google-genai) to extract structured product lifecycle records
from raw crawl content, tables, and technical bulletins across any vendor.
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from google import genai
from google.genai import types

from scraper.config import (
    GEMINI_API_KEY,
    GEMINI_BATCH_MODE,
    GEMINI_ENABLE_PROMPT_CACHING,
    GEMINI_MODEL,
    GEMINI_PROMPT_CACHE_TTL,
    GEMINI_THINKING_BUDGET,
)
from scraper.models import (
    GeminiExtractionBatch,
    GeminiProductItem,
    ProductRecord,
    extract_date_from_bulletin_code,
    is_valid_product_model,
    parse_to_utc_iso,
)
from scraper.vendors import detect_vendor_from_url_or_text, normalize_stage_name

logger = logging.getLogger("ai_scraper.gemini")


EXTRACTION_SYSTEM_INSTRUCTION = """You are an expert industrial automation intelligence analyst specializing in multi-vendor hardware/software lifecycle management.
Analyze the provided crawled web content or technical notice and extract all product lifecycle records into the standardized ProductRecord schema.

### MANDATORY EXTRACTION RULES:
1. **MULTI-VENDOR & STRUCTURE AGNOSTIC**: Support any vendor (e.g., Mitsubishi Electric, Siemens, Schneider Electric, Rockwell Automation / Allen-Bradley, Omron, Cisco, ABB, etc.). Fit all data into the standardized ProductRecord schema.
2. **VENDOR-SPECIFIC LIFECYCLE STATUS (NO FIXED STATUS WHITELIST)**:
   - Manufacturers do NOT follow a single fixed status list. Vendors define distinct lifecycle phases tailored to their operational models (e.g., 'Phase-Out Product', 'Delivery Release', 'Announced Discontinuation', 'Product Cancellation', 'End of Sale', 'Last Date of Support', 'Classic', 'Limited', 'Obsolete', 'Active Mature', 'End of New Service', 'Repair Termination', 'Maintenance Only', 'Stop Shipment', 'Discontinued', 'End of Life', 'Last Time Buy', 'End of Support').
   - Capture the EXACT official status/phase used by the manufacturer. Put NO artificial limitation or restricted enum on status names in output.
   - If a product lists multiple lifecycle milestones (e.g. End of Sale date and Last Date of Support date), emit a SEPARATE ProductRecord for EACH milestone.
3. **UTC DATE NORMALIZATION & DATE OPTIONALITY**:
   - The 'stage_date_utc' column MUST be in UTC ISO 8601 format: 'YYYY-MM-DDTHH:MM:SSZ' (e.g., '2026-09-30T00:00:00Z').
   - If only year/month is given, use the last day of that month at 00:00:00Z.
   - If NO explicit date is given for a discontinued/phased-out model, set 'stage_date_utc' to null. NEVER skip or drop a model because its date is missing!
4. **NO SKIPPING OF MODELS (100% COVERAGE)**:
   - When a series, table row, or text lists multiple models (e.g., 'MI3321G-W and MI3315G-W' or 'FX3-ENET, FX3-ENETADP, FX3-ENETP502'), extract EVERY individual model as its own separate entity. NEVER bundle multiple models together!
   - Unpack model suffixes (e.g., 'FX2N-16MR/ES, -16MT/ES' -> 'FX2N-16MR/ES', 'FX2N-16MT/ES').
5. **ENGLISH TRANSLATION**:
   - If the source is in German, Japanese, Swedish, French, Chinese, or any other regional language, TRANSLATE product category, family, descriptions, and stage names to standard English (e.g. '生産終了' -> 'End of Life (EOL)', '最終受注' -> 'Last Time Buy (LTB)', 'Auslauftyp' -> 'Phase-Out Announced').
6. **METADATA COLUMN**:
   - Populate the 'metadata' dictionary with comprehensive datapoints:
     * 'replacement': successor / alternative product
     * 'family': product family
     * 'series': series / line
     * 'part_number': exact part number or order code
     * 'source_url': source URL
     * 'bulletin_title': bulletin or notice code
     * 'bulletin_url': download URL for PDF
     * 'raw_stage_label': original unnormalized stage text
     * 'detected_language': source language
     * 'notes': migration instructions or notes
"""


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extracts text across all pages of a PDF document using pypdf."""
    if not pdf_bytes:
        return ""
    try:
        import io

        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        extracted_pages = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                extracted_pages.append(t)
        return "\n\n".join(extracted_pages)
    except Exception as e:
        logger.debug(f"Failed to extract text from PDF bytes: {e}")
        return ""


def clean_token_efficient_markdown(raw_text: str) -> str:
    """
    Strips noise, redundant formatting, and padding from crawled markdown
    to minimize input token consumption by 15-30% before calling Gemini.
    """
    if not raw_text:
        return ""

    # Remove HTML comments (e.g. <!-- slide -->, <!-- comment -->)
    text = re.sub(r'<!--.*?-->', '', raw_text, flags=re.DOTALL)

    # Compress markdown table horizontal separators (e.g., |:---|:---| to |---|---|)
    text = re.sub(r'\|(?:\s*[:-]+[-:]\s*\|)+', lambda m: re.sub(r'[: -]{3,}', '---', m.group(0)), text)

    # Remove excessive blank lines (3+ consecutive newlines -> 2)
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)

    # Trim leading/trailing whitespace on lines
    lines = [line.strip() for line in text.split("\n")]

    return "\n".join(lines).strip()


def _gemini_item_to_product_record(
    item: GeminiProductItem,
    default_vendor: str,
    source_url: Optional[str] = None,
) -> Optional[ProductRecord]:
    """Converts a GeminiProductItem from structured extraction into a database-ready ProductRecord."""
    vendor = (item.vendor_name or "").strip() or default_vendor
    model = (item.model_name or "").strip()
    if not is_valid_product_model(model):
        return None

    norm_stage = normalize_stage_name(item.status or "Discontinued")
    raw_status = item.status or norm_stage

    utc_date = None
    if item.stage_date_utc:
        utc_date = parse_to_utc_iso(item.stage_date_utc)

    # Attempt date recovery from bulletin code if direct date was not parsed
    if not utc_date and item.bulletin_code:
        utc_date = extract_date_from_bulletin_code(item.bulletin_code)

    # Mandatory date enforcement: NO NULL ALLOWED
    if not utc_date:
        return None

    # Clean replacement: eliminate generic placeholders
    clean_repl = None
    if item.replacement:
        r_cand = str(item.replacement).strip()
        if r_cand and not any(kw in r_cand.lower() for kw in ["consult", "representative", "official sales", "contact your", "representative"]):
            clean_repl = r_cand

    meta: Dict[str, Any] = {
        "replacement": clean_repl,
        "family": item.category or "General Automation",
        "source_url": source_url or "",
        "bulletin_title": item.bulletin_code or "Official Lifecycle Notice",
        "raw_stage_label": raw_status,
        "notes": item.notes,
    }

    try:
        return ProductRecord(
            vendor_name=vendor,
            model_name=model,
            os=item.os,
            firmware=item.firmware,
            status=raw_status,
            stage=norm_stage,
            vendor_status=raw_status,
            stage_date_utc=utc_date,
            category=item.category or "General Automation",
            product_category=item.category or "General Automation",
            replacement=clean_repl,
            metadata=meta,
        )
    except Exception as err:
        logger.debug(f"Failed to create ProductRecord from Gemini item ({model}): {err}")
        return None


class GeminiExtractor:
    """
    Interfaces with Google Gemini (e.g. gemini-1.5-flash / gemini-2.0-flash / gemini-3.8-flash)
    using the official Google GenAI SDK to perform structured schema extraction.

    Cost & Token Optimization Features:
    1. Thinking Budget Capping: Caps thinking tokens to 0 on Flash models, eliminating internal reasoning output token bills.
    2. Prompt Caching: Leverages native Google GenAI Prompt Caching (system_instruction & client.caches) for up to 90% input discount.
    3. Asynchronous Batch API: Supports Gemini Batch mode (client.batches) with 50% discount on both input and output tokens.
    """

    thinking_budget: Optional[int] = GEMINI_THINKING_BUDGET
    enable_prompt_caching: bool = GEMINI_ENABLE_PROMPT_CACHING
    cache_ttl: str = GEMINI_PROMPT_CACHE_TTL
    batch_mode: bool = GEMINI_BATCH_MODE

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        thinking_budget: Optional[int] = None,
        enable_prompt_caching: Optional[bool] = None,
        cache_ttl: Optional[str] = None,
        batch_mode: Optional[bool] = None,
    ):
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
        self.model_name = model_name or GEMINI_MODEL or "gemini-1.5-flash"
        self.client = None

        # Token & Cost Optimization Settings
        self.thinking_budget = thinking_budget if thinking_budget is not None else GEMINI_THINKING_BUDGET
        self.enable_prompt_caching = enable_prompt_caching if enable_prompt_caching is not None else GEMINI_ENABLE_PROMPT_CACHING
        self.cache_ttl = cache_ttl or GEMINI_PROMPT_CACHE_TTL
        self.batch_mode = batch_mode if batch_mode is not None else GEMINI_BATCH_MODE
        self._active_cache_name: Optional[str] = None

        self.token_metrics: Dict[str, Any] = {
            "total_calls": 0,
            "thinking_budget_applied": self.thinking_budget,
            "prompt_cache_enabled": self.enable_prompt_caching,
            "batch_mode_enabled": self.batch_mode,
            "batch_calls": 0,
        }

        if self.api_key and self.api_key != "your_gemini_api_key_here":
            try:
                self.client = genai.Client(api_key=self.api_key)
                logger.info(
                    f"Initialized Google GenAI Client with model: {self.model_name} "
                    f"(thinking_budget={self.thinking_budget}, prompt_caching={self.enable_prompt_caching}, batch_mode={self.batch_mode})"
                )
            except Exception as e:
                logger.warning(f"Could not initialize Google GenAI Client: {e}")
        else:
            logger.info("No valid GEMINI_API_KEY provided. Operating in deterministic/fallback mode.")

    def is_configured(self) -> bool:
        """Check if Gemini client is ready for live API queries."""
        return bool(self.client and self.api_key and self.api_key != "your_gemini_api_key_here")

    def test_connection(self) -> Tuple[bool, str]:
        """
        Tests the Google Gemini API key by sending a minimal test probe.
        If the primary model is unavailable or 404s, automatically probes supported fallback models.
        Returns (success: bool, message: str).
        """
        if not self.is_configured() or not self.client:
            return False, "GEMINI_API_KEY is not configured or is the default placeholder."

        # Candidate models to probe in order of preference
        candidate_models = [self.model_name]
        for fallback in ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.5-flash", "gemini-flash-latest"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        last_err = ""
        for mod in candidate_models:
            try:
                response = self.client.models.generate_content(
                    model=mod,
                    contents="Reply with: 'GEMINI_OK'"
                )
                text = (response.text or "").strip()
                self.model_name = mod
                return True, f"Connection successful! Model '{mod}' responded: {text}"
            except Exception as e:
                last_err = str(e)
                # If model is unavailable (503), rate-limited (429), or deprecated (404), probe next candidate
                if any(kw in last_err.lower() for kw in ["404", "not_found", "not found", "no longer available", "503", "unavailable", "high demand", "429"]):
                    logger.warning(f"Model '{mod}' unavailable or busy. Probing next candidate...")
                    continue
                # For auth or permissions errors (400/401/403), do not cycle models
                break

        return False, f"Gemini API Error: {last_err}"

    def _build_thinking_config(self) -> Optional[types.ThinkingConfig]:
        """
        Configures thinking token budget for Gemini Flash models.
        Setting thinking_budget=0 disables internal chain-of-thought generation,
        eliminating unnecessary output token billing on deterministic extraction tasks.
        """
        if self.thinking_budget is not None and self.thinking_budget >= 0:
            return types.ThinkingConfig(
                thinking_budget=self.thinking_budget,
                include_thoughts=False
            )
        return None

    def get_or_create_prompt_cache(self, context_prefix: Optional[str] = None) -> Optional[str]:
        """
        Retrieves or creates a Google Prompt Cache using client.caches.create().
        Slashes input token price by up to 90% across repeated crawl queries.
        Falls back smoothly if the context is below Gemini's minimum token threshold (32k).
        """
        if not self.is_configured() or not self.client or not self.enable_prompt_caching:
            return None

        if self._active_cache_name:
            return self._active_cache_name

        try:
            cache_contents: Optional[List[Any]] = [context_prefix] if context_prefix else None
            cache_config = types.CreateCachedContentConfig(
                system_instruction=EXTRACTION_SYSTEM_INSTRUCTION,
                contents=cache_contents,
                ttl=self.cache_ttl,
                display_name=f"lifecycle_cache_{int(time.time())}"
            )
            cache = self.client.caches.create(
                model=self.model_name,
                config=cache_config
            )
            self._active_cache_name = getattr(cache, "name", None)
            if self._active_cache_name:
                logger.info(f"Initialized Google Prompt Cache '{self._active_cache_name}' (up to 90% input token discount).")
                self.token_metrics["prompt_cache_active"] = True
                self.token_metrics["active_cache_name"] = self._active_cache_name
            return self._active_cache_name
        except Exception as e:
            err_msg = str(e).lower()
            if any(kw in err_msg for kw in ["32768", "minimum", "token", "threshold"]):
                logger.debug("Prompt content is below 32k token threshold for explicit cache; using implicit system_instruction caching.")
            else:
                logger.debug(f"Could not create explicit prompt cache ({e}); using implicit system_instruction caching.")
            return None

    def delete_prompt_cache(self) -> None:
        """Deletes the active prompt cache on Google GenAI to release resources."""
        if self._active_cache_name and self.client:
            try:
                self.client.caches.delete(name=self._active_cache_name)
                logger.info(f"Released prompt cache: {self._active_cache_name}")
            except Exception as e:
                logger.debug(f"Error releasing prompt cache {self._active_cache_name}: {e}")
            finally:
                self._active_cache_name = None
                self.token_metrics["prompt_cache_active"] = False

    def create_batch_extraction_job(
        self,
        chunks: List[Dict[str, Any]],
        display_name: Optional[str] = None
    ) -> str:
        """
        Submits an asynchronous batch extraction job via Google Gemini Batch API.
        Slashes both input AND output token prices by 50% for non-real-time extraction.
        """
        if not self.is_configured() or not self.client:
            raise RuntimeError("Gemini API key is not configured for batch job execution.")

        inlined_requests = []
        for idx, item in enumerate(chunks):
            chunk_text = item.get("markdown_chunk", "")
            clean_chunk = clean_token_efficient_markdown(chunk_text)
            source_url = item.get("source_url") or "N/A"
            context = item.get("context") or "Lifecycle EOL Portal"
            vendor = detect_vendor_from_url_or_text(source_url, clean_chunk)

            user_content = (
                f"Source URL: {source_url}\n"
                f"Context: {context}\n"
                f"Vendor: {vendor}\n\n"
                f"Content to analyze:\n\"\"\"\n{clean_chunk}\n\"\"\""
            )

            gen_config_kwargs: Dict[str, Any] = {
                "response_mime_type": "application/json",
                "response_schema": GeminiExtractionBatch,
                "temperature": 0.1,
                "system_instruction": EXTRACTION_SYSTEM_INSTRUCTION
            }
            thinking_cfg = self._build_thinking_config()
            if thinking_cfg:
                gen_config_kwargs["thinking_config"] = thinking_cfg

            req = types.InlinedRequest(
                model=self.model_name,
                contents=user_content,
                metadata={"index": str(idx), "vendor": vendor, "url": source_url},
                config=types.GenerateContentConfig(**gen_config_kwargs)
            )
            inlined_requests.append(req)

        job_config = types.CreateBatchJobConfig(
            display_name=display_name or f"lifecycle_batch_{int(time.time())}"
        )
        batch_job = self.client.batches.create(
            model=self.model_name,
            src=inlined_requests,
            config=job_config
        )
        job_name = getattr(batch_job, "name", str(batch_job))
        logger.info(f"Submitted Gemini Batch Job '{job_name}' with {len(inlined_requests)} requests (50% token cost savings applied).")
        self.token_metrics["batch_calls"] += len(inlined_requests)
        return job_name

    def poll_batch_job(
        self,
        job_name: str,
        poll_interval: int = 5,
        timeout: int = 300
    ) -> List[ProductRecord]:
        """
        Polls a submitted Gemini Batch Job until completion and returns extracted ProductRecords.
        """
        if not self.is_configured() or not self.client:
            return []

        start_time = time.time()
        logger.info(f"Polling Gemini Batch Job '{job_name}' (timeout: {timeout}s)...")

        while time.time() - start_time < timeout:
            job = self.client.batches.get(name=job_name)
            state_str = str(getattr(job, "state", "")).upper()

            if any(kw in state_str for kw in ["SUCCEEDED", "JOB_STATE_SUCCEEDED"]):
                logger.info(f"Gemini Batch Job '{job_name}' SUCCEEDED. Parsing inlined responses...")
                return self._parse_batch_job_destination(job)

            if any(kw in state_str for kw in ["FAILED", "CANCELLED", "EXPIRED", "JOB_STATE_FAILED"]):
                err = getattr(job, "error", "Unknown batch failure")
                logger.error(f"Gemini Batch Job '{job_name}' ended with state '{state_str}': {err}")
                return []

            logger.debug(f"Batch Job '{job_name}' state: {state_str}. Waiting {poll_interval}s...")
            time.sleep(poll_interval)

        logger.warning(f"Gemini Batch Job '{job_name}' timed out after {timeout} seconds.")
        return []

    def _parse_batch_job_destination(self, job: Any) -> List[ProductRecord]:
        """Parses inlined responses from a succeeded BatchJob into ProductRecord list."""
        all_products: List[ProductRecord] = []
        dest = getattr(job, "dest", None)
        if not dest:
            return all_products

        responses = getattr(dest, "inlined_responses", []) or []
        for inlined in responses:
            try:
                resp = getattr(inlined, "response", None)
                if not resp or not getattr(resp, "text", None):
                    continue
                raw_json = resp.text.strip()
                if "```" in raw_json:
                    m_fence = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_json, re.DOTALL)
                    if m_fence:
                        raw_json = m_fence.group(1).strip()
                    else:
                        raw_json = re.sub(r'^```(?:json)?\s*', '', raw_json)
                        raw_json = re.sub(r'\s*```$', '', raw_json).strip()

                data = json.loads(raw_json)
                batch = GeminiExtractionBatch.model_validate(data)
                for item in batch.products:
                    p = _gemini_item_to_product_record(item, default_vendor=batch.vendor_name)
                    if p:
                        all_products.append(p)
            except Exception as e:
                logger.warning(f"Error parsing inlined batch item: {e}")

        logger.info(f"Batch extraction successfully yielded {len(all_products)} product records.")
        return all_products

    def extract_batch(
        self,
        chunks: List[Dict[str, Any]],
        poll_interval: int = 5,
        timeout: int = 300
    ) -> List[ProductRecord]:
        """
        High-level batch extraction handler.
        If batch_mode is True and Gemini is configured, utilizes the 50% discount Batch API.
        Otherwise executes synchronous extraction across chunks.
        """
        if not chunks:
            return []

        if self.is_configured() and self.batch_mode:
            try:
                job_name = self.create_batch_extraction_job(chunks)
                results = self.poll_batch_job(job_name, poll_interval=poll_interval, timeout=timeout)
                if results:
                    return results
                logger.warning("Batch job returned 0 records or failed; falling back to synchronous extraction.")
            except Exception as be:
                err_str = str(be)
                if "failed_precondition" in err_str.lower():
                    logger.info("Note: Google GenAI Batch API requires a linked Google Cloud billing account on your API key. Gracefully executing synchronous extraction with prompt caching...")
                else:
                    logger.warning(f"Could not execute Gemini Batch API ({be}); falling back to synchronous extraction.")

        # Synchronous fallback or default
        all_extracted: List[ProductRecord] = []
        for chunk in chunks:
            extracted = self.extract_from_markdown(
                markdown_chunk=chunk.get("markdown_chunk", ""),
                context=chunk.get("context"),
                source_url=chunk.get("source_url")
            )
            all_extracted.extend(extracted)
        return all_extracted

    def extract_from_pdf_url(
        self,
        pdf_url: str,
        default_vendor: str = "Mitsubishi Electric",
        timeout: int = 15
    ) -> List[ProductRecord]:
        """
        Downloads a technical PDF notice and extracts structured lifecycle records
        via pypdf and structured extraction.
        """
        import requests

        from scraper.config import USER_AGENT
        from scraper.security import is_safe_url

        if not is_safe_url(pdf_url):
            return []

        try:
            resp = requests.get(pdf_url, timeout=timeout, headers={"User-Agent": USER_AGENT})
            if resp.status_code == 200 and resp.content:
                text = extract_text_from_pdf_bytes(resp.content)
                if text:
                    return self.extract_from_markdown(
                        markdown_chunk=text[:25000],
                        context=f"{default_vendor} PDF Lifecycle Notice",
                        source_url=pdf_url
                    )
        except Exception as e:
            logger.debug(f"Could not extract lifecycle records from PDF {pdf_url}: {e}")
        return []

    def extract_from_markdown(
        self,
        markdown_chunk: str,
        context: Optional[str] = None,
        source_url: Optional[str] = None
    ) -> List[ProductRecord]:
        """
        Uses Google Gemini to extract structured product records from crawled markdown or text.
        Applies token optimization:
        1. Token-efficient markdown trimming (removes noise/padding)
        2. Thinking budget cap (0 reasoning overhead on Flash models)
        3. Native prompt caching (system_instruction / cached_content up to 90% discount)
        """
        detected_vendor = detect_vendor_from_url_or_text(source_url or "", markdown_chunk)

        if not self.is_configured() or not self.client:
            logger.info(f"GEMINI_API_KEY not configured. Running deterministic extractor for vendor '{detected_vendor}'.")
            return self.fallback_rule_based_extraction(markdown_chunk, source_url=source_url, default_vendor=detected_vendor)

        clean_text = clean_token_efficient_markdown(markdown_chunk)
        user_prompt = (
            f"Source URL: {source_url or 'N/A'}\n"
            f"Context: {context or 'Industrial Automation Lifecycle & EOL Portal'}\n"
            f"Vendor: {detected_vendor}\n\n"
            f"Content to analyze:\n```\n{clean_text}\n```\n"
        )
        cache_name = self.get_or_create_prompt_cache() if self.enable_prompt_caching else None
        thinking_cfg = self._build_thinking_config()
        self.token_metrics["total_calls"] += 1

        max_api_retries = 2
        for attempt in range(max_api_retries + 1):
            try:
                logger.info(
                    f"Calling Google Gemini ({self.model_name}) for structured extraction (Attempt {attempt + 1}/{max_api_retries + 1})... "
                    f"[thinking_budget={self.thinking_budget}, cache={'active' if cache_name else 'system_instruction'}]"
                )

                gen_config_kwargs: Dict[str, Any] = {
                    "response_mime_type": "application/json",
                    "response_schema": GeminiExtractionBatch,
                    "temperature": 0.1,
                }
                if cache_name:
                    gen_config_kwargs["cached_content"] = cache_name
                else:
                    gen_config_kwargs["system_instruction"] = EXTRACTION_SYSTEM_INSTRUCTION

                if thinking_cfg:
                    gen_config_kwargs["thinking_config"] = thinking_cfg

                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(**gen_config_kwargs)
                )

                text_response = response.text
                if not text_response:
                    logger.warning("Empty response received from Gemini API. Using fallback.")
                    return self.fallback_rule_based_extraction(markdown_chunk, source_url=source_url, default_vendor=detected_vendor)

                cleaned_json = text_response.strip()
                if "```" in cleaned_json:
                    m_fence = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned_json, re.DOTALL)
                    if m_fence:
                        cleaned_json = m_fence.group(1).strip()
                    else:
                        cleaned_json = re.sub(r'^```(?:json)?\s*', '', cleaned_json)
                        cleaned_json = re.sub(r'\s*```$', '', cleaned_json).strip()

                data = json.loads(cleaned_json)
                batch = GeminiExtractionBatch.model_validate(data)

                # Convert Gemini items to database-ready ProductRecord instances
                processed_products = []
                for item in batch.products:
                    p = _gemini_item_to_product_record(
                        item,
                        default_vendor=detected_vendor,
                        source_url=source_url,
                    )
                    if p:
                        processed_products.append(p)

                logger.info(f"Gemini successfully extracted {len(processed_products)} per-stage product records.")
                return processed_products

            except Exception as e:
                err_str = str(e).lower()
                # If thinking_config is unsupported by the model, disable it and retry
                if "thinking" in err_str and thinking_cfg is not None:
                    logger.info("Thinking budget not supported on this model; retrying without thinking_config.")
                    thinking_cfg = None
                    continue
                # If cached_content is invalid or expired, reset cache and retry with system_instruction
                if "cached" in err_str and cache_name is not None:
                    logger.info("Cached content error; retrying with direct system_instruction.")
                    cache_name = None
                    self._active_cache_name = None
                    continue
                if any(kw in err_str for kw in ["429", "quota", "resource", "rate", "timeout", "404", "not_found", "not found", "no longer available", "503", "unavailable", "high demand"]) and attempt < max_api_retries:
                    candidates = ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.5-flash", "gemini-flash-latest"]
                    try:
                        curr_idx = candidates.index(self.model_name)
                        next_candidate = candidates[(curr_idx + 1) % len(candidates)]
                    except ValueError:
                        next_candidate = candidates[0]
                    backoff_secs = (attempt + 1) * 2
                    logger.warning(f"Gemini transient limit/error on '{self.model_name}' ({e}). Switching to '{next_candidate}' (backoff {backoff_secs}s)...")
                    self.model_name = next_candidate
                    time.sleep(backoff_secs)
                    continue
                logger.error(f"Error querying Google Gemini API: {e}. Executing fallback extractor.")
                return self.fallback_rule_based_extraction(markdown_chunk, source_url=source_url, default_vendor=detected_vendor)

        return self.fallback_rule_based_extraction(markdown_chunk, source_url=source_url, default_vendor=detected_vendor)

    def fallback_rule_based_extraction(
        self,
        text: str,
        source_url: Optional[str] = None,
        default_vendor: str = "Mitsubishi Electric"
    ) -> List[ProductRecord]:
        """
        Deterministic, vendor-aware extractor with per-stage expansion,
        complete model unpacking, UTC dates, and rich metadata.
        """
        products: List[ProductRecord] = []
        lines = text.split("\n")

        current_series = ""
        current_models_text = ""
        current_heading_status = ""
        stage_dates: Dict[str, Tuple[str, str]] = {}  # stage_name -> (raw_date, raw_label)
        bulletin_code = ""
        bulletin_link = ""
        category = "General Automation"

        def split_models(raw_text: str, fallback_series: str) -> List[str]:
            """Splits bundled model descriptions into clean, individual part numbers without skipping."""
            cleaned = raw_text.replace("\xa0", " ").replace("\u00a0", " ")
            for prefix in [
                "Includes the following modules:", "Includes following models:",
                "Affects the following model:", "Includes the following model:",
                "Includes the following:", "Affects the complete series",
                "Includes following model:", "Example of main units:",
                "Includes following units:", "Includes complete serie:",
                "Includes the following parts:", "Affected models:",
                "Order numbers:", "Scope:", "Models:", "Discontinued items:",
                "Discontinued products:"
            ]:
                if prefix.lower() in cleaned.lower():
                    parts = cleaned.split(":", 1)
                    if len(parts) > 1:
                        cleaned = parts[1]
                    else:
                        cleaned = cleaned.replace(prefix, "")

            extracted: List[str] = []

            # First, normalize slash-separated models with spaces, e.g. "ModelA / ModelB"
            cleaned = re.sub(r'\s+/\s+', ', ', cleaned)

            # Split by commas, semicolons, 'and', '&'
            tokens = [item.strip().strip(".").strip() for item in re.split(r'[\,\;\&]|\band\b', cleaned)]

            last_valid_model = ""
            for item in tokens:
                if not item or len(item) < 2:
                    continue

                item_lower = item.lower()
                if any(item_lower.startswith(skip) for skip in ["see pdf", "affects", "includes", "example"]):
                    continue

                # Range expansion: e.g. "1756-L61 to 1756-L63"
                m_range = re.match(r'^([A-Za-z0-9\-]+?)(\d+)\s+(?:to|through|\.\.)\s+([A-Za-z0-9\-]+?)(\d+)$', item)
                if m_range and m_range.group(1) == m_range.group(3):
                    pfx = m_range.group(1)
                    start_num = int(m_range.group(2))
                    end_num = int(m_range.group(4))
                    if 0 < (end_num - start_num) <= 50:
                        for n in range(start_num, end_num + 1):
                            m_candidate = f"{pfx}{n}"
                            if is_valid_product_model(m_candidate):
                                extracted.append(m_candidate)
                                last_valid_model = m_candidate
                        continue

                # Suffix / dash expansion: e.g. "-16MT/ES" following "FX2N-16MR/ES"
                if item.startswith("-") and last_valid_model:
                    m_pfx = re.match(r'^([A-Za-z0-9]+)\-', last_valid_model)
                    if m_pfx:
                        expanded = f"{m_pfx.group(1)}{item}"
                        if is_valid_product_model(expanded):
                            extracted.append(expanded)
                            continue

                # Unpack parenthetical models: e.g. "Series 6000 (Model 6001, Model 6002)"
                if "(" in item and ")" in item:
                    m_parenthesis = re.search(r'\(([^)]+)\)', item)
                    outer = re.sub(r'\(.*?\)', '', item).strip()
                    if is_valid_product_model(outer):
                        extracted.append(outer)
                        last_valid_model = outer
                    if m_parenthesis:
                        inner_parts = re.split(r'[\,\/]', m_parenthesis.group(1))
                        for ip in inner_parts:
                            ip_clean = ip.strip()
                            if is_valid_product_model(ip_clean):
                                extracted.append(ip_clean)
                        continue

                if is_valid_product_model(item):
                    extracted.append(item)
                    last_valid_model = item

            if not extracted and fallback_series and is_valid_product_model(fallback_series):
                extracted.append(fallback_series.strip())

            return extracted

        def flush_records():
            nonlocal current_series, current_models_text, stage_dates, bulletin_code, bulletin_link, category, current_heading_status
            if not current_series and not current_models_text:
                return

            models = split_models(current_models_text, current_series)
            if not models:
                current_series = ""
                current_models_text = ""
                stage_dates = {}
                bulletin_code = ""
                bulletin_link = ""
                return

            # Per user specification: No hardcoded OS/firmware defaults.
            # OS and Firmware are populated ONLY if explicitly detected in source documentation.
            detected_category = category
            os_val = None
            firmware_val = None
            replacement = None

            combined_context = (current_series + " " + current_models_text).lower()
            if "plc" in combined_context or "controller" in combined_context or "melsec" in combined_context:
                detected_category = "Programmable Logic Controller (PLC)"
            elif "ipc" in combined_context or "industrial pc" in combined_context:
                detected_category = "Industrial PC (IPC)"
            elif "hmi" in combined_context or "display" in combined_context or "panel" in combined_context or "got" in combined_context:
                detected_category = "HMI (Human-Machine Interface)"
            elif "inverter" in combined_context or "drive" in combined_context:
                detected_category = "Inverter / Drive"
            elif "servo" in combined_context or "motion" in combined_context:
                detected_category = "Motion Controller / Servo"
            elif "robot" in combined_context:
                detected_category = "Industrial Robot"
            elif "switch" in combined_context or "router" in combined_context or "gateway" in combined_context:
                detected_category = "Industrial Networking"

            # Dynamically check for explicitly stated OS or Firmware
            m_os = re.search(r'(?:OS|Operating System|Platform)\s*:\s*([^,\n\r]+)', current_models_text + " " + current_series, re.IGNORECASE)
            if m_os:
                os_val = m_os.group(1).strip()

            m_fw = re.search(r'(?:Firmware|FW|Version|Ver\.?)\s*:\s*([vV]?\d+(?:\.\d+)+)', current_models_text + " " + current_series, re.IGNORECASE)
            if m_fw:
                firmware_val = m_fw.group(1).strip()

            # Date Handling & Bulletin Date Recovery
            bulletin_date = extract_date_from_bulletin_code(bulletin_code) if bulletin_code else None
            effective_stages = dict(stage_dates)
            if not effective_stages and bulletin_date:
                fallback_stg = current_heading_status or "Discontinued"
                effective_stages[fallback_stg] = (bulletin_date, fallback_stg)

            # Prepare list of milestones for metadata
            milestone_summary = [
                {"stage": stg, "date_utc": parse_to_utc_iso(d_raw) if d_raw else None, "raw_date": d_raw}
                for stg, (d_raw, _) in effective_stages.items()
            ]

            # RULE 2: EMIT ONE RECORD PER STAGE A PRODUCT HAS (Zero limitations on status)
            for model_name in models:
                if not is_valid_product_model(model_name):
                    continue
                for stage_name, (raw_date_str, raw_label) in effective_stages.items():
                    norm_stage = normalize_stage_name(stage_name)
                    if len(norm_stage) > 100:
                        norm_stage = norm_stage[:100].strip()
                    utc_date = parse_to_utc_iso(raw_date_str) if raw_date_str else None
                    if not utc_date and bulletin_code:
                        utc_date = extract_date_from_bulletin_code(bulletin_code)

                    # MANDATORY DATE ENFORCEMENT: Reject any stage milestone without a date (NO NULL ALLOWED)
                    if not utc_date:
                        continue

                    metadata_dict = {
                        "replacement": replacement,
                        "family": detected_category,
                        "series": current_series or "General Series",
                        "part_number": model_name,
                        "source_url": source_url or "https://support.industry.com/lifecycle",
                        "bulletin_title": bulletin_code or "Official Lifecycle Notice",
                        "bulletin_url": bulletin_link or None,
                        "raw_stage_label": raw_label,
                        "raw_date_str": raw_date_str or None,
                        "all_milestones": milestone_summary,
                        "notes": f"Catalog series: {current_series}" if current_series else None
                    }

                    try:
                        products.append(ProductRecord(
                            vendor_name=default_vendor,
                            model_name=model_name,
                            os=os_val,
                            firmware=firmware_val,
                            status=raw_label[:100] if raw_label else norm_stage,
                            stage=norm_stage,
                            vendor_status=raw_label[:100] if raw_label else norm_stage,
                            stage_date_utc=utc_date,
                            product_category=detected_category,
                            metadata=metadata_dict
                        ))
                    except Exception as err:
                        logger.debug(f"Skipping product record validation error: {err}")

            # Reset state for next block
            current_series = ""
            current_models_text = ""
            stage_dates = {}
            bulletin_code = ""
            bulletin_link = ""

        table_headers: List[str] = []
        prev_cells: List[str] = []

        # Parse markdown lines
        for line in lines:
            line_str = line.strip()
            if not line_str:
                table_headers = []
                prev_cells = []
                continue

            # Heading indicating new product block
            if line_str.startswith("## ") or line_str.startswith("### "):
                flush_records()
                table_headers = []
                prev_cells = []
                heading_text = line_str.lstrip("#").strip()
                # Check if heading has a status keyword
                h_low = heading_text.lower()
                current_heading_status = ""
                for kw_stg in ["discontinued", "obsolete", "phase-out", "phase out", "end of life", "end of sale", "classic", "limited", "stop shipment", "production termination"]:
                    if kw_stg in h_low:
                        current_heading_status = normalize_stage_name(kw_stg)
                        break
                # Ensure heading is not a cookie notice or navigation menu
                if is_valid_product_model(heading_text):
                    current_series = heading_text
                else:
                    current_series = ""
                continue

            if line_str.startswith("Scope:") or line_str.startswith("Models:"):
                current_models_text = line_str.split(":", 1)[1].strip()
                continue

            # Markdown bullet list item (- **Key**: Value)
            if line_str.startswith("- **") or line_str.startswith("* **"):
                table_headers = []
                prev_cells = []
                parts = line_str.lstrip("- *").split("**:", 1)
                if len(parts) == 1:
                    parts = line_str.lstrip("- *").split("** :", 1)
                if len(parts) == 2:
                    k = parts[0].replace("**", "").strip()
                    v = parts[1].strip()

                    # Check for link
                    if "[" in v and "](" in v:
                        m_url = re.search(r'\[([^\]]+)\]\(([^\)]+)\)', v)
                        if m_url:
                            v = m_url.group(1).strip()
                            bulletin_link = m_url.group(2).strip()

                    k_lower = k.lower()

                    # Special case: Historical discontinuation bullet with embedded date & models in v
                    # Example: **F1J - Complete Series, production discontinuation in September 2000.**: Example of Main units (CPU's): F1J-32MR-ES...
                    if "discontinuation in" in k_lower or "production discontinuation" in k_lower:
                        m_dt = re.search(r'in\s+([A-Za-z]+\s+\d{4})', k, re.IGNORECASE)
                        raw_hist_date = m_dt.group(1) if m_dt else "2000-01-01"
                        hist_utc = parse_to_utc_iso(raw_hist_date)
                        if not hist_utc:
                            continue
                        m_s = re.search(r'^([A-Za-z0-9\/\-]+(?:\s+Series)?)', k)
                        hist_series = m_s.group(1).strip() if m_s else k[:25]
                        hist_models = split_models(v, hist_series)
                        for hm in hist_models:
                            if not is_valid_product_model(hm):
                                continue
                            meta_d = {
                                "replacement": None,
                                "family": "Programmable Logic Controller (PLC)",
                                "series": hist_series,
                                "part_number": hm,
                                "source_url": source_url or "https://no-fa.mitsubishielectric.com/fa/no_en/support/Product-Life-Cycle-Information",
                                "bulletin_title": "Official Lifecycle Notice",
                                "bulletin_url": None,
                                "raw_stage_label": "Production Discontinuation",
                                "raw_date_str": raw_hist_date,
                                "all_milestones": [{"stage": "Discontinued", "date_utc": hist_utc, "raw_date": raw_hist_date}],
                                "notes": f"Historical series: {hist_series}"
                            }
                            try:
                                products.append(ProductRecord(
                                    vendor_name=default_vendor,
                                    model_name=hm,
                                    os=None,
                                    firmware=None,
                                    stage="Discontinued",
                                    vendor_status="Production Discontinuation",
                                    stage_date_utc=hist_utc,
                                    product_category="Programmable Logic Controller (PLC)",
                                    metadata=meta_d
                                ))
                            except Exception:
                                pass
                        continue

                    if any(kw in k_lower for kw in ["document", "bulletin", "pdf", "notice"]):
                        bulletin_code = v
                    elif any(kw in k_lower for kw in ["eol", "life", "buy", "ltb", "service", "eos", "repair", "discontinu", "phase", "order", "sale", "support", "obsolete", "classic", "limited", "delivery", "cancellation", "stop shipment", "maintenance", "withdrawal", "abkündigung", "生産終了", "最終受注"]):
                        if len(k) <= 100 and not any(non_stg in k_lower for non_stg in ["series", "example", "unit", "expansion", "cpu"]):
                            norm_stage = normalize_stage_name(k)
                            stage_dates[norm_stage] = (v, k)
                    elif any(kw in k_lower for kw in ["model", "module", "unit", "scope", "include"]):
                        current_models_text += f", {v}"

            # Plain bullet list item (e.g. - FX2N-16MR or * 6ES7 315-2AG10-0AB0)
            elif (line_str.startswith("- ") or line_str.startswith("* ")) and "**" not in line_str:
                item_text = line_str.lstrip("- *").strip()
                if "[" in item_text and "](" in item_text:
                    m_link = re.search(r'\[([^\]]+)\]\(([^\)]+)\)', item_text)
                    if m_link:
                        item_text = m_link.group(1).strip()
                if is_valid_product_model(item_text):
                    current_models_text += f", {item_text}"

            # Table row parsing
            elif line_str.startswith("|") and line_str.endswith("|"):
                cells = [c.strip() for c in line_str.strip("|").split("|")]
                is_sep = len(cells) > 0 and all(bool(re.match(r'^:?-+:?$', c)) for c in cells if c)

                if is_sep:
                    if prev_cells:
                        table_headers = [c.lower() for c in prev_cells]
                    continue

                if table_headers and len(cells) == len(table_headers):
                    # Multi-column table row parsing
                    header_map = {table_headers[i]: cells[i] for i in range(len(cells))}
                    
                    # Locate model column
                    model_col = None
                    for h in table_headers:
                        if any(kw in h for kw in ["model", "product", "part", "device", "item", "unit"]):
                            model_col = h
                            break
                    if not model_col and len(table_headers) >= 2:
                        model_col = table_headers[0]

                    # Locate replacement column
                    repl_val = None
                    for h in table_headers:
                        if any(kw in h for kw in ["replace", "successor", "alternative", "migration"]):
                            cand = (header_map[h] or "").strip()
                            if cand and cand.lower() not in ("-", "--", "n/a", "none", "null", "nan") and not any(kw in cand.lower() for kw in ["consult", "representative", "official sales", "contact your", "sales rep"]):
                                repl_val = cand
                            break

                    # Locate series column
                    row_series = current_series or "General Series"
                    for h in table_headers:
                        if any(kw in h for kw in ["series", "family", "category"]):
                            if header_map[h]:
                                row_series = header_map[h]
                            break

                    # Check for dedicated stage columns (e.g. End of Sale Date, End of Support Date)
                    stage_cols_found = []
                    for h in table_headers:
                        if any(kw in h for kw in ["eol", "eos", "life", "buy", "ltb", "sale", "support", "service", "repair", "discontinu", "phase", "order", "obsolete", "classic", "limited", "delivery", "cancellation", "stop shipment", "maintenance", "withdrawal", "abkündigung", "生産終了"]):
                            val = header_map[h]
                            if val and val != "-" and val.lower() != "n/a":
                                stage_cols_found.append((h, val))

                    raw_model_str = header_map.get(model_col, "") if model_col else ""
                    if raw_model_str:
                        # Determine category from series and model
                        row_cat = "General Industrial Device"
                        rc_low = (row_series + " " + raw_model_str).lower()
                        if any(kw in rc_low for kw in ["plc", "controller", "melsec", "cpu", "fx"]):
                            row_cat = "Programmable Logic Controller (PLC)"
                        elif any(kw in rc_low for kw in ["hmi", "display", "got", "panel"]):
                            row_cat = "HMI (Human-Machine Interface)"
                        elif any(kw in rc_low for kw in ["inverter", "drive", "vfd", "freq"]):
                            row_cat = "Inverter / Drive"
                        elif any(kw in rc_low for kw in ["ipc", "industrial pc"]):
                            row_cat = "Industrial PC (IPC)"

                        row_models = split_models(raw_model_str, row_series)
                        for r_mod in row_models:
                            if not is_valid_product_model(r_mod):
                                continue

                            if stage_cols_found:
                                for stg_header, raw_dt in stage_cols_found:
                                    n_stage = normalize_stage_name(stg_header)
                                    u_date = parse_to_utc_iso(raw_dt)
                                    if not u_date and bulletin_code:
                                        u_date = extract_date_from_bulletin_code(bulletin_code)
                                    # MANDATORY DATE GUARD: NO NULL ALLOWED
                                    if not u_date:
                                        continue
                                    m_dict = {
                                        "replacement": repl_val,
                                        "family": row_cat,
                                        "series": row_series,
                                        "part_number": r_mod,
                                        "source_url": source_url or "https://support.industry.com/lifecycle",
                                        "bulletin_title": bulletin_code or "Official Lifecycle Table",
                                        "bulletin_url": bulletin_link or None,
                                        "raw_stage_label": stg_header,
                                        "raw_date_str": raw_dt,
                                        "all_milestones": [{"stage": n_stage, "date_utc": u_date, "raw_date": raw_dt}],
                                        "notes": f"Catalog series: {row_series}"
                                    }
                                    try:
                                        products.append(ProductRecord(
                                            vendor_name=default_vendor,
                                            model_name=r_mod,
                                            os=None,
                                            firmware=None,
                                            status=stg_header[:100] if stg_header else n_stage,
                                            stage=n_stage,
                                            vendor_status=stg_header[:100] if stg_header else n_stage,
                                            stage_date_utc=u_date,
                                            product_category=row_cat,
                                            metadata=m_dict
                                        ))
                                    except Exception:
                                        pass
                            else:
                                # Generic Status + Date column lookup
                                stg_val = "Discontinued"
                                for h in table_headers:
                                    if any(kw in h for kw in ["status", "stage", "state"]):
                                        stg_val = header_map[h]
                                        break
                                dt_val = ""
                                for h in table_headers:
                                    if "date" in h or "effective" in h:
                                        dt_val = header_map[h]
                                        break
                                n_stage = normalize_stage_name(stg_val)
                                u_date = parse_to_utc_iso(dt_val)
                                if not u_date and bulletin_code:
                                    u_date = extract_date_from_bulletin_code(bulletin_code)
                                # MANDATORY DATE GUARD: NO NULL ALLOWED
                                if not u_date:
                                    continue
                                m_dict = {
                                    "replacement": repl_val,
                                    "family": row_cat,
                                    "series": row_series,
                                    "part_number": r_mod,
                                    "source_url": source_url or "https://support.industry.com/lifecycle",
                                    "bulletin_title": bulletin_code or "Official Lifecycle Table",
                                    "bulletin_url": bulletin_link or None,
                                    "raw_stage_label": stg_val,
                                    "raw_date_str": dt_val,
                                    "all_milestones": [{"stage": n_stage, "date_utc": u_date, "raw_date": dt_val}],
                                    "notes": f"Catalog series: {row_series}"
                                }
                                try:
                                    products.append(ProductRecord(
                                        vendor_name=default_vendor,
                                        model_name=r_mod,
                                        os=None,
                                        firmware=None,
                                        status=stg_val[:100] if stg_val else n_stage,
                                        stage=n_stage,
                                        vendor_status=stg_val[:100] if stg_val else n_stage,
                                        stage_date_utc=u_date,
                                        product_category=row_cat,
                                        metadata=m_dict
                                    ))
                                except Exception:
                                    pass

                    prev_cells = cells
                    continue

                prev_cells = cells

                # Fallback 2-column key-value parsing (| Key | Value |)
                if len(cells) == 2:
                    k, v = cells[0].strip(), cells[1].strip()
                    k_lower = k.lower()
                    if any(kw in k_lower for kw in ["document", "pdf", "bulletin"]):
                        bulletin_code = v
                    elif any(kw in k_lower for kw in ["eol", "life", "buy", "ltb", "service", "eos", "repair", "discontinu", "phase", "order", "sale", "support", "obsolete", "classic", "limited", "delivery", "cancellation", "stop shipment", "maintenance", "withdrawal", "abkündigung", "生産終了", "最終受注"]):
                        if len(k) <= 100 and not any(non_stg in k_lower for non_stg in ["series", "example", "unit", "expansion", "cpu"]):
                            norm_stage = normalize_stage_name(k)
                            stage_dates[norm_stage] = (v, k)
                    elif any(kw in k_lower for kw in ["series", "module", "model", "unit", "inverter", "controller", "server", "melipc"]):
                        if not current_series and is_valid_product_model(k):
                            current_series = k
                        if v:
                            current_models_text += f", {v}"
            else:
                table_headers = []
                prev_cells = []

            # Look for direct PDF links
            if ".pdf" in line_str.lower() and not bulletin_link:
                url_m = re.search(r'\((https?://[^\s\)]+\.pdf)\)', line_str)
                if url_m:
                    bulletin_link = url_m.group(1)

        # Flush final item
        flush_records()
        return products
