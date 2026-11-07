"""Tests for the first ten WEBSTER desktop actions."""
import tempfile
import unittest
import sys
from types import SimpleNamespace
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


class TestG5AudioAndSystemActions(unittest.TestCase):
    @patch("actions._desktop_helpers.platform.system", return_value="Linux")
    def test_windows_media_keys_fail_cleanly_off_windows(self, _system):
        for action in (
            desktop.volume_up, desktop.volume_down, desktop.volume_mute,
            desktop.media_play_pause, desktop.media_next, desktop.media_previous,
        ):
            with self.subTest(action=action.__name__), self.assertRaises(RuntimeError):
                action()

    @patch("actions._desktop_helpers.platform.system", return_value="Windows")
    @patch("actions._desktop_helpers.ctypes.windll", create=True)
    def test_volume_up_sends_expected_key(self, windll, _system):
        desktop.volume_up()
        self.assertEqual(windll.user32.keybd_event.call_count, 2)
        self.assertEqual(windll.user32.keybd_event.call_args_list[0].args[0], 0xAF)
        self.assertEqual(windll.user32.keybd_event.call_args_list[1].args[2], 0x0002)

    @patch("actions._desktop_helpers.platform.system", return_value="Windows")
    @patch("actions._desktop_helpers.ctypes.windll", create=True)
    def test_media_next_sends_next_track_key(self, windll, _system):
        desktop.media_next()
        self.assertEqual(windll.user32.keybd_event.call_args_list[0].args[0], 0xB0)

    def test_system_status_formats_metrics(self):
        memory = SimpleNamespace(percent=50.0, used=2 * 1024**3, total=4 * 1024**3)
        disk = SimpleNamespace(percent=75.0, used=30 * 1024**3, total=40 * 1024**3)
        fake_psutil = SimpleNamespace(
            cpu_percent=lambda interval: 12.5,
            virtual_memory=lambda: memory,
            disk_usage=lambda path: disk,
        )
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            with patch("actions._desktop_helpers.Path.home", return_value=Path("C:/")):
                result = desktop.system_status()
        self.assertIn("CPU usage: 12.5%", result)
        self.assertIn("RAM usage: 50.0%", result)
        self.assertIn("Disk usage", result)

    def test_battery_status_handles_missing_battery(self):
        fake_psutil = SimpleNamespace(sensors_battery=lambda: None)
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            self.assertIn("No battery information", desktop.battery_status())

    def test_battery_status_reports_charging(self):
        battery = SimpleNamespace(percent=81, power_plugged=True, secsleft=3600)
        fake_psutil = SimpleNamespace(
            POWER_TIME_UNLIMITED=-2,
            POWER_TIME_UNKNOWN=-1,
            sensors_battery=lambda: battery,
        )
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            result = desktop.battery_status()
        self.assertIn("81%", result)
        self.assertIn("charging", result)
        self.assertIn("1h 0m", result)

    def test_network_status_lists_active_interfaces(self):
        import socket
        active = SimpleNamespace(isup=True)
        offline = SimpleNamespace(isup=False)
        address = SimpleNamespace(family=socket.AF_INET, address="192.168.1.20")
        fake_psutil = SimpleNamespace(
            net_if_stats=lambda: {"Ethernet": active, "Offline": offline},
            net_if_addrs=lambda: {"Ethernet": [address]},
        )
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            result = desktop.network_status()
        self.assertIn("Ethernet: up", result)
        self.assertIn("192.168.1.20", result)
        self.assertNotIn("Offline", result)

    def test_current_datetime_includes_date_time_and_timezone(self):
        result = desktop.current_datetime()
        self.assertIn("Date:", result)
        self.assertIn("Time:", result)
        self.assertIn("Timezone:", result)

    def test_new_action_files_are_discoverable(self):
        from actions import ActionManager
        manager = ActionManager()
        ids = {item.action_id for item in manager.discover()}
        expected = {
            "volume_up", "volume_down", "volume_mute", "media_play_pause",
            "media_next", "media_previous", "system_status", "battery_status",
            "network_status", "current_datetime",
        }
        self.assertTrue(expected.issubset(ids))


if __name__ == "__main__":
    unittest.main(verbosity=2)
