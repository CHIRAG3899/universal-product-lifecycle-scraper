---
name: gemini-llm-tuning
description: >-
  Use this skill when modifying Gemini prompts, configuring Google GenAI models, resolving
  API rate limits (HTTP 429), fixing 404 model deprecation errors, or tuning structured JSON extraction.
---

# Google Gemini LLM Tuning & Failover Runbook

This skill outlines guidelines and troubleshooting steps for configuring, tuning, and handling errors when interacting with Google Gemini via the official `google-genai` SDK in [`scraper/gemini_extractor.py`](file:///c:/Code/AI%20scraper/scraper/gemini_extractor.py).

---

## 🔑 Model Support & Probing Order

Google AI Studio periodically updates available models and may return `404 NOT_FOUND` for older or deprecated models on newer accounts.

### Prioritized Probing Order:
1. `gemini-3.5-flash-lite` (Universal production default, fast, prompt caching enabled)
2. `gemini-flash-lite-latest` (Rolling production flash-lite endpoint)
3. `gemini-3.5-flash` (Standard production flash)
4. `gemini-flash-latest` (Rolling production standard flash)

If a model returns 404, the extractor automatically cycles through candidates and updates `.env`.

---

## 🛠️ Key Handling & Setup

To validate or update the Gemini API key interactively:
```bash
python setup_key.py
# Or via CLI flag:
python cli.py --setup-key
```

### Clean Environment Isolation
In unit tests, explicitly pass `api_key=""` to test unconfigured/deterministic fallbacks without picking up live keys from `.env`:
```python
extractor = GeminiExtractor(api_key="")
self.assertFalse(extractor.is_configured())
```

---

## 🛡️ Response Sanitization (Markdown Code Fences)

When Gemini occasionally wraps JSON responses in markdown code fences:
```text
```json
{
  "products": [...]
}
```
```
Always strip the surrounding code fences prior to `json.loads()` to avoid `JSONDecodeError`. This is built into `GeminiExtractor.extract_from_markdown()`.

---

## 🎯 Extraction Prompt Invariants & 100% Coverage Rules

The system prompt in [`scraper/gemini_extractor.py`](file:///c:/Code/AI%20scraper/scraper/gemini_extractor.py) (`EXTRACTION_SYSTEM_INSTRUCTION`) strictly enforces:
1. **Zero Status Limitations**: Vendors do NOT share a fixed status list. The extractor captures the exact vendor milestone (*Phase-Out Product, Delivery Release, Announced Discontinuation, Product Cancellation, End of Sale, Last Date of Support, Classic, Limited, Obsolete, Active Mature, Stop Shipment, Repair Termination*). Never force stages into an artificial 3-stage whitelist.
2. **Strict Mandatory 4-Field Invariant**: `vendor_name`, `model_name`, `status`, and `stage_date_utc` must never be null. If a table or paragraph states a discontinuation notice without a row-level date, the crawler automatically hydrates the date from the circular publication date or crawl snapshot timestamp.
3. **Model Suffix & Range Unpacking**: Pre-processing via `split_models()` expands:
   - Trailing suffix fragments: `FX2N-16MR/ES, -16MT/ES` -> `FX2N-16MR/ES`, `FX2N-16MT/ES`
   - Numeric ranges: `1756-L61 to 1756-L63` -> `1756-L61`, `1756-L62`, `1756-L63`
   - Slashes & commas: `ModelA / ModelB` -> `ModelA`, `ModelB`
4. **PDF Notice Ingestion**: Technical bulletins and obsolescence PDFs linked from portal tables are ingested via `extract_text_from_pdf_bytes()`, ensuring no hardware announced exclusively in PDF releases is missed.

---

## 💰 Google Native Token & Cost Optimization Strategies

When scraping repetitive web structures, leverage Google's native API features to slash token costs:

### 1. Cap Thinking Budget (`thinking_config`)
- **Cost Impact**: Eliminates expensive internal reasoning output tokens on Flash models (`gemini-2.0-flash`, `gemini-2.5-flash`, `gemini-3.8-flash`).
- **Why**: Output tokens are billed at 4-8x input rates. For deterministic schema extraction, verbose chain-of-thought is unnecessary overhead.
- **Config**: Set `thinking_budget=0` (or CLI `--thinking-budget 0`, env `GEMINI_THINKING_BUDGET=0`).

### 2. Native Prompt Caching (`CachedContent` & `system_instruction`)
- **Cost Impact**: Cuts input token costs by **up to 90%** on repetitive prompts.
- **Why**: AI crawlers repeatedly inject invariant extraction rules, schema definitions, and vendor profiles.
- **Config**: Invariant extraction instructions are separated into `system_instruction` in `GenerateContentConfig`. When portal documentation or catalogs exceed 32k tokens, explicit caching via `client.caches.create()` reuses context across calls (CLI `--prompt-caching`, env `GEMINI_ENABLE_PROMPT_CACHING=true`).

### 3. Asynchronous Batch Mode (`client.batches`)
- **Cost Impact**: **50% discount** on BOTH input and output tokens across bulk extraction workloads.
- **Why**: Lifecycle obsolescence audits do not require millisecond interactive latency.
- **Config**: Enable via CLI flag `--batch-mode` or env `GEMINI_BATCH_MODE=true`. `GeminiExtractor.extract_batch()` packages requests into `InlinedRequest` batch jobs polled until completion.
