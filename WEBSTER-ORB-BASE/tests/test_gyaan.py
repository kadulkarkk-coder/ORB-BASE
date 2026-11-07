"""Tests for Gyaan source-aware knowledge storage and retrieval."""

import tempfile
import unittest
from pathlib import Path

from knowledge import Gyaan, GyaanError
from assistant.commands import CommandRouter


class TestGyaan(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = Gyaan(Path(self.temp_dir.name) / "gyaan.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_and_get_preserves_source_metadata(self):
        self.store.add("Python basics", "Variables store values.", "My Python notes", "python, basics")
        item = self.store.get("python basics")
        self.assertEqual(item["content"], "Variables store values.")
        self.assertEqual(item["source"], "My Python notes")
        self.assertEqual(item["tags"], "python, basics")

    def test_search_ranks_title_and_returns_source(self):
        self.store.add("Python loops", "A loop repeats work.", "Class notes")
        self.store.add("History", "Python was created by Guido.", "Textbook, chapter 2")
        results = self.store.search("python loops")
        self.assertEqual(results[0]["title"], "Python loops")
        self.assertEqual(results[0]["source"], "Class notes")
        self.assertGreater(results[0]["score"], 0)

    def test_search_is_case_insensitive_and_empty_results_are_safe(self):
        self.store.add("Science", "Matter has mass.")
        self.assertEqual(len(self.store.search("MATTER")), 1)
        self.assertEqual(self.store.search("astronomy"), [])

    def test_update_by_title_keeps_one_record(self):
        self.store.add("Topic", "First version", "Book A")
        self.store.add("Topic", "Updated version", "Book B")
        self.assertEqual(self.store.count(), 1)
        self.assertEqual(self.store.get("Topic")["source"], "Book B")

    def test_data_persists_after_reopening(self):
        path = Path(self.temp_dir.name) / "persistent.db"
        first = Gyaan(path)
        first.add("Saved", "Persistent content", "Notebook")
        second = Gyaan(path)
        self.assertEqual(second.get("Saved")["content"], "Persistent content")

    def test_list_and_delete(self):
        self.store.add("One", "First")
        self.store.add("Two", "Second")
        self.assertEqual(len(self.store.list_items()), 2)
        self.assertTrue(self.store.delete("one"))
        self.assertFalse(self.store.delete("missing"))
        self.assertEqual(self.store.count(), 1)

    def test_rejects_empty_or_oversized_values(self):
        with self.assertRaises(ValueError):
            self.store.add(" ", "content")
        with self.assertRaises(ValueError):
            self.store.add("title", " ")
        with self.assertRaises(ValueError):
            self.store.add("title", "content", "x" * 501)

    def test_search_rejects_empty_query(self):
        with self.assertRaises(ValueError):
            self.store.search(" ")




class TestGyaanCommandRouter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = Gyaan(Path(self.temp_dir.name) / "commands.db")
        self.router = CommandRouter(gyaan_provider=self.store)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_search_list_and_delete_commands(self):
        added = self.router.route("knowledge add Python loops = A for-loop repeats a block")
        self.assertTrue(added.handled)
        self.assertIn("Gyaan", added.text)

        searched = self.router.route("knowledge search for-loop")
        self.assertTrue(searched.handled)
        self.assertIn("Source: User-provided", searched.text)
        self.assertIn("Python loops", searched.text)

        listed = self.router.route("list knowledge")
        self.assertIn("Python loops", listed.text)

        deleted = self.router.route("knowledge delete Python loops")
        self.assertIn("Deleted", deleted.text)
        self.assertEqual(self.store.count(), 0)

    def test_commands_report_unavailable_provider(self):
        result = CommandRouter().route("knowledge search physics")
        self.assertTrue(result.handled)
        self.assertIn("unavailable", result.text.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
