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

from scraper.ai_extractor import GeminiExtractor, LLMExtractor, UniversalAIExtractor
from scraper.models import ProductRecord
from scraper.providers import (
    call_llm_completion,
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

    @patch("requests.post")
    def test_direct_http_rest_completion_openai(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"products": []}'}}]
        }
        mock_post.return_value = mock_resp

        # Force litellm failure to test HTTP REST fallback
        with patch.dict("sys.modules", {"litellm": None}):
            out = call_llm_completion(
                provider="openai",
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "test"}],
                api_key="sk-test",
            )
            self.assertEqual(out, '{"products": []}')
            mock_post.assert_called_once()
            call_url = mock_post.call_args[0][0]
            self.assertIn("api.openai.com", call_url)

    @patch("requests.post")
    def test_direct_http_rest_completion_anthropic(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"text": '{"vendor_name": "Siemens", "products": []}'}]
        }
        mock_post.return_value = mock_resp

        with patch.dict("sys.modules", {"litellm": None}):
            out = call_llm_completion(
                provider="anthropic",
                model="claude-3-5-haiku-20241022",
                messages=[{"role": "user", "content": "test"}],
                api_key="sk-ant-test",
            )
            self.assertEqual(out, '{"vendor_name": "Siemens", "products": []}')
            mock_post.assert_called_once()
            call_url = mock_post.call_args[0][0]
            self.assertIn("api.anthropic.com", call_url)

    def test_auto_detection_from_key_format(self):
        prov_ant, _, key_ant = resolve_provider_and_model(api_key="sk-ant-testkey123")
        self.assertEqual(prov_ant, "anthropic")
        self.assertEqual(key_ant, "sk-ant-testkey123")

        prov_oai, _, key_oai = resolve_provider_and_model(api_key="sk-proj-testkey456")
        self.assertEqual(prov_oai, "openai")
        self.assertEqual(key_oai, "sk-proj-testkey456")

        prov_gem, _, key_gem = resolve_provider_and_model(api_key="AIzaSyTestKey789")
        self.assertEqual(prov_gem, "gemini")
        self.assertEqual(key_gem, "AIzaSyTestKey789")

        prov_bed, _, key_bed = resolve_provider_and_model(api_key="AKIAIOSFODNN7EXAMPLE")
        self.assertEqual(prov_bed, "bedrock")
        self.assertEqual(key_bed, "AKIAIOSFODNN7EXAMPLE")

    def test_azure_and_bedrock_configuration(self):
        ext_az = UniversalAIExtractor(
            provider="azure",
            api_key="azure-test-key",
            api_base="https://myresource.openai.azure.com",
            model_name="azure/gpt-4o",
        )
        self.assertEqual(ext_az.provider, "azure")
        self.assertTrue(ext_az.is_configured())

        ext_bed = UniversalAIExtractor(
            provider="bedrock",
            api_key="AKIAIOSFODNN7EXAMPLE",
            model_name="bedrock/anthropic.claude-3-5-haiku-20241022-v1:0",
        )
        self.assertEqual(ext_bed.provider, "bedrock")
        self.assertTrue(ext_bed.is_configured())

    def test_direct_openai_client_extraction_mock(self):
        import json
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_payload = {
            "vendor_name": "Siemens",
            "products": [
                {
                    "vendor_name": "Siemens",
                    "model_name": "6ES7511-1AK02-0AB0",
                    "status": "Phase-Out Product",
                    "stage_date_utc": "2026-09-30T00:00:00Z",
                    "category": "PLC CPU",
                    "replacement": "6ES7511-1AL03-0AB0",
                    "notes": "Migration bulletin available",
                    "bulletin_code": "SIEP-2026-09",
                }
            ],
        }
        mock_choice.message.content = json.dumps(mock_payload)
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_resp

        ext = UniversalAIExtractor(provider="openai", api_key="sk-test", model_name="gpt-4o-mini")
        ext.client = mock_client

        records = ext.extract_from_markdown(
            markdown_chunk="Siemens 6ES7511-1AK02-0AB0 Phase-Out Product on 2026-09-30.",
            source_url="https://sieportal.siemens.com/lifecycle",
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].model_name, "6ES7511-1AK02-0AB0")
        self.assertEqual(records[0].vendor_name, "Siemens")
        mock_client.chat.completions.create.assert_called_once()

    def test_pre_commit_config_path_validity(self):
        """Verifies that .pre-commit-config.yaml references an existing script path without outdated prefixes."""
        pre_commit_yaml = BASE_DIR / ".pre-commit-config.yaml"
        self.assertTrue(pre_commit_yaml.exists())
        content = pre_commit_yaml.read_text(encoding="utf-8")
        self.assertNotIn("AI scraper", content, "Stale folder 'AI scraper' should not be in .pre-commit-config.yaml")
        self.assertIn("python scripts/pre_commit_check.py", content)

    def test_requirements_contain_multi_provider_dependencies(self):
        """Verifies that requirements.txt declares all multi-provider SDKs and runtime tools."""
        req_file = BASE_DIR / "requirements.txt"
        self.assertTrue(req_file.exists())
        content = req_file.read_text(encoding="utf-8").lower()
        required_packages = [
            "google-genai",
            "openai",
            "litellm",
            "pydantic",
            "crawl4ai",
            "playwright",
            "requests",
            "pyyaml",
            "pandas",
            "pypdf",
        ]
        for pkg in required_packages:
            self.assertIn(pkg, content, f"Missing {pkg} in requirements.txt")

    def test_ai_extractor_without_google_genai(self):
        """Verifies that UniversalAIExtractor works when google.genai is absent."""
        import scraper.ai_extractor as mod
        with patch.object(mod, "genai", None), patch.object(mod, "types", None):
            ext = UniversalAIExtractor(provider="openai", api_key="sk-test", model_name="gpt-4o-mini")
            self.assertEqual(ext.provider, "openai")
            self.assertIsNone(ext._build_thinking_config())
            self.assertIsNone(ext.get_or_create_prompt_cache())


if __name__ == "__main__":
    unittest.main()
