"""
Unit tests for scraper/adapters.py.
Validates FrameworkAdapter, LifecyclePlugin, and LangChainToolAdapter
for pluggability, conversion utilities, and security threat prevention.
"""

import unittest

import pandas as pd

from scraper.adapters import (
    FrameworkAdapter,
    LangChainToolAdapter,
    LifecyclePlugin,
    get_framework_adapter,
)
from scraper.models import ProductRecord
from scraper.security import SecurityThreatError


class TestFrameworkAdapters(unittest.TestCase):

    def setUp(self):
        self.adapter = FrameworkAdapter()
        self.langchain_adapter = LangChainToolAdapter(self.adapter)

        # Create sample records for adapter tests
        self.sample_records = [
            ProductRecord(
                vendor_name="Siemens",
                model_name="6ES7511-1AK02-0AB0",
                status="Phase-Out",
                stage_date_utc="2026-10-01T00:00:00Z",
                category="PLC",
                replacement="6ES7511-1AK03-0AB0",
            ),
            ProductRecord(
                vendor_name="Mitsubishi Electric",
                model_name="GT25-WLAN",
                status="Discontinued",
                stage_date_utc="2027-03-31T00:00:00Z",
                category="HMI",
                replacement="GT27-WLAN",
            ),
        ]

    # -------------------------------------------------------------------------
    # 1. FrameworkAdapter Initialization & Relative Reference Paths
    # -------------------------------------------------------------------------
    def test_adapter_initialization(self):
        adapter = get_framework_adapter()
        self.assertIsInstance(adapter, FrameworkAdapter)
        self.assertTrue(str(adapter.master_csv_path).endswith("all_vendors_lifecycle.csv"))
        self.assertTrue(str(adapter.config_path).endswith("vendors.yaml"))

    # -------------------------------------------------------------------------
    # 2. DataFrame and Dict Conversion Utilities
    # -------------------------------------------------------------------------
    def test_to_dataframe_conversion(self):
        df = self.adapter.to_dataframe(self.sample_records)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 2)
        self.assertIn("vendor_name", df.columns)
        self.assertIn("model_name", df.columns)
        self.assertIn("stage_date_utc", df.columns)
        self.assertEqual(df.iloc[0]["vendor_name"], "Siemens")
        self.assertEqual(df.iloc[0]["model_name"], "6ES7511-1AK02-0AB0")

    def test_to_dataframe_empty(self):
        df = self.adapter.to_dataframe([])
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 0)
        self.assertIn("vendor_name", df.columns)

    def test_to_dicts_conversion(self):
        dicts = self.adapter.to_dicts(self.sample_records)
        self.assertIsInstance(dicts, list)
        self.assertEqual(len(dicts), 2)
        self.assertEqual(dicts[0]["vendor_name"], "Siemens")
        self.assertEqual(dicts[0]["model_name"], "6ES7511-1AK02-0AB0")
        self.assertEqual(dicts[1]["vendor_name"], "Mitsubishi Electric")

    # -------------------------------------------------------------------------
    # 3. Security Threat Prevention on Query Parameters
    # -------------------------------------------------------------------------
    def test_query_records_rejects_sql_injection(self):
        with self.assertRaises(SecurityThreatError) as ctx:
            self.adapter.query_records(vendor_name="Siemens' OR '1'='1")
        self.assertEqual(ctx.exception.threat_type, "SQL_INJECTION")

        with self.assertRaises(SecurityThreatError) as ctx:
            self.adapter.query_records(model_name="6ES7; DROP TABLE products; --")
        self.assertEqual(ctx.exception.threat_type, "SQL_INJECTION")

    def test_query_records_rejects_xss(self):
        with self.assertRaises(SecurityThreatError) as ctx:
            self.adapter.query_records(model_name="<script>alert('xss')</script>")
        self.assertEqual(ctx.exception.threat_type, "XSS")

    def test_query_records_rejects_command_injection(self):
        with self.assertRaises(SecurityThreatError) as ctx:
            self.adapter.query_records(vendor_name="Siemens && whoami")
        self.assertEqual(ctx.exception.threat_type, "COMMAND_INJECTION")

    def test_query_vendor_terminology_security(self):
        with self.assertRaises(SecurityThreatError) as ctx:
            self.adapter.query_vendor_terminology(vendor_name="Cisco' UNION SELECT 1, 2--")
        self.assertEqual(ctx.exception.threat_type, "SQL_INJECTION")

        # Clean query should succeed
        term = self.adapter.query_vendor_terminology(vendor_name="Siemens")
        self.assertIn("vendor_name", term)
        self.assertIn("Siemens", term["vendor_name"])

    # -------------------------------------------------------------------------
    # 4. LifecyclePlugin Alias Compatibility
    # -------------------------------------------------------------------------
    def test_lifecycle_plugin_alias(self):
        plugin = LifecyclePlugin()
        self.assertIsInstance(plugin, FrameworkAdapter)

    # -------------------------------------------------------------------------
    # 5. LangChainToolAdapter Tests
    # -------------------------------------------------------------------------
    def test_langchain_tool_query_clean(self):
        output = self.langchain_adapter.query_product_lifecycle(
            vendor_name="Siemens",
            model_name="6ES7",
        )
        self.assertIsInstance(output, str)

    def test_langchain_tool_query_blocks_threat(self):
        output = self.langchain_adapter.query_product_lifecycle(
            vendor_name="Siemens' OR 1=1 --",
        )
        self.assertIn("SECURITY INCIDENT BLOCKED", output)
        self.assertIn("SQL_INJECTION", output)

    def test_langchain_tool_terminology_blocks_threat(self):
        output = self.langchain_adapter.get_vendor_lifecycle_terminology(
            vendor_name="<script>alert(1)</script>",
        )
        self.assertIn("SECURITY INCIDENT BLOCKED", output)
        self.assertIn("XSS", output)

    def test_langchain_tools_export(self):
        tools = self.langchain_adapter.as_langchain_tools()
        self.assertEqual(len(tools), 2)
        tool_names = [getattr(t, "name", "") for t in tools]
        self.assertIn("query_product_lifecycle", tool_names)
        self.assertIn("get_vendor_lifecycle_terminology", tool_names)


if __name__ == "__main__":
    unittest.main()
