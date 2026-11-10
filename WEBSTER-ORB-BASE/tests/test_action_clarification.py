"""Tests for multi-turn missing-argument clarification in CommandRouter."""
import unittest
from types import SimpleNamespace

from assistant.commands import CommandRouter


class FakeActionManager:
    def __init__(self):
        self.item = SimpleNamespace(
            action_id="create_folder",
            description="Create a new folder at a chosen path.",
            content_hash="test-hash",
            permission_id="extension:create_folder",
        )

    def discover(self):
        return [self.item]

    def get(self, action_id):
        return self.item if action_id == self.item.action_id else None

    def execute(self, action_id, *, expected_hash=None, arguments=""):
        return f"executed {action_id}: {arguments}"


class TestActionClarification(unittest.TestCase):
    def test_missing_folder_name_prompts_then_uses_followup(self):
        router = CommandRouter(action_provider=FakeActionManager())

        first = router.route("create a folder")
        self.assertTrue(first.handled)
        self.assertFalse(first.requires_confirmation)
        self.assertIn("name the folder", first.text.lower())

        second = router.route("Homework on desktop")
        self.assertTrue(second.handled)
        self.assertTrue(second.requires_confirmation)
        self.assertEqual(second.action_id, "extension:create_folder")
        self.assertIn("~/Desktop/Homework", second.text)

    def test_pending_clarification_can_be_cancelled(self):
        router = CommandRouter(action_provider=FakeActionManager())
        router.route("create a folder")

        result = router.route("cancel")
        self.assertTrue(result.handled)
        self.assertIn("cancelled", result.text.lower())

    def test_incomplete_followup_keeps_request_pending(self):
        router = CommandRouter(action_provider=FakeActionManager())
        router.route("create a folder")

        result = router.route("on desktop")
        self.assertTrue(result.handled)
        self.assertFalse(result.requires_confirmation)
        self.assertIn("still need", result.text.lower())


if __name__ == "__main__":
    unittest.main()
