"""
Unit & Edge Case Tests for scraper/models.py
Validates ProductRecord, model sanitisation, UTC date conversion, and firmware normalization.
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.models import ProductRecord, is_valid_product_model, normalize_firmware_version, parse_to_utc_iso


class TestModels(unittest.TestCase):

    # -------------------------------------------------------------------------
    # 1. is_valid_product_model tests (Genuine vs Noise/Cookies/Navigation)
    # -------------------------------------------------------------------------
    def test_genuine_product_models(self):
        genuine_models = [
            "GT25-WLAN",
            "FX5-EIP",
            "MI3321G-W",
            "S7-1500",
            "PowerEdge R750",
            "Catalyst 9300",
            "ESP32-WROOM-32D",
            "FR-E800-0.75K",
            "MR-J4-40B",
            "6ES7511-1AK02-0AB0",
            "TM221CE16R",
            "1756-L83E",
            "MELSEC-Q Series",
            "Series 6000",
            "Model 6001"
        ]
        for model in genuine_models:
            with self.subTest(model=model):
                self.assertTrue(is_valid_product_model(model), f"Should accept genuine model: '{model}'")

    def test_reject_cookie_consent_tokens(self):
        cookie_terms = [
            "Performance Cookies",
            "strictly necessary cookies",
            "Functional Cookies",
            "Targeting Cookies",
            "Cookie Notice",
            "Manage Consent Preferences",
            "Cookies Settings",
            "Cookie Policy"
        ]
        for term in cookie_terms:
            with self.subTest(term=term):
                self.assertFalse(is_valid_product_model(term), f"Should reject cookie token: '{term}'")

    def test_reject_navigation_tokens(self):
        nav_terms = [
            "Global",
            "Americas",
            "Asia-Pacific",
            "Europe, CIS, Middle East & Africa",
            "Follow Us",
            "About",
            "Contact Us",
            "Privacy Policy",
            "Terms of Use",
            "Site Map",
            "Home",
            "Products",
            "Support",
            "Downloads",
            "Series",
            "Model"
        ]
        for term in nav_terms:
            with self.subTest(term=term):
                self.assertFalse(is_valid_product_model(term), f"Should reject nav token: '{term}'")

    def test_reject_instructional_phrases_and_urls(self):
        bad_inputs = [
            "Consult your official sales representative",
            "See bulletin PDF for details",
            "Click here to download",
            "Read more about lifecycle",
            "Download document EOL-123",
            "[GT25-WLAN](https://example.com/gt25)",
            "https://se-fa.mitsubishielectric.com/fa/se_en",
            "http://example.com/notice.pdf"
        ]
        for item in bad_inputs:
            with self.subTest(item=item):
                self.assertFalse(is_valid_product_model(item), f"Should reject non-model: '{item}'")

    def test_reject_empty_or_length_bounds(self):
        self.assertFalse(is_valid_product_model(None))
        self.assertFalse(is_valid_product_model(""))
        self.assertFalse(is_valid_product_model("   "))
        self.assertFalse(is_valid_product_model("A"))  # Too short (< 2 chars)
        self.assertFalse(is_valid_product_model("A" * 125))  # Too long (> 120 chars)
        self.assertFalse(is_valid_product_model("---"))  # No alphanumeric
        self.assertFalse(is_valid_product_model("!@#$%^&*()"))

    # -------------------------------------------------------------------------
    # 2. parse_to_utc_iso tests (Dates & Edge Cases)
    # -------------------------------------------------------------------------
    def test_parse_iso_and_slash_dates(self):
        self.assertEqual(parse_to_utc_iso("2026-09-30"), "2026-09-30T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("2025/10/29"), "2025-10-29T00:00:00Z")

    def test_parse_european_dates(self):
        self.assertEqual(parse_to_utc_iso("30.09.2026"), "2026-09-30T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("28.01.2025"), "2025-01-28T00:00:00Z")

    def test_parse_us_dates(self):
        self.assertEqual(parse_to_utc_iso("09/30/2026"), "2026-09-30T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("10/29/2025"), "2025-10-29T00:00:00Z")

    def test_parse_asian_kanji_dates(self):
        self.assertEqual(parse_to_utc_iso("2026年9月30日"), "2026-09-30T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("2023年8月17日"), "2023-08-17T00:00:00Z")

    def test_parse_text_month_dates(self):
        # Textual month formats normalize to the end of that month
        self.assertEqual(parse_to_utc_iso("September 2026"), "2026-09-30T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("Oct 2025"), "2025-10-31T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("February 2024"), "2024-02-29T00:00:00Z")  # 2024 is a leap year

    def test_parse_quarters_and_half_years(self):
        """Verifies Quarter (Q1-Q4) and Half-Year (H1-H2) milestone dates."""
        self.assertEqual(parse_to_utc_iso("Q1 2025"), "2025-03-31T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("2025-Q2"), "2025-06-30T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("3Q 2026"), "2026-09-30T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("Q4 2026"), "2026-12-31T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("Q3/25"), "2025-09-30T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("H1 2025"), "2025-06-30T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("2H 2026"), "2026-12-31T00:00:00Z")

    def test_parse_german_months_and_years(self):
        """Verifies German month localization and standalone year parsing."""
        self.assertEqual(parse_to_utc_iso("31. März 2026"), "2026-03-31T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("15. Oktober 2025"), "2025-10-15T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("Februar 2024"), "2024-02-29T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("September, 2024"), "2024-09-30T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("2026"), "2026-12-31T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("FY25"), "2025-12-31T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("FY2027"), "2027-12-31T00:00:00Z")

    def test_parse_international_french_spanish_asian_dates(self):
        """Verifies French, Spanish/Italian, and Asian year-month date parsing."""
        # French
        self.assertEqual(parse_to_utc_iso("15 Mars 2026"), "2026-03-15T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("31 Décembre 2025"), "2025-12-31T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("Juin 2026"), "2026-06-30T00:00:00Z")
        # Spanish / Italian
        self.assertEqual(parse_to_utc_iso("15 de Mayo 2026"), "2026-05-15T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("Marzo 2025"), "2025-03-31T00:00:00Z")
        # Asian Year + Month only
        self.assertEqual(parse_to_utc_iso("2026年9月"), "2026-09-30T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("2025年2月"), "2025-02-28T00:00:00Z")

    def test_parse_invalid_day_clamping(self):
        # Clamps invalid days (e.g. Nov 31 -> Nov 30, Feb 30 on non-leap year -> Feb 28)
        self.assertEqual(parse_to_utc_iso("2026-11-31"), "2026-11-30T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("2023-02-31"), "2023-02-28T00:00:00Z")
        self.assertEqual(parse_to_utc_iso("2024-02-31"), "2024-02-29T00:00:00Z")

    def test_parse_invalid_or_non_date_strings(self):
        self.assertIsNone(parse_to_utc_iso(None))
        self.assertIsNone(parse_to_utc_iso(""))
        self.assertIsNone(parse_to_utc_iso("N/A"))
        self.assertIsNone(parse_to_utc_iso("None"))
        self.assertIsNone(parse_to_utc_iso("TBD"))
        self.assertIsNone(parse_to_utc_iso("Announced"))
        self.assertIsNone(parse_to_utc_iso("Random Non Date String 12345"))

    # -------------------------------------------------------------------------
    # 3. normalize_firmware_version tests
    # -------------------------------------------------------------------------
    def test_normalize_firmware(self):
        self.assertEqual(normalize_firmware_version("v1.2.3"), "1.2.3")
        self.assertEqual(normalize_firmware_version("1.2.3.4"), "1.2.3.4")
        self.assertEqual(normalize_firmware_version("2.1.0"), "2.1.0")
        self.assertEqual(normalize_firmware_version("3.0"), "3.0.0")
        self.assertEqual(normalize_firmware_version("Rev 4.5.1"), "4.5.1")
        self.assertIsNone(normalize_firmware_version(None))
        self.assertIsNone(normalize_firmware_version(""))
        self.assertIsNone(normalize_firmware_version("N/A"))
        self.assertIsNone(normalize_firmware_version("Hardware Revision"))

    # -------------------------------------------------------------------------
    # 4. ProductRecord schema & synchronization tests
    # -------------------------------------------------------------------------
    def test_product_record_defaults_and_synchronization(self):
        record = ProductRecord(
            vendor_name="Mitsubishi Electric",
            model_name="MI3321G-W",
            stage="Last Time Buy (LTB)",
            stage_date_utc="2026-09-30",
            metadata={"replacement": "MI5000", "source_url": "https://example.com/portal"}
        )
        self.assertEqual(record.status, "Last Time Buy (LTB)")
        self.assertEqual(record.vendor_status, "Last Time Buy (LTB)")
        self.assertEqual(record.stage, "Last Time Buy (LTB)")
        self.assertEqual(record.stage_date_utc, "2026-09-30T00:00:00Z")
        self.assertEqual(record.replacement, "MI5000")
        self.assertEqual(record.source_url, "https://example.com/portal")
        self.assertIsNotNone(record.fingerprint)
        self.assertEqual(len(record.fingerprint or ""), 16)

        # Test replacement filler phrase normalization to None
        record_repl = ProductRecord(
            vendor_name="Mitsubishi Electric",
            model_name="GT25-WLAN",
            stage="End of Life",
            stage_date_utc="FY25",
            replacement="Consult your official sales representative"
        )
        self.assertIsNone(record_repl.replacement)

    def test_product_record_rejects_invalid_model(self):
        with self.assertRaises(ValueError):
            ProductRecord(
                vendor_name="Mitsubishi Electric",
                model_name="Performance Cookies",
                stage="End of Life (EOL)",
                stage_date_utc="2026-09-30"
            )

    def test_mandatory_fields_strictly_enforced_no_nulls(self):
        """Verifies that vendor_name, model_name, status, and stage_date_utc strictly reject null/empty values."""
        # 1. vendor_name missing/empty/None
        with self.assertRaises(ValueError):
            ProductRecord(vendor_name="", model_name="FX2N-16MR", status="Discontinued", stage_date_utc="2026-09-30")
        with self.assertRaises(ValueError):
            ProductRecord(vendor_name=None, model_name="FX2N-16MR", status="Discontinued", stage_date_utc="2026-09-30")

        # 2. model_name missing/empty/None
        with self.assertRaises(ValueError):
            ProductRecord(vendor_name="Mitsubishi Electric", model_name="", status="Discontinued", stage_date_utc="2026-09-30")
        with self.assertRaises(ValueError):
            ProductRecord(vendor_name="Mitsubishi Electric", model_name=None, status="Discontinued", stage_date_utc="2026-09-30")

        # 3. status missing/empty/None
        with self.assertRaises(ValueError):
            ProductRecord(vendor_name="Mitsubishi Electric", model_name="FX2N-16MR", status="", stage="", vendor_status="", stage_date_utc="2026-09-30")

        # 4. stage_date_utc missing/empty/None
        with self.assertRaises(ValueError):
            ProductRecord(vendor_name="Mitsubishi Electric", model_name="FX2N-16MR", status="Discontinued", stage_date_utc="")
        with self.assertRaises(ValueError):
            ProductRecord(vendor_name="Mitsubishi Electric", model_name="FX2N-16MR", status="Discontinued", stage_date_utc=None)
        with self.assertRaises(ValueError):
            ProductRecord(vendor_name="Mitsubishi Electric", model_name="FX2N-16MR", status="Discontinued", stage_date_utc="not-a-date")

    def test_bulletin_code_date_recovery(self):
        """Verifies that stage_date_utc is automatically recovered from bulletin code in metadata if not directly passed."""
        rec = ProductRecord(
            vendor_name="Mitsubishi Electric",
            model_name="L02CPU-P",
            status="End of Life",
            stage_date_utc="",
            metadata={"bulletin_title": "EOL-PLC-240408-1961-SCA"}
        )
        self.assertEqual(rec.stage_date_utc, "2024-04-08T00:00:00Z")

    def test_os_and_software_lifecycle_empty_model_name_supported(self):
        """Verifies that OS and software lifecycles (e.g. Windows 7, Ubuntu, RHEL) allow empty model_name while enforcing status and stage_date_utc."""
        # 1. Windows 7 OS record
        win7 = ProductRecord(
            vendor_name="Microsoft",
            model_name="",
            category="Operating System",
            os="Windows 7",
            status="End of Support",
            stage_date_utc="2020-01-14"
        )
        self.assertEqual(win7.vendor_name, "Microsoft")
        self.assertEqual(win7.status, "End of Support")
        self.assertEqual(win7.stage_date_utc, "2020-01-14T00:00:00Z")
        self.assertTrue(len(win7.fingerprint) == 16)

        # 2. Ubuntu OS record with None model_name
        ubuntu = ProductRecord(
            vendor_name="Canonical",
            model_name=None,
            category="Operating System",
            os="Ubuntu 18.04 LTS",
            status="End of Standard Support",
            stage_date_utc="2023-05-31"
        )
        self.assertEqual(ubuntu.status, "End of Standard Support")
        self.assertEqual(ubuntu.stage_date_utc, "2023-05-31T00:00:00Z")
        self.assertTrue(len(ubuntu.fingerprint) == 16)

        # 3. RHEL record with Software category
        rhel = ProductRecord(
            vendor_name="Red Hat",
            model_name="",
            category="Software",
            os="RHEL 7",
            status="End of Maintenance",
            stage_date_utc="2024-06-30"
        )
        self.assertEqual(rhel.status, "End of Maintenance")
        self.assertEqual(rhel.stage_date_utc, "2024-06-30T00:00:00Z")

        # 4. Debian OS record with empty model_name
        debian = ProductRecord(
            vendor_name="Debian",
            model_name="",
            category="Operating System",
            os="Debian 11 (Bullseye)",
            status="End of Life",
            stage_date_utc="2026-06-30"
        )
        self.assertEqual(debian.vendor_name, "Debian")
        self.assertEqual(debian.status, "End of Life")

        # 5. Linux kernel entry with empty model_name
        linux = ProductRecord(
            vendor_name="Linux Foundation",
            model_name="",
            category="Operating System",
            os="Linux Kernel 5.15 LTS",
            status="End of Life",
            stage_date_utc="2026-10-31"
        )
        self.assertEqual(linux.status, "End of Life")

        # 6. Software Application entry with empty model_name
        scada_app = ProductRecord(
            vendor_name="Siemens",
            model_name="",
            category="Software Application",
            os="WinCC V7.5",
            status="Phase-Out",
            stage_date_utc="2025-10-01"
        )
        self.assertEqual(scada_app.status, "Phase-Out")

        # 7. Hardware records with empty model_name MUST STRICTLY FAIL validation
        with self.assertRaises(ValueError):
            ProductRecord(vendor_name="Cisco", model_name="", category="Industrial Switch", status="End of Sale", stage_date_utc="2026-09-30")
        with self.assertRaises(ValueError):
            ProductRecord(vendor_name="Rockwell Automation", model_name="", category="PLC", status="End of Life", stage_date_utc="2026-09-30")
        with self.assertRaises(ValueError):
            ProductRecord(vendor_name="Mitsubishi Electric", model_name="", category="Inverter", status="Discontinued", stage_date_utc="2026-09-30")
        with self.assertRaises(ValueError):
            ProductRecord(vendor_name="Siemens", model_name="", category="Drive", status="Phase-Out", stage_date_utc="2026-09-30")

        # 8. Mandatory status and date still strictly enforced even for OS/Software
        with self.assertRaises(ValueError):
            ProductRecord(vendor_name="Microsoft", model_name="", category="Operating System", os="Windows 7", status="", stage_date_utc="2020-01-14")
        with self.assertRaises(ValueError):
            ProductRecord(vendor_name="Microsoft", model_name="", category="Operating System", os="Windows 7", status="End of Support", stage_date_utc="")


if __name__ == "__main__":
    unittest.main()
