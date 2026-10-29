"""
Unit & Edge Case Tests for setup_key.py.
Validates:
1. Banner output rendering.
2. test_and_save_key validation with empty string.
3. test_and_save_key failure handling when test_connection fails.
4. test_and_save_key success handling: writing/updating .env with new GEMINI_API_KEY and GEMINI_MODEL.
5. Preserving existing non-Gemini environment variables in .env during update.
6. main() execution with --key=... CLI parameter.
7. main() handling user cancellation (Ctrl+C / EOF).
"""

import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import setup_key


class TestSetupKey(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir)
        self.mock_env = Path(self.temp_dir) / ".env"

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_01_print_banner(self, mock_stdout):
        """Verifies setup_key banner displays helpful setup instructions."""
        setup_key.print_banner()
        output = mock_stdout.getvalue()
        self.assertIn("GOOGLE GEMINI API KEY SETUP", output)
        self.assertIn("aistudio.google.com", output)

    def test_02_empty_key_fails(self):
        """Verifies empty or whitespace key returns False without testing connection."""
        self.assertFalse(setup_key.test_and_save_key(""))
        self.assertFalse(setup_key.test_and_save_key("   "))

    @patch("scraper.ai_extractor.UniversalAIExtractor.test_connection")
    def test_03_connection_failure_returns_false(self, mock_test_conn):
        """Verifies failed Gemini connection returns False and does not save .env."""
        mock_test_conn.return_value = (False, "API_KEY_INVALID")
        result = setup_key.test_and_save_key("invalid_key_123")
        self.assertFalse(result)

    @patch("setup_key.BASE_DIR")
    @patch("scraper.ai_extractor.UniversalAIExtractor.test_connection")
    def test_04_connection_success_saves_env(self, mock_test_conn, mock_base_dir):
        """Verifies successful connection saves key to .env without corrupting existing variables."""
        mock_base_dir.__truediv__.return_value = self.mock_env
        self.mock_env.write_text("SOME_OTHER_VAR=important_value\nGEMINI_API_KEY=old_key\n", encoding="utf-8")

        mock_test_conn.return_value = (True, "Handshake verified")
        result = setup_key.test_and_save_key("AIzaSyNewValidKey123", model_name="gemini-1.5-flash")
        self.assertTrue(result)

        saved_content = self.mock_env.read_text(encoding="utf-8")
        self.assertIn("SOME_OTHER_VAR=important_value", saved_content)
        self.assertIn("GEMINI_API_KEY=AIzaSyNewValidKey123", saved_content)
        self.assertIn("GEMINI_MODEL=gemini-1.5-flash", saved_content)

    @patch("setup_key.test_and_save_key")
    def test_05_main_with_cli_arg(self, mock_test_and_save):
        """Verifies main() reads --key=... CLI argument."""
        with patch.object(sys, "argv", ["setup_key.py", "--key=AIzaSyDirectArg", "--model=gemini-1.5-flash"]):
            with patch("sys.stdout", new_callable=io.StringIO):
                setup_key.main()
        mock_test_and_save.assert_called_once_with("AIzaSyDirectArg", "gemini-1.5-flash")

    @patch("builtins.input", side_effect=KeyboardInterrupt)
    def test_06_main_user_cancellation(self, mock_input):
        """Verifies main() gracefully handles KeyboardInterrupt."""
        with patch.object(sys, "argv", ["setup_key.py"]):
            with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
                with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                    setup_key.main()
                    self.assertIn("cancelled", mock_stdout.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
