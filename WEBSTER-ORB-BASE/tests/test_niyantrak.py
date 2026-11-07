"""Tests for Niyantrak's fail-closed system-action permission gate."""

import unittest
from unittest.mock import patch

from assistant.assistant_manager import AssistantManager
from assistant.commands import CommandResult, CommandRouter
from system.niyantrak import Niyantrak, PermissionStatus


class TestNiyantrakPolicy(unittest.TestCase):
    def setUp(self):
        self.policy = Niyantrak()

    def test_missing_action_identifier_is_denied(self):
        decision = self.policy.evaluate(None)
        self.assertEqual(decision.status, PermissionStatus.DENIED)

    def test_non_string_action_identifier_is_denied(self):
        decision = self.policy.evaluate(123)
        self.assertEqual(decision.status, PermissionStatus.DENIED)

    def test_blank_action_identifier_is_denied(self):
        decision = self.policy.evaluate("   ")
        self.assertEqual(decision.status, PermissionStatus.DENIED)

    def test_unknown_action_is_denied_even_when_confirmed(self):
        decision = self.policy.evaluate(
            "run_arbitrary_command",
            confirmed=True,
        )
        self.assertEqual(decision.status, PermissionStatus.DENIED)

    def test_known_desktop_action_requires_confirmation(self):
        decision = self.policy.evaluate("open_app")
        self.assertEqual(
            decision.status,
            PermissionStatus.CONFIRMATION_REQUIRED,
        )

    def test_truthy_non_boolean_confirmation_is_not_accepted(self):
        for value in ("yes", 1, object()):
            with self.subTest(value=value):
                decision = self.policy.evaluate(
                    "open_url",
                    confirmed=value,
                )
                self.assertEqual(
                    decision.status,
                    PermissionStatus.CONFIRMATION_REQUIRED,
                )

    def test_known_action_is_allowed_after_literal_true_confirmation(self):
        decision = self.policy.evaluate("open_url", confirmed=True)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.status, PermissionStatus.ALLOWED)

    def test_action_identifiers_are_normalized(self):
        decision = self.policy.evaluate(" OPEN_APP ", confirmed=True)
        self.assertTrue(decision.allowed)

    def test_registered_actions_are_exposed_as_immutable_set(self):
        actions = self.policy.registered_actions
        self.assertEqual(
            actions,
            frozenset({"open_app", "open_url", "sleep_display"}),
        )
        with self.assertRaises(AttributeError):
            actions.add("arbitrary_action")

    def test_confirmation_query_rejects_unknown_and_malformed_ids(self):
        self.assertTrue(self.policy.requires_confirmation("open_app"))
        self.assertFalse(self.policy.requires_confirmation("unknown"))
        self.assertFalse(self.policy.requires_confirmation(None))


class TestCommandPermissionMetadata(unittest.TestCase):
    def setUp(self):
        self.router = CommandRouter()

    def test_open_app_is_marked_for_confirmation(self):
        result = self.router.route("open chrome")
        self.assertTrue(result.handled)
        self.assertTrue(result.requires_confirmation)
        self.assertEqual(result.action_id, "open_app")

    def test_open_url_is_marked_for_confirmation(self):
        result = self.router.route("open https://example.com")
        self.assertTrue(result.handled)
        self.assertTrue(result.requires_confirmation)
        self.assertEqual(result.action_id, "open_url")

    def test_sleep_display_is_marked_for_confirmation(self):
        result = self.router.route("sleep display")
        self.assertTrue(result.handled)
        self.assertTrue(result.requires_confirmation)
        self.assertEqual(result.action_id, "sleep_display")

    def test_quit_is_marked_for_confirmation(self):
        result = self.router.route("quit")
        self.assertTrue(result.handled)
        self.assertTrue(result.requires_confirmation)
        self.assertEqual(result.ui_action, "quit")


class TestAssistantNiyantrakIntegration(unittest.TestCase):
    def _manager(self):
        with patch("assistant.assistant_manager.Smriti"), \
             patch("assistant.assistant_manager.create_engine"), \
             patch("assistant.assistant_manager.SpeechEngine"):
            manager = AssistantManager()
        manager.tts_enabled = False
        self.addCleanup(manager.shutdown)
        return manager

    def test_action_waits_for_yes_confirmation(self):
        manager = self._manager()
        calls = []
        result = CommandResult(
            handled=True,
            text="Open test application?",
            requires_confirmation=True,
            action=lambda: calls.append("ran") or "done",
            action_id="open_app",
        )

        manager._handle_command_result(result)
        self.assertEqual(calls, [])
        self.assertIs(manager._pending_command, result)

        manager._handle_confirmation("yes")
        self.assertEqual(calls, ["ran"])
        self.assertIsNone(manager._pending_command)

    def test_action_is_not_run_when_confirmation_is_cancelled(self):
        manager = self._manager()
        calls = []
        result = CommandResult(
            handled=True,
            text="Open test application?",
            requires_confirmation=True,
            action=lambda: calls.append("ran"),
            action_id="open_app",
        )

        manager._handle_command_result(result)
        manager._handle_confirmation("no")

        self.assertEqual(calls, [])
        self.assertIsNone(manager._pending_command)

    def test_unregistered_action_is_blocked(self):
        manager = self._manager()
        calls = []
        result = CommandResult(
            handled=True,
            text="Run unknown action?",
            action=lambda: calls.append("ran"),
            action_id="unknown_action",
        )

        manager._handle_command_result(result)

        self.assertEqual(calls, [])
        self.assertIsNone(manager._pending_command)

    def test_action_without_identifier_is_blocked(self):
        manager = self._manager()
        calls = []
        result = CommandResult(
            handled=True,
            text="Run unlabelled operation?",
            action=lambda: calls.append("ran"),
        )

        manager._handle_command_result(result)

        self.assertEqual(calls, [])
        self.assertIsNone(manager._pending_command)


if __name__ == "__main__":
    unittest.main(verbosity=2)
