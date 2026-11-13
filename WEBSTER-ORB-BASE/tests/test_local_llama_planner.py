"""Tests for Llama's structured, non-executing action planner."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from assistant.commands import CommandRouter
from assistant.local_llama_engine import LlamaCppEngine
from assistant.offline_action_router import ActionIntent
from actions import ActionManager


class FakeModel:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def create_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "choices": [{
                "message": {"content": json.dumps(self.payload)}
            }]
        }


class TestLlamaStructuredPlanner(unittest.TestCase):
    def make_engine(self, payload):
        engine = LlamaCppEngine.__new__(LlamaCppEngine)
        engine._llama = FakeModel(payload)
        engine._offline = None
        return engine

    def test_returns_only_a_catalogued_action(self):
        engine = self.make_engine({
            "action_id": "create_folder",
            "arguments": "Homework",
            "confidence": 0.91,
        })
        actions = [
            SimpleNamespace(
                action_id="create_folder",
                description="Create a new folder.",
            )
        ]

        result = engine.plan_action("Make a Homework folder", actions)

        self.assertIsInstance(result, ActionIntent)
        self.assertEqual(result.action_id, "create_folder")
        self.assertEqual(result.arguments, "Homework")
        self.assertEqual(result.score, 0.91)
        self.assertEqual(engine._llama.calls[0]["response_format"], {"type": "json_object"})

    def test_rejects_action_id_not_in_catalog(self):
        engine = self.make_engine({
            "action_id": "delete_everything",
            "arguments": "",
            "confidence": 1.0,
        })
        result = engine.plan_action(
            "Do something",
            [SimpleNamespace(action_id="create_folder", description="Create folder.")],
        )
        self.assertIsNone(result)

    def test_rejects_low_confidence(self):
        engine = self.make_engine({
            "action_id": "create_folder",
            "arguments": "Notes",
            "confidence": 0.51,
        })
        result = engine.plan_action(
            "Make Notes",
            [SimpleNamespace(action_id="create_folder", description="Create folder.")],
        )
        self.assertIsNone(result)

    def test_rejects_multiline_or_oversized_arguments(self):
        for arguments in ("line one\nline two", "x" * 2049):
            with self.subTest(arguments_length=len(arguments)):
                engine = self.make_engine({
                    "action_id": "create_folder",
                    "arguments": arguments,
                    "confidence": 0.99,
                })
                result = engine.plan_action(
                    "Make a folder",
                    [SimpleNamespace(action_id="create_folder", description="Create folder.")],
                )
                self.assertIsNone(result)

    def test_model_error_switches_to_builtin_offline_engine(self):
        engine = LlamaCppEngine.__new__(LlamaCppEngine)
        engine._llama = None
        engine._offline = None
        engine._runtime = None
        engine._load_error = "test unavailable"
        engine._load_lock = Mock()

        result = engine.plan_action(
            "Please create a folder",
            [SimpleNamespace(action_id="create_folder", description="Create folder.")],
        )

        self.assertIsNone(result)
        self.assertIsNotNone(engine._offline)
        self.assertEqual(engine._offline.status, "LOCAL")


class TestCommandRouterLlamaFallback(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp_dir.name)
        self.manager = ActionManager(self.folder)
        (self.folder / "desktop_overview.py").write_text(
            'ACTION_ID = "desktop_overview"\n'
            'DESCRIPTION = "Show an overview of desktop windows."\n'
            'def run(): return "overview ready"\n',
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_llama_planner_handles_natural_paraphrase_after_lexical_abstention(self):
        planner = Mock(return_value=ActionIntent("desktop_overview", "", 0.94))
        router = CommandRouter(
            action_provider=self.manager,
            action_planner=planner,
        )

        result = router.route("Could you tidy up my desktop?")

        planner.assert_called_once()
        self.assertTrue(result.handled)
        self.assertTrue(result.requires_confirmation)
        self.assertEqual(result.action_id, "extension:desktop_overview")

    def test_regular_question_does_not_trigger_action_planner(self):
        planner = Mock(return_value=None)
        router = CommandRouter(
            action_provider=self.manager,
            action_planner=planner,
        )

        result = router.route("Explain photosynthesis in simple terms.")

        planner.assert_not_called()
        self.assertFalse(result.handled)

    def test_planner_cannot_select_unavailable_action(self):
        planner = Mock(return_value=ActionIntent("not_installed", "", 0.99))
        router = CommandRouter(
            action_provider=self.manager,
            action_planner=planner,
        )

        result = router.route("Could you tidy up my desktop?")

        self.assertFalse(result.handled)


if __name__ == "__main__":
    unittest.main(verbosity=2)
