"""Tests for G5.41–G5.50 system and archive actions."""
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from actions import ActionManager
from actions import _system_helpers as helpers


class TestG541ToG550(unittest.TestCase):
    def test_clipboard_copy_uses_tk_clipboard(self):
        class FakeRoot:
            def __init__(self): self.value = None
            def withdraw(self): pass
            def clipboard_clear(self): pass
            def clipboard_append(self, value): self.value = value
            def update(self): pass
            def destroy(self): pass
        root = FakeRoot()
        fake_tk = type("FakeTk", (), {"Tk": lambda: root})
        with patch.dict("sys.modules", {"tkinter": fake_tk}):
            self.assertIn("Copied 5 characters", helpers.clipboard_copy("hello"))
            self.assertEqual(root.value, "hello")

    def test_clipboard_copy_enforces_size(self):
        with self.assertRaises(ValueError):
            helpers.clipboard_copy("x" * (16 * 1024 + 1))

    def test_create_zip_archive_and_inspect(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "source"; source.mkdir()
            (source / "note.txt").write_text("hello", encoding="utf-8")
            archive = root / "notes.zip"
            self.assertIn("1 files", helpers.create_zip_archive(f"{source} | {archive}"))
            self.assertIn("note.txt", helpers.inspect_zip_archive(str(archive)))
            with self.assertRaises(FileExistsError):
                helpers.create_zip_archive(f"{source} | {archive}")

    def test_extract_zip_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); archive = root / "a.zip"; target = root / "out"; target.mkdir()
            with zipfile.ZipFile(archive, "w") as z: z.writestr("docs/note.txt", "hello")
            self.assertIn("Extracted 1 files", helpers.extract_zip_archive(f"{archive} | {target}"))
            self.assertEqual((target / "docs" / "note.txt").read_text(encoding="utf-8"), "hello")

    def test_extract_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); archive = root / "bad.zip"; target = root / "out"; target.mkdir()
            with zipfile.ZipFile(archive, "w") as z: z.writestr("../outside.txt", "bad")
            with self.assertRaises(ValueError):
                helpers.extract_zip_archive(f"{archive} | {target}")
            self.assertFalse((root / "outside.txt").exists())

    def test_extract_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); archive = root / "a.zip"; target = root / "out"; target.mkdir()
            (target / "note.txt").write_text("keep", encoding="utf-8")
            with zipfile.ZipFile(archive, "w") as z: z.writestr("note.txt", "replace")
            with self.assertRaises(FileExistsError):
                helpers.extract_zip_archive(f"{archive} | {target}")
            self.assertEqual((target / "note.txt").read_text(encoding="utf-8"), "keep")

    def test_inspect_rejects_non_zip(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "file.txt"; p.write_text("x")
            with self.assertRaises(ValueError): helpers.inspect_zip_archive(str(p))

    def test_uptime_reports_boot_time(self):
        result = helpers.uptime_status()
        self.assertIn("System uptime:", result)
        self.assertIn("Boot time:", result)

    def test_process_summary_is_read_only(self):
        result = helpers.process_summary()
        self.assertIn("Processes observed:", result)
        self.assertIn("Currently running:", result)

    def test_top_processes_is_bounded(self):
        result = helpers.top_processes()
        self.assertIn("Top processes", result)
        self.assertLessEqual(len(result.splitlines()), 11)

    def test_dns_lookup_rejects_url_and_port(self):
        for value in ("https://example.com", "example.com:443", "../example.com"):
            with self.assertRaises(ValueError): helpers.dns_lookup(value)

    def test_dns_lookup_uses_resolver(self):
        with patch("actions._system_helpers.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("192.0.2.1", 0))]):
            self.assertIn("192.0.2.1", helpers.dns_lookup("example.com"))

    def test_python_environment_reports_runtime(self):
        result = helpers.python_environment()
        self.assertIn("Python:", result)
        self.assertIn("Executable:", result)

    def test_disk_volumes_reports_mounts(self):
        result = helpers.disk_volumes()
        self.assertIn("Mounted volumes:", result)

    def test_no_argument_actions_reject_arguments(self):
        for fn in (helpers.uptime_status, helpers.process_summary, helpers.top_processes, helpers.python_environment, helpers.disk_volumes):
            with self.assertRaises(ValueError): fn("unexpected")

    def test_new_actions_are_discoverable(self):
        ids = {item.action_id for item in ActionManager().discover()}
        expected = {"clipboard_copy", "create_zip_archive", "inspect_zip_archive", "extract_zip_archive",
                    "uptime_status", "process_summary", "top_processes", "dns_lookup", "python_environment", "disk_volumes"}
        self.assertTrue(expected.issubset(ids))


if __name__ == "__main__":
    unittest.main(verbosity=2)
