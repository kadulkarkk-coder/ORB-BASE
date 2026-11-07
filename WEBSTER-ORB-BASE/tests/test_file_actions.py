"""Tests for G5.21–G5.30 bounded file and utility actions."""
import tempfile
import unittest
from pathlib import Path
from actions import ActionManager
from actions import _file_helpers as helpers

class TestG5FileActions(unittest.TestCase):
    def test_calculator_basic_arithmetic(self):
        self.assertEqual(helpers.calculate("(2 + 3) * 4"), "(2 + 3) * 4 = 20")

    def test_calculator_rejects_python_execution(self):
        for value in ("__import__('os').system('whoami')", "open('x')", "2 < 3"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                helpers.calculate(value)

    def test_calculator_rejects_division_by_zero(self):
        with self.assertRaises(ValueError):
            helpers.calculate("10 / 0")

    def test_calculator_limits_exponent(self):
        with self.assertRaises(ValueError):
            helpers.calculate("2 ** 100")

    def test_create_folder_creates_new_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "new-folder"
            self.assertIn("Created folder", helpers.create_folder(str(target)))
            self.assertTrue(target.is_dir())

    def test_create_folder_does_not_replace_existing(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FileExistsError):
                helpers.create_folder(temp)

    def test_create_text_file_creates_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "note.txt"
            helpers.create_text_file(f"{target} | hello WEBSTER")
            self.assertEqual(target.read_text(encoding="utf-8"), "hello WEBSTER")
            with self.assertRaises(FileExistsError):
                helpers.create_text_file(f"{target} | replacement")

    def test_create_text_file_requires_text_extension(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                helpers.create_text_file(f"{Path(temp) / 'note.exe'} | content")

    def test_append_text_file_appends_only(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "note.txt"
            target.write_text("first", encoding="utf-8")
            helpers.append_text_file(f"{target} | second")
            self.assertEqual(target.read_text(encoding="utf-8"), "firstsecond")

    def test_append_text_file_requires_existing_file(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FileNotFoundError):
                helpers.append_text_file(f"{Path(temp) / 'missing.txt'} | text")

    def test_list_folder_lists_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "note.txt").write_text("x", encoding="utf-8")
            self.assertIn("note.txt", helpers.list_folder(temp))

    def test_search_files_matches_name_only(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "project-notes.txt"
            target.write_text("needle is in content only", encoding="utf-8")
            self.assertIn(str(target), helpers.search_files(f"{temp} | project"))
            self.assertIn("No filenames", helpers.search_files(f"{temp} | needle"))

    def test_search_files_requires_separator(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                helpers.search_files(temp)

    def test_file_info_reports_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "info.txt"
            target.write_text("hello", encoding="utf-8")
            result = helpers.file_info(str(target))
            self.assertIn("Size: 5 bytes", result)
            self.assertIn("info.txt", result)

    def test_read_text_file_reads_utf8(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "readme.md"
            target.write_text("hello", encoding="utf-8")
            self.assertIn("hello", helpers.read_text_file(str(target)))

    def test_read_text_file_rejects_binary_extension(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "image.png"
            target.write_bytes(b"not text")
            with self.assertRaises(ValueError):
                helpers.read_text_file(str(target))

    def test_read_text_file_enforces_size_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "large.txt"
            target.write_bytes(b"x" * (helpers.MAX_TEXT_BYTES + 1))
            with self.assertRaises(ValueError):
                helpers.read_text_file(str(target))

    def test_find_text_reports_line_numbers(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "notes.txt"
            target.write_text("alpha\nbeta needle\ngamma", encoding="utf-8")
            result = helpers.find_text_in_file(f"{target} | needle")
            self.assertIn("2: beta needle", result)

    def test_actions_are_discoverable(self):
        ids = {item.action_id for item in ActionManager().discover()}
        expected = {
            "calculate", "open_file", "create_folder", "create_text_file",
            "append_text_file", "list_folder", "search_files", "file_info",
            "read_text_file", "find_text_in_file",
        }
        self.assertTrue(expected.issubset(ids))

if __name__ == "__main__":
    unittest.main(verbosity=2)
