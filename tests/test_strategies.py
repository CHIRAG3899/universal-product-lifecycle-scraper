"""
Unit tests for Pluggable Scraping Strategy Framework (scraper.strategies).
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scraper.state import VendorRunState
from scraper.strategies import (
    DomTableStrategy,
    RestApiStrategy,
    SearchPortalStrategy,
    SitemapStrategy,
    get_strategy,
)
from scraper.strategies.base import (
    sanitize_alias_text,
    split_model_identifiers,
)
from scraper.strategies.search_portal import extract_model_family_prefix


class TestStrategiesFramework(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name)
        self.state = VendorRunState("test_vendor", state_dir=self.state_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_strategy_resolution(self):
        self.assertIsInstance(get_strategy("search_portal"), SearchPortalStrategy)
        self.assertIsInstance(get_strategy("lifecycle_search"), SearchPortalStrategy)
        self.assertIsInstance(get_strategy("dom_table"), DomTableStrategy)
        self.assertIsInstance(get_strategy("html_table"), DomTableStrategy)
        self.assertIsInstance(get_strategy("table"), DomTableStrategy)
        self.assertIsInstance(get_strategy("sitemap"), SitemapStrategy)
        self.assertIsInstance(get_strategy("sitemap_index"), SitemapStrategy)
        self.assertIsInstance(get_strategy("rest_api"), RestApiStrategy)
        self.assertIsInstance(get_strategy("json_api"), RestApiStrategy)
        # Default fallback
        self.assertIsInstance(get_strategy("unknown_strat"), DomTableStrategy)
        self.assertIsInstance(get_strategy(None), DomTableStrategy)

    def test_sanitize_alias_text(self):
        # Removes double quotes, single quotes, backticks, and smart quotes
        self.assertEqual(
            sanitize_alias_text('""Rotary Disconnect MPCB/MCP S Handle, R/Y""'),
            "Rotary Disconnect MPCB/MCP S Handle - R/Y",
        )
        self.assertEqual(
            sanitize_alias_text("‘Smart Quote’ and “Double Quote” and `backtick`"),
            "Smart Quote and Double Quote and backtick",
        )
        self.assertIsNone(sanitize_alias_text(""))
        self.assertIsNone(sanitize_alias_text(None))

    def test_split_model_identifiers(self):
        # Commas outside parentheses split into distinct models
        self.assertEqual(
            split_model_identifiers("MS220-8-HW, MS220-8P-HW"),
            ["MS220-8-HW", "MS220-8P-HW"],
        )
        # Slashes split distinct models
        self.assertEqual(
            split_model_identifiers("PowerEdge R740 / R740xd"),
            ["PowerEdge R740", "R740xd"],
        )
        # Commas INSIDE parentheses are preserved
        self.assertEqual(
            split_model_identifiers("LIC-MI-L (1D, 1YR, 3YR, 5YR, 7YR, 10YR)"),
            ["LIC-MI-L (1D, 1YR, 3YR, 5YR, 7YR, 10YR)"],
        )
        # Empty/whitespace
        self.assertEqual(split_model_identifiers(""), [])
        self.assertEqual(split_model_identifiers(None), [])

    def test_extract_model_family_prefix(self):
        # Rockwell catalog SKUs
        self.assertEqual(extract_model_family_prefix("1756-L85E"), "1756")
        self.assertEqual(extract_model_family_prefix("PL-CCP153"), "PL-CCP")
        self.assertEqual(extract_model_family_prefix("20-COMM-E"), "20-")
        self.assertEqual(extract_model_family_prefix("140M-C2E-B10"), "140M")
        self.assertEqual(extract_model_family_prefix("MSSP-200"), "MSSP")
        self.assertEqual(extract_model_family_prefix("700-CF400EJ"), "700-")
        # Leading alphanumeric block
        self.assertEqual(extract_model_family_prefix("C9300-48P"), "C9300")
        self.assertEqual(extract_model_family_prefix("6ES7515-2AM01-0AB0"), "6ES7515")
        # Empty/whitespace
        self.assertIsNone(extract_model_family_prefix(""))
        self.assertIsNone(extract_model_family_prefix(None))

    def test_create_sanitized_record_valid_model(self):
        strat = DomTableStrategy()
        rec = strat.create_sanitized_record(
            vendor_name="Rockwell Automation",
            raw_model="PL-CCP153",
            raw_alias="ControlLogix Maintenance & TS",
            raw_status="Active",
            raw_date="2026-10-01",
            source_url="https://example.com/pdp",
            category="Industrial Automation",
            raw_replacement="PL-CCP154",
        )
        self.assertIsNotNone(rec)
        assert rec is not None
        self.assertEqual(rec.vendor_name, "Rockwell Automation")
        self.assertEqual(rec.model_name, "PL-CCP153")
        self.assertNotIn('"', rec.aliases)
        self.assertEqual(rec.status, "Active")
        self.assertEqual(rec.stage_date_utc, "2026-10-01T00:00:00Z")
        self.assertEqual(rec.replacement, "PL-CCP154")

    def test_create_sanitized_record_rejects_category_and_boilerplate(self):
        strat = DomTableStrategy()
        # Reject generic marketing category
        rec_noise = strat.create_sanitized_record(
            vendor_name="Rockwell Automation",
            raw_model="Human Machine Interface",
            raw_alias="Generic HMI",
            raw_status="Active",
            raw_date=None,
            source_url="https://example.com/pdp",
        )
        self.assertIsNone(rec_noise)

        # Reject boilerplate replacement text
        rec_boiler = strat.create_sanitized_record(
            vendor_name="Rockwell Automation",
            raw_model="1756-L71",
            raw_alias="ControlLogix 5570",
            raw_status="Discontinued",
            raw_date="2025-01-01",
            source_url="https://example.com/pdp",
            raw_replacement="CONTACT REPAIR & REPLACEMENT",
        )
        self.assertIsNotNone(rec_boiler)
        assert rec_boiler is not None
        # Replacement should be cleaned/rejected
        self.assertIsNone(rec_boiler.replacement)

    def test_rest_api_strategy_parsing(self):
        strat = RestApiStrategy()
        mock_response_data = b"""[
            {"modelName": "WS-C2960X-48FPS-L", "productName": "Catalyst 2960-X Switch", "lifecycleStatus": "End of Sale", "endDate": "2025-10-31", "replacementModel": "C9200L-48P-4G-E"},
            {"modelName": "WS-C3850-24P", "productName": "Catalyst 3850", "lifecycleStatus": "End of Life", "endDate": "2026-12-31", "replacementModel": "C9300-24P"}
        ]"""

        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_response_data
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            import asyncio
            records = asyncio.run(strat.execute(
                entry_point={"url": "https://api.cisco.com/v1/eol", "field_map": {}},
                vendor_cfg={"name": "Cisco Systems", "id": "cisco"},
                crawler=None,
                state=self.state,
            ))

            self.assertEqual(len(records), 2)
            self.assertEqual(records[0].model_name, "WS-C2960X-48FPS-L")
            self.assertIn("End of Sale", records[0].status)
            self.assertEqual(records[0].replacement, "C9200L-48P-4G-E")
            self.assertEqual(records[1].model_name, "WS-C3850-24P")


if __name__ == "__main__":
    unittest.main()
