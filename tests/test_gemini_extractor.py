"""
Unit & Edge Case Tests for scraper/gemini_extractor.py
Validates GeminiExtractor initialization, unconfigured fallback routing, and deterministic table parsing.
"""

import json
import sys
import unittest
import unittest.mock
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.gemini_extractor import GeminiExtractor


class TestGeminiExtractor(unittest.TestCase):

    def test_unconfigured_extractor_state(self):
        extractor = GeminiExtractor(api_key="")
        self.assertFalse(extractor.is_configured())

        success, msg = extractor.test_connection()
        self.assertFalse(success)
        self.assertIn("not configured", msg.lower())

    def test_placeholder_key_treated_as_unconfigured(self):
        extractor = GeminiExtractor(api_key="your_gemini_api_key_here")
        self.assertFalse(extractor.is_configured())

    def test_fallback_rule_based_extraction_markdown_table(self):
        extractor = GeminiExtractor(api_key="")
        sample_markdown = """
## GT25-WLAN - Wireless Unit
- **Models**: GT25-WLAN
- **End of Life**: 2023-08-17
- **Last Time Buy**: 2025-01-28
- **End of Service**: 2032-01-28
- **Document**: EOL-HMI-230817.pdf

## MI3321G-W Industrial PC
- **Models**: MI3321G-W
- **End of Life**: 2025-10-29
- **Last Time Buy**: 2026-09-30
- **End of Service**: 2031-10-31
- **Document**: EOL-IPC-251029.pdf

## Performance Cookies
- **Models**: Performance Cookies
- **Status**: Active
"""
        records = extractor.fallback_rule_based_extraction(
            text=sample_markdown,
            source_url="https://se-fa.mitsubishielectric.com/fa/se_en/support/eol",
            default_vendor="Mitsubishi Electric"
        )

        self.assertTrue(len(records) > 0)
        # Verify that cookie noise was discarded
        models = [p.model_name for p in records]
        self.assertIn("GT25-WLAN", models)
        self.assertIn("MI3321G-W", models)
        self.assertNotIn("Performance Cookies", models)

        # Verify 1 record per stage explosion (MI3321G-W has 3 stages: EOL, LTB, EOS)
        mi_records = [p for p in records if p.model_name == "MI3321G-W"]
        self.assertEqual(len(mi_records), 3)

        stages = [p.status or "" for p in mi_records]
        self.assertTrue(any("End of Life" in s for s in stages))
        self.assertTrue(any("Last Time Buy" in s for s in stages))
        self.assertTrue(any("End of Service" in s for s in stages))

    def test_fallback_extraction_empty_or_no_tables(self):
        extractor = GeminiExtractor(api_key="")
        records_empty = extractor.fallback_rule_based_extraction("", default_vendor="Siemens")
        self.assertEqual(len(records_empty), 0)

        records_no_tables = extractor.fallback_rule_based_extraction(
            "Just some random paragraph without any tables or part numbers.",
            default_vendor="Siemens"
        )
        self.assertEqual(len(records_no_tables), 0)

    def test_extract_from_markdown_delegation_when_unconfigured(self):
        extractor = GeminiExtractor(api_key="")
        sample_markdown = """
## FX5-EIP Module
- **Models**: FX5-EIP
- **End of Life**: 2026-03-31
"""
        records = extractor.extract_from_markdown(
            sample_markdown,
            source_url="https://mitsubishielectric.com/support"
        )
        self.assertTrue(len(records) >= 1)
        self.assertEqual(records[0].model_name, "FX5-EIP")

    def test_fallback_multi_column_table_extraction(self):
        """Verifies multi-column matrix table parsing and 1 record per stage explosion."""
        extractor = GeminiExtractor(api_key="")
        markdown_table = """
| Model / Part Number | Series | End of Sale Date | End of Support Date | Recommended Replacement |
| --- | --- | --- | --- | --- |
| FX2N-16MR | FX Series | 2024-03-31 | 2031-03-31 | FX3G-14MR |
| Q02UCPU | MELSEC-Q | 2025-06-30 | 2032-06-30 | Q03UDECPU |
"""
        records = extractor.fallback_rule_based_extraction(markdown_table, default_vendor="Mitsubishi Electric")
        self.assertEqual(len(records), 4)  # 2 models x 2 stage columns

        fx_records = [r for r in records if r.model_name == "FX2N-16MR"]
        stages = [(r.status or "").lower() for r in fx_records]
        self.assertTrue(any("sale" in s for s in stages))
        self.assertTrue(any("support" in s for s in stages))
        self.assertEqual(fx_records[0].replacement, "FX3G-14MR")

    def test_gemini_json_code_fence_stripping(self):
        """Verifies that markdown code fences ```json ... ``` are cleanly stripped from LLM output."""
        extractor = GeminiExtractor(api_key="mock_key_123")
        extractor.client = unittest.mock.MagicMock()

        mock_payload = {
            "vendor_name": "Schneider Electric",
            "detected_language": "en",
            "products": [
                {
                    "vendor_name": "Schneider Electric",
                    "model_name": "TM221CE16R",
                    "status": "End of Life (EOL)",
                    "stage": "End of Life (EOL)",
                    "stage_date_utc": "2026-12-31T00:00:00Z",
                    "source_url": "https://se.com/support",
                    "replacement": "TM241CE24R",
                    "metadata": {}
                }
            ]
        }
        mock_response = unittest.mock.MagicMock()
        mock_response.text = f"```json\n{json.dumps(mock_payload)}\n```"
        extractor.client.models.generate_content.return_value = mock_response

        records = extractor.extract_from_markdown("sample text", source_url="https://se.com/eol")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].model_name, "TM221CE16R")
        self.assertEqual(records[0].vendor_name, "Schneider Electric")
        self.assertEqual(records[0].stage_date_utc, "2026-12-31T00:00:00Z")

    def test_clean_token_efficient_markdown(self):
        """Verifies that markdown table noise, HTML comments, and extra newlines are trimmed."""
        from scraper.gemini_extractor import clean_token_efficient_markdown

        raw = """
        <!-- navigation comment -->
        ## Mitsubishi EOL

        | Model Name         | Status        | Date       |
        |:-------------------|:--------------|:-----------|
        | FX2N-16MR          | Discontinued  | 2024-03-31 |



        <!-- footer comment -->
        """
        cleaned = clean_token_efficient_markdown(raw)
        self.assertNotIn("<!-- navigation comment -->", cleaned)
        self.assertNotIn("<!-- footer comment -->", cleaned)
        self.assertIn("|---|---|---|", cleaned)
        self.assertNotIn("\n\n\n", cleaned)

    def test_thinking_budget_configuration(self):
        """Verifies ThinkingConfig is generated with budget cap to eliminate reasoning token billing."""
        extractor = GeminiExtractor(api_key="test_key", thinking_budget=0)
        cfg = extractor._build_thinking_config()
        self.assertIsNotNone(cfg)
        assert cfg is not None
        self.assertEqual(cfg.thinking_budget, 0)
        self.assertFalse(cfg.include_thoughts)

        # Unconstrained thinking
        extractor_none = GeminiExtractor(api_key="test_key", thinking_budget=-1)
        self.assertIsNone(extractor_none._build_thinking_config())

    def test_prompt_cache_creation_and_fallback(self):
        """Verifies PromptCache creation and graceful fallback below 32k threshold."""
        extractor = GeminiExtractor(api_key="test_key", enable_prompt_caching=True)
        extractor.client = unittest.mock.MagicMock()

        # Simulate successful cache creation
        mock_cache = unittest.mock.MagicMock()
        mock_cache.name = "cachedContents/test_cache_123"
        extractor.client.caches.create.return_value = mock_cache

        cache_name = extractor.get_or_create_prompt_cache()
        self.assertEqual(cache_name, "cachedContents/test_cache_123")
        self.assertTrue(extractor.token_metrics["prompt_cache_active"])

        # Release cache
        extractor.delete_prompt_cache()
        extractor.client.caches.delete.assert_called_once_with(name="cachedContents/test_cache_123")
        self.assertIsNone(extractor._active_cache_name)

        # Simulate below 32k threshold error -> smooth fallback
        extractor.client.caches.create.side_effect = Exception("Total number of tokens in cached content must be at least 32768.")
        fallback_cache = extractor.get_or_create_prompt_cache()
        self.assertIsNone(fallback_cache)

    def test_batch_extraction_job_submission(self):
        """Verifies that create_batch_extraction_job formats InlinedRequests and submits BatchJob."""
        extractor = GeminiExtractor(api_key="test_key", batch_mode=True)
        extractor.client = unittest.mock.MagicMock()

        mock_batch_job = unittest.mock.MagicMock()
        mock_batch_job.name = "batchJobs/lifecycle_batch_456"
        extractor.client.batches.create.return_value = mock_batch_job

        chunks = [
            {"markdown_chunk": "| Model | Date |\n|---|---|\n| FX3U | 2025-01-01 |", "source_url": "https://mitsubishielectric.com/eol"}
        ]
        job_name = extractor.create_batch_extraction_job(chunks)
        self.assertEqual(job_name, "batchJobs/lifecycle_batch_456")
        extractor.client.batches.create.assert_called_once()
        self.assertEqual(extractor.token_metrics["batch_calls"], 1)

    def test_batch_job_polling_and_parsing(self):
        """Verifies polling a succeeded batch job returns parsed ProductRecords."""
        extractor = GeminiExtractor(api_key="test_key")
        extractor.client = unittest.mock.MagicMock()

        mock_payload = {
            "vendor_name": "Siemens",
            "detected_language": "en",
            "products": [
                {
                    "vendor_name": "Siemens",
                    "model_name": "6ES7214-1AG40-0XB0",
                    "status": "End of Life (EOL)",
                    "stage": "End of Life (EOL)",
                    "stage_date_utc": "2027-10-01T00:00:00Z",
                    "source_url": "https://siemens.com/lifecycle",
                    "replacement": "6ES7214-1AG40-0XB1",
                    "metadata": {}
                }
            ]
        }

        mock_inlined = unittest.mock.MagicMock()
        mock_inlined.response.text = json.dumps(mock_payload)

        mock_job = unittest.mock.MagicMock()
        mock_job.state = "JOB_STATE_SUCCEEDED"
        mock_job.dest.inlined_responses = [mock_inlined]
        extractor.client.batches.get.return_value = mock_job

        results = extractor.poll_batch_job("batchJobs/lifecycle_batch_456", poll_interval=0, timeout=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].model_name, "6ES7214-1AG40-0XB0")
        self.assertEqual(results[0].vendor_name, "Siemens")

    def test_suffix_and_range_unpacking(self):
        """Verifies suffix expansion (-16MT/ES), range expansion, and slash unbundling."""
        extractor = GeminiExtractor(api_key="")
        md = """
## Discontinued Controllers
- **Models**: FX2N-16MR/ES, -16MT/ES, -32MR/ES
- **Phase-Out**: 2024-03-31
- **Models**: CP1E-E20DR-A / CP1E-N20DR-A
"""
        records = extractor.fallback_rule_based_extraction(md, default_vendor="Mitsubishi Electric")
        models = [r.model_name for r in records]
        self.assertIn("FX2N-16MR/ES", models)
        self.assertIn("FX2N-16MT/ES", models)
        self.assertIn("FX2N-32MR/ES", models)
        self.assertIn("CP1E-E20DR-A", models)
        self.assertIn("CP1E-N20DR-A", models)

    def test_mandatory_fields_and_bulletin_date_recovery(self):
        """Verifies models with bulletin codes recover exact UTC dates and enforce mandatory non-null invariant."""
        extractor = GeminiExtractor(api_key="")
        md = """
## Discontinued Legacy Modules
- **Bulletin**: EOL-PLC-240408-1961-SCA
- A1SJCPU
- A2USHCPU-S1
- A3NCPU
"""
        records = extractor.fallback_rule_based_extraction(md, default_vendor="Mitsubishi Electric")
        self.assertEqual(len(records), 3)
        models = [r.model_name for r in records]
        self.assertIn("A1SJCPU", models)
        self.assertIn("A2USHCPU-S1", models)
        self.assertIn("A3NCPU", models)
        for r in records:
            self.assertIsNotNone(r.stage_date_utc)
            self.assertEqual(r.stage_date_utc, "2024-04-08T00:00:00Z")
            self.assertEqual(r.status, "Discontinued")
            self.assertEqual(r.vendor_name, "Mitsubishi Electric")

        # Also verify that models completely lacking any date or bulletin code are dropped (no null allowed)
        md_no_date = """
## Completely Undated Header
- UNDATED-001
"""
        records_no_date = extractor.fallback_rule_based_extraction(md_no_date, default_vendor="Mitsubishi Electric")
        self.assertEqual(len(records_no_date), 0)

    def test_extract_text_from_pdf_bytes_helper(self):
        """Verifies extract_text_from_pdf_bytes handles empty or corrupt PDF bytes gracefully."""
        from scraper.gemini_extractor import extract_text_from_pdf_bytes
        self.assertEqual(extract_text_from_pdf_bytes(b""), "")
        self.assertEqual(extract_text_from_pdf_bytes(b"not a valid pdf"), "")


if __name__ == "__main__":
    unittest.main()
