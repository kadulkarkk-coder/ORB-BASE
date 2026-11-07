"""Tests for G5.31–G5.40 bounded file and text utilities."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from actions import ActionManager
from actions import _file_helpers as helpers

class TestG531ToG540(unittest.TestCase):
    def test_copy_file_copies_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, destination = root / "a.txt", root / "b.txt"
            source.write_text("hello", encoding="utf-8")
            helpers.copy_file(f"{source} | {destination}")
            self.assertEqual(destination.read_text(encoding="utf-8"), "hello")
            with self.assertRaises(FileExistsError):
                helpers.copy_file(f"{source} | {destination}")

    def test_copy_file_requires_existing_destination_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "a.txt"
            source.write_text("x", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                helpers.copy_file(f"{source} | {Path(temp) / 'missing' / 'b.txt'}")

    def test_rename_file_renames_in_same_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            source, destination = Path(temp) / "old.txt", Path(temp) / "new.txt"
            source.write_text("data", encoding="utf-8")
            helpers.rename_file(f"{source} | new.txt")
            self.assertFalse(source.exists())
            self.assertEqual(destination.read_text(encoding="utf-8"), "data")

    def test_rename_file_rejects_path_and_existing_target(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "old.txt"
            target = Path(temp) / "taken.txt"
            source.write_text("a", encoding="utf-8")
            target.write_text("b", encoding="utf-8")
            with self.assertRaises(ValueError):
                helpers.rename_file(f"{source} | ../escape.txt")
            with self.assertRaises(FileExistsError):
                helpers.rename_file(f"{source} | taken.txt")

    def test_hash_file_matches_sha256(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "hash.txt"
            path.write_bytes(b"hello")
            expected = hashlib.sha256(b"hello").hexdigest()
            self.assertIn(expected, helpers.hash_file(str(path)))

    def test_word_count_counts_words(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "words.txt"
            path.write_text("one two\nthree", encoding="utf-8")
            self.assertIn("3 words", helpers.word_count(str(path)))

    def test_text_statistics_reports_lines_and_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "stats.md"
            path.write_text("one\ntwo", encoding="utf-8")
            result = helpers.text_statistics(str(path))
            self.assertIn("2 lines", result)
            self.assertIn("7 UTF-8 bytes", result)

    def test_convert_units_length(self):
        self.assertIn("5000", helpers.convert_units("5 km to m"))

    def test_convert_units_temperature(self):
        self.assertIn("32", helpers.convert_units("0 c to f"))

    def test_convert_units_rejects_mixed_categories(self):
        with self.assertRaises(ValueError):
            helpers.convert_units("5 km to kg")

    def test_convert_units_rejects_non_finite_or_huge_value(self):
        with self.assertRaises(ValueError):
            helpers.convert_units("999999999999999999999999999999 km to m")

    def test_generate_uuid_returns_uuid(self):
        value = helpers.generate_uuid("")
        self.assertRegex(value, r"UUID: [0-9a-f-]{36}")

    def test_generate_uuid_rejects_arguments(self):
        with self.assertRaises(ValueError):
            helpers.generate_uuid("anything")

    def test_compare_text_files_identical(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / "a.txt", Path(temp) / "b.txt"
            a.write_text("same", encoding="utf-8")
            b.write_text("same", encoding="utf-8")
            self.assertIn("identical", helpers.compare_text_files(f"{a} | {b}"))

    def test_compare_text_files_returns_diff(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / "a.txt", Path(temp) / "b.txt"
            a.write_text("alpha", encoding="utf-8")
            b.write_text("beta", encoding="utf-8")
            result = helpers.compare_text_files(f"{a} | {b}")
            self.assertIn("-alpha", result)
            self.assertIn("+beta", result)

    def test_search_text_in_folder_finds_phrase(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "notes.txt"
            path.write_text("hello\nWEBSTER is here", encoding="utf-8")
            result = helpers.search_text_in_folder(f"{temp} | WEBSTER")
            self.assertIn("notes.txt:2", result)

    def test_search_text_in_folder_ignores_binary_extension(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "secret.bin"
            path.write_text("needle", encoding="utf-8")
            result = helpers.search_text_in_folder(f"{temp} | needle")
            self.assertIn("No matches", result)

    def test_validate_json_file_accepts_valid_json(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "data.json"
            path.write_text(json.dumps({"ok": True}), encoding="utf-8")
            self.assertIn("Valid JSON", helpers.validate_json_file(str(path)))

    def test_validate_json_file_rejects_invalid_json(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.json"
            path.write_text("{bad", encoding="utf-8")
            with self.assertRaises(ValueError):
                helpers.validate_json_file(str(path))

    def test_validate_json_file_rejects_non_json_suffix(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "data.txt"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                helpers.validate_json_file(str(path))

    def test_new_actions_are_discoverable(self):
        ids = {item.action_id for item in ActionManager().discover()}
        expected = {
            "copy_file", "rename_file", "hash_file", "word_count",
            "text_statistics", "convert_units", "generate_uuid",
            "compare_text_files", "search_text_in_folder", "validate_json_file",
        }
        self.assertTrue(expected.issubset(ids))

if __name__ == "__main__":
    unittest.main(verbosity=2)
