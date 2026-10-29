"""
Unit & Edge Case Tests for scraper/vendors.py
Validates multi-lingual stage normalization and vendor detection across OT, IoT, and IT.
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.vendors import detect_vendor_from_url_or_text, normalize_stage_name


class TestVendors(unittest.TestCase):

    # -------------------------------------------------------------------------
    # 1. Multi-Lingual Stage Normalization Tests
    # -------------------------------------------------------------------------
    def test_english_stage_normalization(self):
        cases = [
            ("End of Life", "End of Life (EOL)"),
            ("EOL", "End of Life (EOL)"),
            ("Last Time Buy", "Last Time Buy (LTB)"),
            ("LTB", "Last Time Buy (LTB)"),
            ("End of Service", "End of Service (EOS)"),
            ("EOS", "End of Service (EOS)"),
            ("Discontinued", "Discontinued"),
            ("Phase Out", "Phase-Out Announced"),
            ("Final Order", "Last Time Buy (LTB)"),
            ("Repair End", "End of Service (EOS)")
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_stage_name(raw), expected)

    def test_german_stage_normalization(self):
        cases = [
            ("Produktabkündigung", "End of Life (EOL)"),
            ("Abkündigung", "End of Life (EOL)"),
            ("Auslauftyp", "Phase-Out Announced"),
            ("Letzte Bestellmöglichkeit", "Last Time Buy (LTB)"),
            ("Einstellung der Reparatur", "End of Service (EOS)"),
            ("Ersatzteilende", "End of Service (EOS)"),
            ("Lieferstopp", "Discontinued")
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_stage_name(raw), expected)

    def test_japanese_stage_normalization(self):
        cases = [
            ("生産終了", "End of Life (EOL)"),
            ("販売終了", "End of Life (EOL)"),
            ("製造中止", "Discontinued"),
            ("最終受注", "Last Time Buy (LTB)"),
            ("最終注文", "Last Time Buy (LTB)"),
            ("修理対応終了", "End of Service (EOS)"),
            ("保守終了", "End of Service (EOS)")
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_stage_name(raw), expected)

    def test_swedish_and_french_normalization(self):
        cases = [
            ("Utgående produkt", "End of Life (EOL)"),
            ("Sista orderdatum", "Last Time Buy (LTB)"),
            ("Service upphör", "End of Service (EOS)"),
            ("Fin de vie", "End of Life (EOL)"),
            ("Dernière commande", "Last Time Buy (LTB)"),
            ("Fin de support", "End of Service (EOS)")
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_stage_name(raw), expected)

    def test_stage_normalization_edge_cases(self):
        # Empty and None values
        self.assertEqual(normalize_stage_name(None), "Discontinued")
        self.assertEqual(normalize_stage_name(""), "Discontinued")
        self.assertEqual(normalize_stage_name("   "), "Discontinued")
        # Truncates sentence-length phrases
        long_phrase = "This product has reached its end of sales announcement and will not be replenished"
        normalized = normalize_stage_name(long_phrase)
        self.assertTrue(len(normalized) <= 40)
        self.assertIn("End of Life (EOL)", normalized)

    # -------------------------------------------------------------------------
    # 2. Vendor Detection Tests
    # -------------------------------------------------------------------------
    def test_detect_vendor_from_url(self):
        url_cases = [
            ("https://se-fa.mitsubishielectric.com/fa/se_en/support/eol", "Mitsubishi Electric"),
            ("https://mall.industry.siemens.com/catalog", "Siemens"),
            ("https://www.se.com/ww/en/work/support/lifecycle", "Schneider Electric"),
            ("https://www.rockwellautomation.com/support", "Rockwell Automation (Allen-Bradley)"),
            ("https://ia.omron.com/support/product", "Omron Corporation"),
            ("https://new.abb.com/drives/lifecycle", "ABB"),
            ("https://www.cisco.com/c/en/us/products/eos-eol-notice.html", "Cisco Systems"),
            ("https://www.digi.com/support/eol", "Digi International")
        ]
        for url, expected in url_cases:
            with self.subTest(url=url):
                detected = detect_vendor_from_url_or_text(url, "")
                self.assertEqual(detected, expected)

    def test_detect_vendor_from_body_text(self):
        self.assertEqual(
            detect_vendor_from_url_or_text("", "Official notice from Siemens AG regarding SIMATIC S7-300"),
            "Siemens"
        )
        self.assertEqual(
            detect_vendor_from_url_or_text("", "Mitsubishi Electric FA EOL notice for MELIPC series"),
            "Mitsubishi Electric"
        )

    def test_detect_vendor_from_yaml_100_vendors(self):
        """Verifies that vendors configured in vendors.yaml (not in hardcoded 11) are dynamically resolved."""
        yaml_cases = [
            ("https://www.advantech.com/support/lifecycle", "Advantech"),
            ("https://www.fanucamerica.com/support/parts", "FANUC Corporation"),
            ("https://www.fortinet.com/support/product-life-cycle", "Fortinet"),
            ("https://support.juniper.net/support/eol/", "Juniper Networks"),
            ("https://www.axis.com/support/product-lifecycle", "Axis Communications"),
            ("https://www.alliedtelesis.com/en/services/end-of-life-policy", "Allied Telesis"),
            ("https://www.lenze.com/en-us/service/product-lifecycle/", "Lenze"),
            ("https://www.parker.com/us/en/support/discontinued-products.html", "Parker Hannifin")
        ]
        for url, expected in yaml_cases:
            with self.subTest(url=url):
                detected = detect_vendor_from_url_or_text(url, "")
                self.assertEqual(detected, expected)

    def test_vendor_specific_status_no_fixed_limitation(self):
        """Verifies that vendor-specific statuses have NO limitation and are preserved accurately."""
        cases = [
            ("End of Sale", "End of Sale"),
            ("Last Date of Support", "Last Date of Support"),
            ("Classic", "Classic"),
            ("Limited", "Limited"),
            ("Obsolete", "Obsolete"),
            ("Active Mature", "Active Mature"),
            ("Phase-Out Product", "Phase-Out Product"),
            ("Delivery Release", "Delivery Release"),
            ("Announced Discontinuation", "Announced Discontinuation"),
            ("Product Cancellation", "Product Cancellation"),
            ("Stop Shipment", "Stop Shipment"),
            ("Repair Termination", "Repair Termination"),
            ("Maintenance Only", "Maintenance Only"),
            ("Custom Lifecycle Phase 4", "Custom Lifecycle Phase 4")
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_stage_name(raw), expected)


if __name__ == "__main__":
    unittest.main()
