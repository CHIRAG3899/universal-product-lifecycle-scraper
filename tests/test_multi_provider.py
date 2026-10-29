"""
Unit Tests for Multi-Provider LLM Abstraction Layer.
Validates provider normalization, model resolution, multi-provider initialization,
and mock extraction across OpenAI, Anthropic Claude, Azure OpenAI, AWS Bedrock, and Ollama.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.gemini_extractor import GeminiExtractor, LLMExtractor, UniversalAIExtractor
from scraper.models import ProductRecord
from scraper.providers import (
    detect_provider_from_model,
    normalize_provider_name,
    resolve_provider_and_model,
)


class TestMultiProvider(unittest.TestCase):

    def test_provider_normalization(self):
        self.assertEqual(normalize_provider_name("claude"), "anthropic")
        self.assertEqual(normalize_provider_name("Anthropic"), "anthropic")
        self.assertEqual(normalize_provider_name("aws"), "bedrock")
        self.assertEqual(normalize_provider_name("bedrock"), "bedrock")
        self.assertEqual(normalize_provider_name("azure_openai"), "azure")
        self.assertEqual(normalize_provider_name("local"), "ollama")
        self.assertEqual(normalize_provider_name("gemini"), "gemini")
        self.assertEqual(normalize_provider_name("openai"), "openai")
        self.assertEqual(normalize_provider_name(""), "auto")
        self.assertEqual(normalize_provider_name(None), "auto")

    def test_detect_provider_from_model(self):
        self.assertEqual(detect_provider_from_model("gpt-4o"), "openai")
        self.assertEqual(detect_provider_from_model("gpt-4o-mini"), "openai")
        self.assertEqual(detect_provider_from_model("o1-preview"), "openai")
        self.assertEqual(detect_provider_from_model("claude-3-5-sonnet-20241022"), "anthropic")
        self.assertEqual(detect_provider_from_model("claude-3-haiku"), "anthropic")
        self.assertEqual(detect_provider_from_model("azure/my-gpt4-deployment"), "azure")
        self.assertEqual(detect_provider_from_model("bedrock/anthropic.claude-v2"), "bedrock")
        self.assertEqual(detect_provider_from_model("gemini-3.5-flash-lite"), "gemini")
        self.assertEqual(detect_provider_from_model("ollama/llama3.2"), "ollama")
        self.assertIsNone(detect_provider_from_model("unknown-custom-model"))

    def test_resolve_provider_and_model_defaults(self):
        prov, model, key = resolve_provider_and_model(provider="gemini")
        self.assertEqual(prov, "gemini")
        self.assertIn("gemini", model.lower())

        prov_oai, model_oai, _ = resolve_provider_and_model(provider="openai")
        self.assertEqual(prov_oai, "openai")
        self.assertEqual(model_oai, "gpt-4o-mini")

        prov_ant, model_ant, _ = resolve_provider_and_model(provider="anthropic")
        self.assertEqual(prov_ant, "anthropic")
        self.assertIn("claude", model_ant.lower())

    def test_resolve_provider_inferred_from_model(self):
        prov, model, _ = resolve_provider_and_model(model="gpt-4o")
        self.assertEqual(prov, "openai")
        self.assertEqual(model, "gpt-4o")

        prov_c, model_c, _ = resolve_provider_and_model(model="claude-3-5-sonnet-20241022")
        self.assertEqual(prov_c, "anthropic")
        self.assertEqual(model_c, "claude-3-5-sonnet-20241022")

    def test_aliases_equality(self):
        self.assertIs(UniversalAIExtractor, GeminiExtractor)
        self.assertIs(LLMExtractor, GeminiExtractor)

    def test_multi_provider_instantiation(self):
        # OpenAI
        ext_openai = UniversalAIExtractor(provider="openai", api_key="sk-test12345", model_name="gpt-4o")
        self.assertEqual(ext_openai.provider, "openai")
        self.assertEqual(ext_openai.model_name, "gpt-4o")
        self.assertTrue(ext_openai.is_configured())

        # Claude
        ext_claude = UniversalAIExtractor(provider="anthropic", api_key="sk-ant-test123", model_name="claude-3-5-haiku-20241022")
        self.assertEqual(ext_claude.provider, "anthropic")
        self.assertTrue(ext_claude.is_configured())

        # Ollama (no key required)
        ext_ollama = UniversalAIExtractor(provider="ollama", model_name="ollama/llama3.2")
        self.assertEqual(ext_ollama.provider, "ollama")
        self.assertTrue(ext_ollama.is_configured())

    @patch("litellm.completion")
    def test_test_connection_non_gemini_success(self, mock_completion):
        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "OK"
        mock_resp.choices = [mock_choice]
        mock_completion.return_value = mock_resp

        ext = UniversalAIExtractor(provider="openai", api_key="sk-test", model_name="gpt-4o-mini")
        success, msg = ext.test_connection()
        self.assertTrue(success)
        self.assertIn("Connection successful", msg)
        self.assertIn("openai", msg.lower())

    @patch("litellm.completion")
    def test_extract_from_markdown_with_openai_mock(self, mock_completion):
        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_json_payload = {
            "vendor_name": "Rockwell Automation",
            "products": [
                {
                    "vendor_name": "Rockwell Automation",
                    "model_name": "1756-L71",
                    "status": "End of Life",
                    "stage_date_utc": "2025-12-31T00:00:00Z",
                    "category": "PLC Controller",
                    "replacement": "1756-L81E",
                    "notes": "Migrate to ControlLogix 5580",
                    "bulletin_code": "BULLETIN-2025-12",
                }
            ],
        }
        import json
        mock_choice.message.content = json.dumps(mock_json_payload)
        mock_resp.choices = [mock_choice]
        mock_completion.return_value = mock_resp

        ext = UniversalAIExtractor(provider="openai", api_key="sk-test", model_name="gpt-4o-mini")
        records = ext.extract_from_markdown(
            markdown_chunk="Notice: 1756-L71 End of Life December 31, 2025. Successor 1756-L81E.",
            source_url="https://rockwellautomation.com/support/eol",
        )

        self.assertEqual(len(records), 1)
        self.assertIsInstance(records[0], ProductRecord)
        self.assertEqual(records[0].model_name, "1756-L71")
        self.assertEqual(records[0].status, "End of Life")
        self.assertEqual(records[0].stage_date_utc, "2025-12-31T00:00:00Z")
        self.assertEqual(records[0].replacement, "1756-L81E")


if __name__ == "__main__":
    unittest.main()
