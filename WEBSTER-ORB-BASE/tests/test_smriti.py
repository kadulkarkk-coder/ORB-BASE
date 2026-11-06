
"""Unit tests for WEBSTER's Smriti memory system."""

import tempfile
import unittest
from unittest.mock import patch

from pathlib import Path

from memory import Smriti, SmritiError
from assistant.commands import CommandRouter
from assistant.assistant_manager import AssistantManager


class TestSmriti(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "test_smriti.db"
        self.memory = Smriti(database_path=self.database)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_retrieve(self):
        self.memory.save("name", "WEBSTER", "identity")

        result = self.memory.get("name")

        self.assertIsNotNone(result)
        self.assertEqual(result["memory_value"], "WEBSTER")
        self.assertEqual(result["category"], "identity")

    def test_memory_persists_after_restart(self):
        self.memory.save("project", "WEBSTER", "projects")

        second_instance = Smriti(database_path=self.database)

        result = second_instance.get("project")

        self.assertIsNotNone(result)
        self.assertEqual(result["memory_value"], "WEBSTER")

    def test_update_existing_memory(self):
        self.memory.save("theme", "blue", "preferences")
        self.memory.save("theme", "cyan", "preferences")

        result = self.memory.get("theme")

        self.assertEqual(result["memory_value"], "cyan")
        self.assertEqual(self.memory.count(), 1)

    def test_search_memory(self):
        self.memory.save(
            "python_level",
            "Learning advanced Python",
            "education",
        )

        results = self.memory.search("advanced")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["memory_key"], "python_level")

    def test_list_by_category(self):
        self.memory.save("language", "English", "preferences")
        self.memory.save("project", "WEBSTER", "projects")

        results = self.memory.list_memories(category="preferences")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["memory_key"], "language")

    def test_delete_memory(self):
        self.memory.save("temporary", "test", "system")

        self.assertTrue(self.memory.delete("temporary"))
        self.assertIsNone(self.memory.get("temporary"))

    def test_delete_missing_memory(self):
        self.assertFalse(self.memory.delete("does_not_exist"))

    def test_clear_category(self):
        self.memory.save("a", "one", "temporary")
        self.memory.save("b", "two", "temporary")
        self.memory.save("c", "three", "permanent")

        deleted = self.memory.clear(category="temporary")

        self.assertEqual(deleted, 2)
        self.assertEqual(self.memory.count(), 1)

    def test_clear_all(self):
        self.memory.save("a", "one")
        self.memory.save("b", "two")

        deleted = self.memory.clear()

        self.assertEqual(deleted, 2)
        self.assertEqual(self.memory.count(), 0)

    def test_empty_key_rejected(self):
        with self.assertRaises(ValueError):
            self.memory.save("", "value")

    def test_empty_value_rejected(self):
        with self.assertRaises(ValueError):
            self.memory.save("key", "   ")

    def test_memory_metadata(self):
        self.memory.save("test", "value", "system")

        result = self.memory.get("test")

        self.assertIn("created_at", result)
        self.assertIn("updated_at", result)
        self.assertIn("id", result)


class TestSmritiCommandRouter(unittest.TestCase):
    """Verify explicit memory commands through the same router used by WEBSTER."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "router_smriti.db"
        self.memory = Smriti(database_path=self.database)
        self.router = CommandRouter(memory_provider=self.memory)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_remember_recall_list_and_forget(self):
        saved = self.router.route("remember favorite_language = Python")
        self.assertTrue(saved.handled)
        self.assertIn("saved", saved.text.lower())

        recalled = self.router.route("recall favorite_language")
        self.assertTrue(recalled.handled)
        self.assertIn("Python", recalled.text)

        listed = self.router.route("list memories")
        self.assertTrue(listed.handled)
        self.assertIn("favorite_language: Python", listed.text)

        forgotten = self.router.route("forget favorite_language")
        self.assertTrue(forgotten.handled)
        self.assertIsNone(self.memory.get("favorite_language"))

    def test_memory_commands_return_controlled_error_when_unavailable(self):
        router = CommandRouter(memory_provider=None)

        result = router.route("recall missing_key")

        self.assertTrue(result.handled)
        self.assertIn("unavailable", result.text.lower())

    def test_router_can_receive_memory_provider_after_initialization(self):
        router = CommandRouter()
        router.set_memory_provider(self.memory)

        result = router.route("remember project = WEBSTER")

        self.assertTrue(result.handled)
        self.assertEqual(
            self.memory.get("project")["memory_value"],
            "WEBSTER",
        )


    def test_assistant_manager_connects_smriti_to_router(self):
        with patch("assistant.assistant_manager.Smriti", return_value=self.memory), \
             patch("assistant.assistant_manager.create_engine"), \
             patch("assistant.assistant_manager.SpeechEngine"):
            manager = AssistantManager()

        self.assertIs(manager.router._memory, manager.memory)


if __name__ == "__main__":
    unittest.main(verbosity=2)
