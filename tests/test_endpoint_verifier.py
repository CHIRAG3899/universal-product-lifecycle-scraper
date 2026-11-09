#!/usr/bin/env python3
"""
Unit and Integration Tests for Endpoint & Pattern Verification Engine.
Tests EndpointProber, PatternAnalyzer, LLMEndpointVerifier, and YAML enrichment.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from scripts.verify_and_enrich_endpoints import (
    EndpointProber,
    LLMEndpointVerifier,
    PatternAnalyzer,
    enrich_and_update_vendor_yaml,
)


class TestEndpointVerifier(unittest.TestCase):
    """Test suite for live endpoint and regex pattern verification."""

    def setUp(self) -> None:
        self.prober = EndpointProber(timeout=2.0)
        self.verifier = LLMEndpointVerifier(enabled=False)  # deterministic test mode

    def test_pattern_analyzer_discovers_product_sku_regex(self) -> None:
        """Verifies PatternAnalyzer discovers accurate model regex from sample URLs."""
        sample_urls = [
            "https://www.rockwellautomation.com/en-us/products/details.1756-L83E.html",
            "https://www.rockwellautomation.com/en-us/products/details.5069-L306ER.html",
            "https://www.rockwellautomation.com/en-us/products/details.2080-LC50-24QBB.html",
            "https://www.rockwellautomation.com/en-us/products/details.2711P-T10C22D9P.html",
        ]
        result = PatternAnalyzer.test_and_discover_patterns(sample_urls)
        self.assertIsNotNone(result["best_pattern"])
        self.assertIn("details", result["best_pattern"])
        self.assertGreaterEqual(result["match_count"], 3)
        self.assertGreaterEqual(result["valid_model_count"], 3)
        self.assertIn("1756-L83E", result["sample_extracted_models"])

    def test_pattern_analyzer_rejects_stopwords(self) -> None:
        """Verifies PatternAnalyzer rejects generic website stopwords and navigation slugs."""
        sample_urls = [
            "https://example.com/company/about-us",
            "https://example.com/legal/privacy",
            "https://example.com/portal/login",
            "https://example.com/support/contact",
        ]
        result = PatternAnalyzer.test_and_discover_patterns(sample_urls)
        # Should not extract stopwords as valid product models
        self.assertEqual(len(result["sample_extracted_models"]), 0)

    def test_deterministic_verification_sitemap_high_confidence(self) -> None:
        """Verifies deterministic verification scores valid sitemaps with models as high confidence."""
        ep_info = {
            "status_code": 200,
            "waf_challenge": None,
            "has_data": True,
            "endpoint_type": "sitemap",
            "valid_model_count": 5,
            "best_pattern": r"details\.([A-Za-z0-9\-_.]+)\.html",
            "sample_urls": ["https://example.com/details.1756-L83E.html"],
            "name": "Rockwell_PDP_Sitemap",
        }
        res = self.verifier.verify_endpoint("rockwell", "Rockwell Automation", "OT", ep_info)
        self.assertTrue(res["is_valid_endpoint"])
        self.assertEqual(res["confidence"], "high")
        self.assertFalse(res["review_needed"])
        self.assertIn("Authoritative XML sitemap", res["confidence_reason"])

    def test_deterministic_verification_waf_challenge_low_confidence(self) -> None:
        """Verifies deterministic verification flags WAF challenged endpoints as low confidence."""
        ep_info = {
            "status_code": 202,
            "waf_challenge": "AWS_WAF_CHALLENGE",
            "has_data": False,
            "endpoint_type": "dom_table",
            "name": "Yokogawa_Discontinued",
        }
        res = self.verifier.verify_endpoint("yokogawa", "Yokogawa", "OT", ep_info)
        self.assertFalse(res["is_valid_endpoint"])
        self.assertEqual(res["confidence"], "low")
        self.assertTrue(res["review_needed"])
        self.assertIn("Blocked by AWS_WAF_CHALLENGE", res["confidence_reason"])

    def test_deterministic_verification_404_low_confidence(self) -> None:
        """Verifies deterministic verification flags 404 endpoints as low confidence with reason."""
        ep_info = {
            "status_code": 404,
            "waf_challenge": None,
            "has_data": False,
            "endpoint_type": "dom_table",
            "error": "Not Found",
            "name": "Broken_Endpoint",
        }
        res = self.verifier.verify_endpoint("vendor_x", "Vendor X", "OT", ep_info)
        self.assertFalse(res["is_valid_endpoint"])
        self.assertEqual(res["confidence"], "low")
        self.assertTrue(res["review_needed"])
        self.assertIn("HTTP reachability failure: status 404", res["confidence_reason"])

    def test_enrich_and_update_vendor_yaml_attributes(self) -> None:
        """Verifies enrich_and_update_vendor_yaml sets confidence, reason, and review_needed."""
        mock_yaml_data = {
            "vendors": {
                "test_vendor": {
                    "id": "test_vendor",
                    "name": "Test Vendor Inc",
                    "sector": "OT",
                    "entry_points": [
                        {
                            "name": "Existing_Table",
                            "url": "https://testvendor.com/lifecycle",
                            "strategy": "dom_table",
                        }
                    ],
                }
            }
        }

        verified_eps = [
            {
                "url": "https://testvendor.com/lifecycle",
                "final_url": "https://testvendor.com/lifecycle",
                "is_redirect": False,
                "is_valid_endpoint": True,
                "endpoint_type": "dom_table",
                "confidence": "low",
                "confidence_reason": "Table requires JavaScript execution to populate rows",
                "suggested_product_pattern": None,
                "review_needed": True,
                "evidence_authority": "official_model_status_or_notice_evidence",
            },
            {
                "url": "https://testvendor.com/sitemap.xml",
                "final_url": "https://testvendor.com/sitemap.xml",
                "is_redirect": False,
                "is_valid_endpoint": True,
                "endpoint_type": "sitemap",
                "confidence": "high",
                "confidence_reason": "Verified product sitemap with 50+ models",
                "suggested_product_pattern": r"/products/([A-Za-z0-9\-]+)",
                "suggested_name": "TestVendor_Product_Sitemap",
                "review_needed": False,
                "evidence_authority": "active_product_catalog_authority",
            },
        ]

        modified = enrich_and_update_vendor_yaml(
            vendor_id="test_vendor",
            vendor_conf=mock_yaml_data["vendors"]["test_vendor"],
            verified_endpoints=verified_eps,
            all_vendors_yaml_data=mock_yaml_data,
        )

        self.assertTrue(modified)
        eps = mock_yaml_data["vendors"]["test_vendor"]["entry_points"]
        self.assertEqual(len(eps), 2)

        # First existing endpoint updated with low confidence
        self.assertEqual(eps[0]["confidence"], "low")
        self.assertTrue(eps[0]["review_needed"])
        self.assertIn("JavaScript execution", eps[0]["confidence_reason"])

        # Second new endpoint added with high confidence
        self.assertEqual(eps[1]["confidence"], "high")
        self.assertNotIn("review_needed", eps[1])
        self.assertEqual(eps[1]["strategy"], "sitemap")
        self.assertEqual(eps[1]["product_pattern"], r"/products/([A-Za-z0-9\-]+)")

    def test_enrich_and_update_vendor_yaml_prevents_duplicate_urls(self) -> None:
        """Verifies enrich_and_update_vendor_yaml strictly rejects duplicate URLs."""
        mock_yaml_data = {
            "vendors": {
                "vendor_a": {
                    "id": "vendor_a",
                    "entry_points": [{"url": "https://shared.com/products"}],
                },
                "vendor_b": {
                    "id": "vendor_b",
                    "entry_points": [],
                },
            }
        }

        # Try to add shared URL to vendor_b
        verified_eps = [
            {
                "url": "https://shared.com/products",
                "is_valid_endpoint": True,
                "endpoint_type": "dom_table",
                "confidence": "high",
                "confidence_reason": "Valid table",
            }
        ]

        modified = enrich_and_update_vendor_yaml(
            vendor_id="vendor_b",
            vendor_conf=mock_yaml_data["vendors"]["vendor_b"],
            verified_endpoints=verified_eps,
            all_vendors_yaml_data=mock_yaml_data,
        )

        # Should not modify vendor_b because URL is already assigned to vendor_a
        self.assertFalse(modified)
        self.assertEqual(len(mock_yaml_data["vendors"]["vendor_b"]["entry_points"]), 0)

    def test_enrich_and_update_vendor_yaml_ignores_broken_new_candidates(self) -> None:
        """Verifies enrich_and_update_vendor_yaml does not add non-existent 404 candidates as entry points."""
        mock_yaml_data = {
            "vendors": {
                "vendor_c": {
                    "id": "vendor_c",
                    "entry_points": [{"url": "https://working.com/lifecycle"}],
                }
            }
        }

        verified_eps = [
            {
                "url": "https://broken.com/nonexistent_catalog",
                "final_url": "https://broken.com/404",
                "status_code": 404,
                "is_valid_endpoint": False,
                "confidence": "low",
                "confidence_reason": "HTTP reachability failure: status 404",
            }
        ]

        modified = enrich_and_update_vendor_yaml(
            vendor_id="vendor_c",
            vendor_conf=mock_yaml_data["vendors"]["vendor_c"],
            verified_endpoints=verified_eps,
            all_vendors_yaml_data=mock_yaml_data,
        )

        self.assertFalse(modified)
        self.assertEqual(len(mock_yaml_data["vendors"]["vendor_c"]["entry_points"]), 1)

    @patch("requests.Session.get")
    def test_inspect_sitemap_xml_parsing(self, mock_get: MagicMock) -> None:
        """Verifies XML sitemap index and urlset parsing."""
        mock_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/products/item-100.html</loc></url>
            <url><loc>https://example.com/products/item-200.html</loc></url>
        </urlset>"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = mock_xml
        mock_resp.url = "https://example.com/sitemap.xml"
        mock_resp.headers = {"Content-Type": "application/xml"}
        mock_resp.history = []
        mock_get.return_value = mock_resp

        res = self.prober.inspect_sitemap("https://example.com/sitemap.xml")
        self.assertTrue(res["has_data"])
        self.assertFalse(res["is_index"])
        self.assertEqual(len(res["sample_urls"]), 2)
        self.assertIn("https://example.com/products/item-100.html", res["sample_urls"])


if __name__ == "__main__":
    unittest.main()

