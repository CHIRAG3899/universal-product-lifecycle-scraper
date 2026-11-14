"""
Unit & Edge Case Tests for scraper/models.py
Validates ProductRecord, model sanitisation, UTC date conversion, and firmware normalization.
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scraper.models import (
    ProductRecord,
    is_valid_product_model,
    normalize_firmware_version,
    parse_to_utc_iso,
    resolve_fallback_stage_date,
)


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
            "http://example.com/notice.pdf",
            "This product has been discontinued, please contact your sales representative",
            "For further information regarding replacement units please refer to support",
            "Model Number",
            "Product Name",
            "Part No.",
            "Replacement Model",
            "Inhaltsverzeichnis",
            "目次",
            "お問い合わせ",
            "Table des matières",
            "Skip to main content",
            "Shopping Cart",
            "View Details",
            # Status words masquerading as models
            "Discontinued",
            "End of Life",
            "End of Sale",
            "Phase-Out",
            "Obsolete",
            "Last Time Buy",
            "生産終了",
            "販売終了",
            "Produktabkündigung",
            # Pure dates masquerading as models
            "2023-03-31",
            "2022/09/30",
            "15-May-2024",
            "2024"
        ]
        for item in bad_inputs:
            with self.subTest(item=item):
                self.assertFalse(is_valid_product_model(item), f"Should reject non-model: '{item}'")

    def test_reject_table_header_tokens(self):
        """Verifies rejection of table header labels in English, German, French, Japanese, and Chinese."""
        headers = [
            "Part Number", "Part Numbers", "Part No", "Part No.", "Part #",
            "Catalog Number", "Catalog No", "Catalog No.", "Catalog #",
            "Order Number", "Order No", "Order Code", "Ordering Code",
            "Model Name", "Model Number", "Model No", "Model #",
            "Item Number", "Item No", "Item Description",
            "Product Name", "Product Line", "Product Code", "Product Family",
            "Discontinued Model", "Discontinued Product", "Replacement Model",
            "Replacement Part", "Successor Model", "Successor Part", "Alternate Model",
            "Discontinuation Date", "Effective Date", "Series Name", "Lifecycle Status",
            "Quantity", "Unit Price", "List Price", "Availability",
            # Multilingual
            "形名", "形式", "型番", "品名", "品目", "仕様", "概要", "代替品", "代替推奨品",
            "Artikelnummer", "Bestellnummer", "Typbezeichnung", "Nachfolgeprodukt",
            "Référence", "Reference", "Désignation", "Code article",
            "产品型号", "订货号", "产品名称", "替代型号"
        ]
        for h in headers:
            with self.subTest(header=h):
                self.assertFalse(is_valid_product_model(h), f"Should reject table header token: '{h}'")

    def test_reject_pure_engineering_specifications(self):
        """Verifies rejection of electrical, mechanical, and ingress ratings mistakenly parsed as models."""
        specs = [
            # Voltage / Power / Frequency / Current
            "24VDC", "24 VDC", "12VDC", "48VDC", "5VDC",
            "100-240VAC", "100-240 VAC", "115VAC", "230VAC", "24V",
            "50/60Hz", "50Hz", "60Hz", "100kHz",
            "0.75kW", "1.5kW", "2.2kW", "100W", "250W",
            "4-20mA", "0-20mA", "0-10V", "10A", "16A", "100mA",
            "120ohm", "100kohm", "1000rpm", "3000rpm",
            "10bar", "100psi", "250g", "1.5kg", "100mm",
            # Enclosure / Ingress Protection
            "IP20", "IP54", "IP65", "IP67", "IP68", "IP69K", "NEMA 4X", "NEMA 12",
            # Physical dimensions
            "100x50x25mm", "100 x 50 x 25 mm", "50x50mm",
            # Connector / Protocol standards
            "RJ45", "M12", "M8", "RS-485", "RS-232", "USB-C"
        ]
        for s in specs:
            with self.subTest(spec=s):
                self.assertFalse(is_valid_product_model(s), f"Should reject pure specification: '{s}'")

    def test_reject_price_and_commercial_terms(self):
        """Verifies rejection of currency amounts, stock levels, and commercial ordering notes."""
        terms = [
            "$1,200", "$450.00", "€350", "£99.99", "¥50,000",
            "USD 300", "EUR 450", "300 USD", "450.00 EUR", "1250.00",
            "In Stock", "Out of Stock", "Available", "Unavailable",
            "On Backorder", "Call for price", "Request quote",
            "Lead time: 4 weeks", "Qty: 10", "Quantity: 5", "MOQ: 100"
        ]
        for t in terms:
            with self.subTest(term=t):
                self.assertFalse(is_valid_product_model(t), f"Should reject price/commercial term: '{t}'")

    def test_reject_ui_breadcrumbs_and_pagination(self):
        """Verifies rejection of breadcrumb trails, pagination buttons, and search UI noise."""
        ui_noise = [
            "Home > Products > PLCs",
            "Support > Discontinued > Controllers",
            "Products » Inverters » Compact",
            "Page 1 of 5", "Page 2 of 10", "Next Page", "Previous Page",
            "Showing 1-20 of 150", "Results 1 to 25",
            "Click Here", "Read More", "Learn More", "View Details",
            "Download PDF", "Download Now", "Search Results", "Back to Top"
        ]
        for n in ui_noise:
            with self.subTest(noise=n):
                self.assertFalse(is_valid_product_model(n), f"Should reject UI noise: '{n}'")

    def test_reject_row_index_numbers(self):
        """Verifies rejection of table row sequence indices like 1, 2, 99, #1."""
        indices = ["1", "2", "3", "10", "99", "100", "#1", "#2", "#25"]
        for idx in indices:
            with self.subTest(index=idx):
                self.assertFalse(is_valid_product_model(idx), f"Should reject row index: '{idx}'")

    def test_accept_genuine_industrial_models(self):
        """Verifies genuine industrial hardware/software models across vendors are strictly preserved."""
        genuine = [
            "GT25-WLAN", "6ES7516-3AN02-0AB0", "FX5-16MR/ES", "1756-L83E",
            "C9300-48P", "PowerEdge R740", "PowerFlex 525", "TM221CE16R",
            "CP1E-N30DR-A", "ACS880-01-04A6-2", "TRD-J", "MI3321G-W",
            "MELSEC-iQ-R", "Ubuntu 22.04 LTS", "Windows Server 2019"
        ]
        for m in genuine:
            with self.subTest(model=m):
                self.assertTrue(is_valid_product_model(m), f"Should accept genuine model: '{m}'")

    def test_reject_empty_or_length_bounds(self):
        self.assertFalse(is_valid_product_model(None))
        self.assertFalse(is_valid_product_model(""))
        self.assertFalse(is_valid_product_model("   "))
        self.assertFalse(is_valid_product_model("A"))  # Too short (< 2 chars)
        self.assertFalse(is_valid_product_model("A" * 125))  # Too long (> 120 chars)
        self.assertFalse(is_valid_product_model("---"))  # No alphanumeric
        self.assertFalse(is_valid_product_model("!@#$%^&*()"))

    def test_reject_corrupt_symbols_and_uncommon_characters(self):
        """Verifies rejection of corrupt characters, mojibake, emojis, and unnecessary symbols."""
        corrupt_samples = [
            "GT25-WLAN\ufffd",         # Replacement character
            "Model\x00Name",            # Null byte
            "PLC\u200bSeries",          # Zero-width space
            "GT25-WLAN™",               # Trademark symbol
            "PowerEdge® R740",          # Registered symbol
            "Siemens © S7-1200",        # Copyright symbol
            "Switch ★ Pro",             # Star icon
            "Module • FX5",             # Bullet point
            "Unit § 4",                 # Section symbol
            "Model ~ 200",              # Tilde
            "Item ^ 4",                 # Caret
            "Price $500",               # Dollar sign
            "Ratio 50%",                # Percent sign
            "Product <Tag>",            # HTML brackets
            "Sensor {123}",             # Curly braces
            "Device; Series",           # Semicolon
            "Unit | Secondary",         # Pipe
            "Model \\ Rack",            # Backslash
        ]
        for item in corrupt_samples:
            with self.subTest(item=item):
                self.assertFalse(is_valid_product_model(item), f"Should reject corrupt/uncommon symbol string: {item}")

    def test_clean_and_sanitize_identifier(self):
        """Verifies that clean_and_sanitize_identifier scrubs corrupt symbols and retains clean identifiers."""
        from scraper.security import clean_and_sanitize_identifier

        # Pure valid strings are preserved
        self.assertEqual(clean_and_sanitize_identifier("GT25-WLAN"), "GT25-WLAN")
        self.assertEqual(clean_and_sanitize_identifier("IR1101/K9"), "IR1101/K9")
        self.assertEqual(clean_and_sanitize_identifier("CPU:214-1AD23"), "CPU:214-1AD23")
        self.assertEqual(clean_and_sanitize_identifier("6ES7511-1AK02-0AB0"), "6ES7511-1AK02-0AB0")
        self.assertEqual(clean_and_sanitize_identifier("PowerEdge R740+"), "PowerEdge R740+")
        self.assertEqual(clean_and_sanitize_identifier("Allen & Bradley (1756)"), "Allen & Bradley (1756)")
        self.assertEqual(clean_and_sanitize_identifier("Part #1234"), "Part #1234")

        # Corrupt and uncommon symbols are stripped
        self.assertEqual(clean_and_sanitize_identifier("• GT25-WLAN™"), "GT25-WLAN")
        self.assertEqual(clean_and_sanitize_identifier("PowerEdge® R740"), "PowerEdge R740")
        self.assertEqual(clean_and_sanitize_identifier("★ S7-1500 § 2"), "S7-1500 2")
        self.assertEqual(clean_and_sanitize_identifier("Model ~ FX5"), "Model FX5")

        # Pure noise or pure symbols return None
        self.assertIsNone(clean_and_sanitize_identifier("™®©★•"))
        self.assertIsNone(clean_and_sanitize_identifier(None))
        self.assertIsNone(clean_and_sanitize_identifier("n/a"))
        self.assertIsNone(clean_and_sanitize_identifier("---"))

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
        """Verifies that vendor_name, model_name, and status strictly reject null/empty values, while undated EOL models are preserved."""
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

        # 4. stage_date_utc missing/empty/None: MUST NOT drop record, populates fallback date (at least 1 month old) and metadata.missing_date=True
        rec_empty = ProductRecord(vendor_name="Mitsubishi Electric", model_name="FX2N-16MR", status="Discontinued", stage_date_utc="")
        self.assertIsNotNone(rec_empty.stage_date_utc)
        self.assertTrue(rec_empty.stage_date_utc.endswith("Z"))
        self.assertTrue(rec_empty.metadata.get("missing_date"))
        self.assertTrue(rec_empty.metadata.get("fallback_date_applied"))

        rec_none = ProductRecord(vendor_name="Mitsubishi Electric", model_name="FX2N-16MR", status="Discontinued", stage_date_utc=None)
        self.assertIsNotNone(rec_none.stage_date_utc)
        self.assertTrue(rec_none.stage_date_utc.endswith("Z"))
        self.assertTrue(rec_none.metadata.get("missing_date"))
        self.assertTrue(rec_none.metadata.get("fallback_date_applied"))

        rec_unparseable = ProductRecord(vendor_name="Mitsubishi Electric", model_name="FX2N-16MR", status="Discontinued", stage_date_utc="not-a-date")
        self.assertIsNotNone(rec_unparseable.stage_date_utc)
        self.assertTrue(rec_unparseable.stage_date_utc.endswith("Z"))

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

        # 8. Mandatory status strictly enforced even for OS/Software; undated OS entries preserved
        with self.assertRaises(ValueError):
            ProductRecord(vendor_name="Microsoft", model_name="", category="Operating System", os="Windows 7", status="", stage_date_utc="2020-01-14")
        with self.assertRaises(ValueError):
            ProductRecord(vendor_name="", model_name="", category="Operating System", os="Windows 7", status="End of Support", stage_date_utc="2020-01-14")
        win_undated = ProductRecord(vendor_name="Microsoft", model_name="", category="Operating System", os="Windows 7", status="End of Support", stage_date_utc="")
        self.assertIsNotNone(win_undated.stage_date_utc)
        self.assertTrue(win_undated.stage_date_utc.endswith("Z"))



    def test_aliases_string_and_list_normalization(self):
        """Verifies aliases accept strings or lists, clean whitespace, and deduplicate."""
        rec1 = ProductRecord(
            vendor_name="Siemens",
            model_name="6ES7516-3AN02-0AB0",
            aliases=["SIMATIC S7-1500 CPU 1516-3 PN/DP", "CPU 1516-3", "CPU 1516-3"],
            status="End of Life",
            stage_date_utc="2024-10-01"
        )
        self.assertEqual(rec1.aliases, "SIMATIC S7-1500 CPU 1516-3 PN/DP, CPU 1516-3")

        rec2 = ProductRecord(
            vendor_name="Cisco",
            model_name="C9300-48P",
            aliases="Catalyst 9300; Cat9300-48P; Catalyst 9300",
            status="End of Sale",
            stage_date_utc="2025-10-31"
        )
        self.assertEqual(rec2.aliases, "Catalyst 9300, Cat9300-48P")

    def test_aliases_removes_exact_model_self_reference(self):
        """Verifies that if an alias is identical to model_name, it is stripped."""
        rec = ProductRecord(
            vendor_name="Rockwell Automation",
            model_name="1756-L83E",
            aliases="ControlLogix 5580, 1756-L83E, 1756-L83E Controller",
            status="Active",
            stage_date_utc="2028-12-31"
        )
        self.assertEqual(rec.aliases, "ControlLogix 5580, 1756-L83E Controller")

    def test_aliases_from_metadata(self):
        """Verifies that aliases are recovered from metadata if omitted in top-level fields."""
        rec = ProductRecord(
            vendor_name="Mitsubishi Electric",
            model_name="GT25-WLAN",
            metadata={"common_name": "GOT2000 Wireless LAN Communication Unit"},
            status="Discontinued",
            stage_date_utc="2023-08-17"
        )
        self.assertEqual(rec.aliases, "GOT2000 Wireless LAN Communication Unit")

    def test_aliases_filters_invalid_models_and_specs(self):
        """Verifies that invalid tokens (table headers, electrical specs, noise) are filtered from aliases."""
        rec = ProductRecord(
            vendor_name="Mitsubishi Electric",
            model_name="GT25-WLAN",
            aliases=["GOT2000 Wireless LAN Unit", "24VDC", "Part Number", "Page 1 of 5", "GT25 WLAN Adapter"],
            status="Discontinued",
            stage_date_utc="2023-08-17"
        )
        self.assertEqual(rec.aliases, "GOT2000 Wireless LAN Unit, GT25 WLAN Adapter")


    def test_lifecycle_fallback_date_logic(self):
        """
        Verifies fallback date resolution according to user directive:
        - Authentic milestone dates must NEVER be overwritten.
        - Fallback uses article, page creation, or release date if at least 1 month old (>= 30 days).
        - If candidate date is less than 1 month old or missing, uses 1 month old from current date.
        """
        from datetime import datetime, timedelta, timezone

        ref_now = datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
        expected_30_days_ago = "2026-10-15T00:00:00Z"

        # 1. Authentic milestone date is present -> Strictly preserved without modification
        self.assertEqual(
            resolve_fallback_stage_date("2024-05-01T00:00:00Z", reference_now=ref_now),
            "2024-05-01T00:00:00Z"
        )
        self.assertEqual(
            resolve_fallback_stage_date("2023-11-20", reference_now=ref_now),
            "2023-11-20T00:00:00Z"
        )

        # 2. Candidate article date is older than 30 days -> Candidate date is used
        self.assertEqual(
            resolve_fallback_stage_date(None, candidate_date="2023-01-15", reference_now=ref_now),
            "2023-01-15T00:00:00Z"
        )
        self.assertEqual(
            resolve_fallback_stage_date("", metadata={"article_date": "2022-06-30"}, reference_now=ref_now),
            "2022-06-30T00:00:00Z"
        )
        self.assertEqual(
            resolve_fallback_stage_date(None, metadata={"page_creation_date": "2024-01-01T00:00:00Z"}, reference_now=ref_now),
            "2024-01-01T00:00:00Z"
        )
        self.assertEqual(
            resolve_fallback_stage_date(None, metadata={"release_date": "2021-12-01"}, reference_now=ref_now),
            "2021-12-01T00:00:00Z"
        )

        # 3. Candidate date is less than 30 days old (e.g. 5 days ago) -> Clamped to 1 month old from current
        recent_date = (ref_now - timedelta(days=5)).strftime("%Y-%m-%d")
        self.assertEqual(
            resolve_fallback_stage_date(None, candidate_date=recent_date, reference_now=ref_now),
            expected_30_days_ago
        )

        # 4. Candidate date is in the future -> Clamped to 1 month old from current
        future_date = (ref_now + timedelta(days=60)).strftime("%Y-%m-%d")
        self.assertEqual(
            resolve_fallback_stage_date(None, candidate_date=future_date, reference_now=ref_now),
            expected_30_days_ago
        )

        # 5. Missing / None candidate date -> Clamped to 1 month old from current
        self.assertEqual(
            resolve_fallback_stage_date(None, candidate_date=None, metadata={}, reference_now=ref_now),
            expected_30_days_ago
        )

        # 6. End-to-end integration with ProductRecord
        rec_with_art = ProductRecord(
            vendor_name="Rockwell Automation",
            model_name="1756-L85E",
            status="Active",
            stage_date_utc="",
            metadata={"article_date": "2023-03-15"}
        )
        self.assertEqual(rec_with_art.stage_date_utc, "2023-03-15T00:00:00Z")
        self.assertTrue(rec_with_art.metadata.get("fallback_date_applied"))

        rec_with_authentic = ProductRecord(
            vendor_name="Rockwell Automation",
            model_name="1756-L75",
            status="End of Life",
            stage_date_utc="2025-10-31",
            metadata={"article_date": "2023-03-15"}
        )
        # Authentic date must NOT be replaced by article_date
        self.assertEqual(rec_with_authentic.stage_date_utc, "2025-10-31T00:00:00Z")
        self.assertFalse(rec_with_authentic.metadata.get("fallback_date_applied", False))

    def test_canonical_status_normalization(self):
        """
        Verifies Requirement 12:
        Canonical status normalization to 6 ENUM values across multi-lingual terminology.
        """
        from scraper.models import CanonicalStatus, normalize_to_canonical_status

        test_cases = [
            # Active
            ("Active", CanonicalStatus.ACTIVE.value),
            ("Current", CanonicalStatus.ACTIVE.value),
            ("Regular Availability", CanonicalStatus.ACTIVE.value),
            ("Special Order Products from HID Global", CanonicalStatus.ACTIVE.value),
            ("Buy American", CanonicalStatus.ACTIVE.value),
            ("PowerG Life Safety", CanonicalStatus.ACTIVE.value),
            # Active Mature
            ("Active Mature", CanonicalStatus.ACTIVE_MATURE.value),
            ("Mature", CanonicalStatus.ACTIVE_MATURE.value),
            ("NRND", CanonicalStatus.ACTIVE_MATURE.value),
            ("Classic", CanonicalStatus.ACTIVE_MATURE.value),
            ("Limited", CanonicalStatus.ACTIVE_MATURE.value),
            # Phase Out
            ("Phase Out", CanonicalStatus.PHASE_OUT.value),
            ("Phase-out", CanonicalStatus.PHASE_OUT.value),
            ("Auslauftyp", CanonicalStatus.PHASE_OUT.value),
            ("Retiring", CanonicalStatus.PHASE_OUT.value),
            # End of Sale
            ("End of Sale", CanonicalStatus.END_OF_SALE.value),
            ("End of Sale (EOS)", CanonicalStatus.END_OF_SALE.value),
            ("Last Time Buy", CanonicalStatus.END_OF_SALE.value),
            ("LTB", CanonicalStatus.END_OF_SALE.value),
            ("End-Of-Build", CanonicalStatus.END_OF_SALE.value),
            ("Letzte Bestellmöglichkeit", CanonicalStatus.END_OF_SALE.value),
            # End of Support
            ("End of Support", CanonicalStatus.END_OF_SUPPORT.value),
            ("End of Service (EOS)", CanonicalStatus.END_OF_SUPPORT.value),
            ("EOSL", CanonicalStatus.END_OF_SUPPORT.value),
            ("End of Engineering", CanonicalStatus.END_OF_SUPPORT.value),
            ("End of Updates", CanonicalStatus.END_OF_SUPPORT.value),
            ("Einstellung der Reparatur", CanonicalStatus.END_OF_SUPPORT.value),
            # Obsolete
            ("Discontinued", CanonicalStatus.OBSOLETE.value),
            ("Obsolete", CanonicalStatus.OBSOLETE.value),
            ("End of Life", CanonicalStatus.OBSOLETE.value),
            ("EOL", CanonicalStatus.OBSOLETE.value),
            ("Vintage", CanonicalStatus.OBSOLETE.value),
            ("Retired", CanonicalStatus.OBSOLETE.value),
            ("Produktabkündigung", CanonicalStatus.OBSOLETE.value),
            ("生産終了", CanonicalStatus.OBSOLETE.value),
        ]

        for raw, expected in test_cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_to_canonical_status(raw), expected)

    def test_compare_and_select_latest_record(self):
        """
        Verifies Requirement 11 & 12:
        Record with latest date is kept when other key attributes match,
        and secondary attributes (replacement, aliases, metadata) are cleanly merged.
        """
        from scraper.models import compare_and_select_latest_record

        rec_old = {
            "vendor_name": "Rockwell Automation",
            "model_name": "1756-L75",
            "status": "Obsolete",
            "stage_date_utc": "2023-01-01T00:00:00Z",
            "replacement": "1756-L85E",
            "aliases": "ControlLogix 5570",
            "metadata": '{"doc_id": "123", "notice": "old"}'
        }

        rec_new = {
            "vendor_name": "Rockwell Automation",
            "model_name": "1756-L75",
            "status": "Obsolete",
            "stage_date_utc": "2025-06-30T00:00:00Z",
            "replacement": "",
            "aliases": "",
            "metadata": '{"doc_id": "456", "bulletin": "latest"}'
        }

        winner = compare_and_select_latest_record(rec_old, rec_new)
        # Winner must have latest date
        self.assertEqual(winner["stage_date_utc"], "2025-06-30T00:00:00Z")
        # Winner merges non-empty replacement and aliases from older record
        self.assertEqual(winner["replacement"], "1756-L85E")
        self.assertEqual(winner["aliases"], "ControlLogix 5570")

    def test_classify_hardware_or_software(self):
        """
        Verifies Requirement 15:
        Accurately extracts OS names from model fields and categorizes products.
        """
        from scraper.models import classify_hardware_or_software

        # Apple OS models
        p_cls, ext_os = classify_hardware_or_software("Apple Inc.", "iOS 12.5.8", "", "IT")
        self.assertEqual(p_cls, "Software - OS")
        self.assertEqual(ext_os, "iOS 12.5.8")

        p_cls, ext_os = classify_hardware_or_software("Apple Inc.", "macOS Sonoma 14.7.1", "", "IT")
        self.assertEqual(p_cls, "Software - OS")
        self.assertEqual(ext_os, "macOS Sonoma 14.7.1")

        p_cls, ext_os = classify_hardware_or_software("Apple Inc.", "watchOS 10.6.1", "", "IT")
        self.assertEqual(p_cls, "Software - OS")
        self.assertEqual(ext_os, "watchOS 10.6.1")

        # Hardware models
        p_cls, ext_os = classify_hardware_or_software("Apple Inc.", "iPhone 15 Pro", "", "IT")
        self.assertEqual(p_cls, "Hardware")
        self.assertIsNone(ext_os)

        p_cls, ext_os = classify_hardware_or_software("Siemens", "6ES7511-1AK02-0AB0", "", "OT")
        self.assertEqual(p_cls, "Hardware")
        self.assertIsNone(ext_os)


if __name__ == "__main__":
    unittest.main()
