"""Tests for the first ten WEBSTER desktop actions."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from actions import ActionManager
from actions import _desktop_helpers as desktop
from assistant.commands import CommandRouter


class TestDesktopActionValidation(unittest.TestCase):
    def test_required_argument_and_quoted_paths(self):
        self.assertEqual(
            desktop.require_argument('"C:\\Users\\Student\\My Folder"', "path"),
            "C:\\Users\\Student\\My Folder",
        )
        with self.assertRaises(ValueError):
            desktop.require_argument(" ", "application name")
        with self.assertRaises(ValueError):
            desktop.require_argument("bad\nvalue", "argument")

    def test_open_app_rejects_unapproved_application(self):
        with self.assertRaises(ValueError):
            desktop.open_application("some random executable")

    def test_open_website_rejects_non_http_schemes(self):
        for url in ("file:///C:/secret.txt", "javascript:alert(1)", "ftp://example.com"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                desktop.open_website(url)

    def test_open_website_rejects_embedded_credentials(self):
        with self.assertRaises(ValueError):
            desktop.open_website("https://user:pass@example.com")

    @patch("actions._desktop_helpers.webbrowser.open", return_value=True)
    def test_open_website_opens_valid_url(self, open_browser):
        result = desktop.open_website("https://example.com/path")
        open_browser.assert_called_once_with("https://example.com/path", new=2)
        self.assertIn("example.com", result)

    def test_open_folder_requires_existing_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            file_path = folder / "note.txt"
            file_path.write_text("note", encoding="utf-8")
            with self.assertRaises(ValueError):
                desktop.open_folder(str(file_path))
            with self.assertRaises(FileNotFoundError):
                desktop.open_folder(str(folder / "missing"))

    def test_open_settings_rejects_unknown_page(self):
        with self.assertRaises(ValueError):
            desktop.open_settings("run powershell")

    def test_close_app_rejects_unapproved_application(self):
        with self.assertRaises(ValueError):
            desktop.close_application("unknown process")

    def test_window_actions_fail_cleanly_off_windows(self):
        with patch("actions._desktop_helpers.platform.system", return_value="Linux"):
            with self.assertRaises(RuntimeError):
                desktop.minimize_active_window()
            with self.assertRaises(RuntimeError):
                desktop.toggle_maximize_active_window()
            with self.assertRaises(RuntimeError):
                desktop.switch_window("browser")
            with self.assertRaises(RuntimeError):
                desktop.lock_screen()
            with self.assertRaises(RuntimeError):
                desktop.show_desktop_overview()


class TestActionArgumentTransport(unittest.TestCase):
    def test_arguments_reach_action_only_after_confirmation_callback(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "echo.py").write_text(
                'ACTION_ID = "echo_args"\n'
                'DESCRIPTION = "Returns supplied arguments"\n'
                'def run(): return ACTION_ARGUMENTS\n',
                encoding="utf-8",
            )
            manager = ActionManager(folder)
            router = CommandRouter(action_provider=manager)
            result = router.route("run action echo_args hello from WEBSTER")
            self.assertTrue(result.requires_confirmation)
            self.assertIn("hello from WEBSTER", result.text)
            self.assertEqual(result.action(), "hello from WEBSTER")

    def test_argument_validation_rejects_multiline_and_oversize(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "echo.py").write_text(
                'ACTION_ID = "echo_args"\n'
                'DESCRIPTION = "Returns supplied arguments"\n'
                'def run(): return ACTION_ARGUMENTS\n',
                encoding="utf-8",
            )
            manager = ActionManager(folder)
            with self.assertRaises(Exception):
                manager.execute("echo_args", arguments="first\nsecond")
            with self.assertRaises(Exception):
                manager.execute("echo_args", arguments="x" * 2049)


if __name__ == "__main__":
    unittest.main(verbosity=2)
