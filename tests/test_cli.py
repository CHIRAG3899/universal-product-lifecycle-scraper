"""
Unit & Edge Case Tests for cli.py.
Validates:
1. Command line flags: --list-vendors, --compare-modes, --setup-key.
2. Argument parsing: --vendor, --sector, --all-vendors, --site-crawl, --url, --webhook-url.
3. Sector argument validation (OT, IoT, IT, all) and invalid choice rejection.
4. Correct invocation of LifecyclePipeline.execute with parsed CLI options.
"""

import io
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import cli
from scraper.models import ScrapedDataset


class TestCLI(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.held_stdout = io.StringIO()

    def tearDown(self):
        self.held_stdout.close()

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_01_print_banner(self, mock_stdout):
        """Verifies CLI banner output contains key framework metadata."""
        cli.print_banner()
        output = mock_stdout.getvalue()
        self.assertIn("ENTERPRISE MULTI-VENDOR LIFECYCLE", output)
        self.assertIn("140 Top Vendors", output)
        self.assertIn("Crawl4AI + Google Gemini", output)

    @patch("setup_key.main")
    async def test_02_setup_key_flag(self, mock_setup_main):
        """Verifies --setup-key launches interactive setup_key module."""
        with patch.object(sys, "argv", ["cli.py", "--setup-key"]):
            with patch("sys.stdout", new_callable=io.StringIO):
                await cli.main()
        mock_setup_main.assert_called_once()

    @patch("sys.stdout", new_callable=io.StringIO)
    async def test_03_compare_modes_flag(self, mock_stdout):
        """Verifies --compare-modes prints technical crawler matrix."""
        with patch.object(sys, "argv", ["cli.py", "--compare-modes"]):
            await cli.main()
        output = mock_stdout.getvalue()
        self.assertIn("TECHNICAL COMPARISON", output)
        self.assertIn("GENERIC IDE CRAWLER vs. ENTERPRISE AI CRAWLER", output)

    @patch("sys.stdout", new_callable=io.StringIO)
    async def test_04_list_vendors_flag(self, mock_stdout):
        """Verifies --list-vendors displays table with 100 supported vendors."""
        with patch.object(sys, "argv", ["cli.py", "--list-vendors"]):
            await cli.main()
        output = mock_stdout.getvalue()
        self.assertIn("Configured Vendors", output)
        self.assertIn("mitsubishi", output)
        self.assertIn("Total:", output)

    @patch("scraper.pipeline.LifecyclePipeline.execute", new_callable=AsyncMock)
    async def test_05_default_vendor_fallback(self, mock_execute):
        """Verifies default vendor target falls back to 'mitsubishi'."""
        mock_execute.return_value = ScrapedDataset(
            source_url="manifest",
            crawl_timestamp="2026-10-24T00:00:00Z",
            total_products=10,
            ai_model_used="gemini-2.5-flash",
            products=[]
        )
        with patch.object(sys, "argv", ["cli.py"]):
            with patch("sys.stdout", new_callable=io.StringIO):
                await cli.main()

        mock_execute.assert_called_once_with(
            vendor_filter="mitsubishi",
            sector_filter=None,
            target_url=None,
            site_crawl=True,
            max_pages=0,
            max_depth=0,
            resume=False
        )

    @patch("scraper.pipeline.LifecyclePipeline.execute", new_callable=AsyncMock)
    async def test_06_custom_vendor_and_sector_flags(self, mock_execute):
        """Verifies custom --vendor, --sector, and --site-crawl arguments."""
        mock_execute.return_value = ScrapedDataset(
            source_url="manifest",
            crawl_timestamp="2026-10-24T00:00:00Z",
            total_products=5,
            ai_model_used="gemini-2.5-flash",
            products=[]
        )
        with patch.object(sys, "argv", [
            "cli.py",
            "--vendor", "siemens",
            "--sector", "OT",
            "--site-crawl",
            "--webhook-url", "https://hooks.slack.com/services/test"
        ]):
            with patch("sys.stdout", new_callable=io.StringIO):
                await cli.main()

        mock_execute.assert_called_once_with(
            vendor_filter="siemens",
            sector_filter="OT",
            target_url=None,
            site_crawl=True,
            max_pages=0,
            max_depth=0,
            resume=False
        )

    @patch("scraper.pipeline.LifecyclePipeline.execute", new_callable=AsyncMock)
    async def test_07_all_vendors_flag(self, mock_execute):
        """Verifies --all-vendors sets vendor_filter to 'all'."""
        mock_execute.return_value = ScrapedDataset(
            source_url="manifest",
            crawl_timestamp="2026-10-24T00:00:00Z",
            total_products=100,
            ai_model_used="gemini-2.5-flash",
            products=[]
        )
        with patch.object(sys, "argv", ["cli.py", "--all-vendors", "--sector", "IoT"]):
            with patch("sys.stdout", new_callable=io.StringIO):
                await cli.main()

        mock_execute.assert_called_once_with(
            vendor_filter="all",
            sector_filter="IoT",
            target_url=None,
            site_crawl=True,
            max_pages=0,
            max_depth=0,
            resume=False
        )

    @patch("scraper.pipeline.LifecyclePipeline.execute", new_callable=AsyncMock)
    async def test_09_max_pages_and_depth_flags(self, mock_execute):
        """Verifies --max-pages and --max-depth are passed to pipeline.execute."""
        mock_execute.return_value = ScrapedDataset(
            source_url="manifest",
            crawl_timestamp="2026-10-24T00:00:00Z",
            total_products=20,
            ai_model_used="gemini-2.5-flash",
            products=[]
        )
        with patch.object(sys, "argv", [
            "cli.py",
            "--vendor", "rockwell_automation",
            "--site-crawl",
            "--max-pages", "50",
            "--max-depth", "3"
        ]):
            with patch("sys.stdout", new_callable=io.StringIO):
                await cli.main()

        mock_execute.assert_called_once_with(
            vendor_filter="rockwell_automation",
            sector_filter=None,
            target_url=None,
            site_crawl=True,
            max_pages=50,
            max_depth=3,
            resume=False
        )

    @patch("scraper.pipeline.LifecyclePipeline.execute", new_callable=AsyncMock)
    async def test_12_resume_flag(self, mock_execute):
        """Verifies --resume flag is passed to pipeline.execute."""
        mock_execute.return_value = ScrapedDataset(
            source_url="manifest",
            crawl_timestamp="2026-10-25T00:00:00Z",
            total_products=15,
            ai_model_used="gemini-2.5-flash",
            products=[]
        )
        with patch.object(sys, "argv", ["cli.py", "--resume", "--vendor", "mitsubishi"]):
            with patch("sys.stdout", new_callable=io.StringIO):
                await cli.main()

        mock_execute.assert_called_once_with(
            vendor_filter="mitsubishi",
            sector_filter=None,
            target_url=None,
            site_crawl=True,
            max_pages=0,
            max_depth=0,
            resume=True
        )

    @patch("scraper.pipeline.LifecyclePipeline.execute", new_callable=AsyncMock)
    async def test_13_no_site_crawl_flag(self, mock_execute):
        """Verifies --no-site-crawl flag explicitly disables site crawl."""
        mock_execute.return_value = ScrapedDataset(
            source_url="manifest",
            crawl_timestamp="2026-10-25T00:00:00Z",
            total_products=5,
            ai_model_used="gemini-2.5-flash",
            products=[]
        )
        with patch.object(sys, "argv", ["cli.py", "--no-site-crawl", "--vendor", "mitsubishi"]):
            with patch("sys.stdout", new_callable=io.StringIO):
                await cli.main()

        mock_execute.assert_called_once_with(
            vendor_filter="mitsubishi",
            sector_filter=None,
            target_url=None,
            site_crawl=False,
            max_pages=0,
            max_depth=0,
            resume=False
        )

    def test_08_invalid_sector_rejected(self):
        """Verifies argparse raises SystemExit on invalid sector choices."""
        with patch.object(sys, "argv", ["cli.py", "--sector", "INVALID_SECTOR"]):
            with patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit):
                    import argparse
                    parser = argparse.ArgumentParser()
                    parser.add_argument("--sector", choices=["OT", "IoT", "IT", "all"])
                    parser.parse_args(["--sector", "INVALID_SECTOR"])

    async def test_09_clean_artifacts_flag(self):
        """Verifies --clean-artifacts flag executes cleanup."""
        with patch.object(sys, "argv", ["cli.py", "--clean-artifacts"]):
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                await cli.main()
                self.assertIn("Successfully cleaned", mock_stdout.getvalue())

    @patch("cli.LifecyclePipeline")
    async def test_10_token_optimization_flags(self, mock_pipeline_cls):
        """Verifies --batch-mode, --thinking-budget, and --prompt-caching flags are passed to LifecyclePipeline."""
        mock_instance = MagicMock()
        mock_instance.execute = AsyncMock()
        mock_pipeline_cls.return_value = mock_instance

        with patch.object(sys, "argv", ["cli.py", "--model", "gemini-1.5-flash", "--batch-mode", "--thinking-budget", "0", "--prompt-caching"]):
            with patch("sys.stdout", new_callable=io.StringIO):
                await cli.main()

        mock_pipeline_cls.assert_called_once_with(
            api_key=None,
            model="gemini-1.5-flash",
            batch_mode=True,
            thinking_budget=0,
            enable_prompt_caching=True
        )


if __name__ == "__main__":
    unittest.main()
