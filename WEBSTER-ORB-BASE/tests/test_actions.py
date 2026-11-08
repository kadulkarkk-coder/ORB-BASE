"""Tests for WEBSTER's flat action folder."""

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from actions import ActionError, ActionManager
from assistant.commands import CommandRouter
from system.niyantrak import Niyantrak, PermissionStatus
from assistant.assistant_manager import AssistantManager


class TestActionManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp_dir.name)
        self.manager = ActionManager(self.folder)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_action(self, filename, source):
        (self.folder / filename).write_text(source, encoding="utf-8")

    def test_discovers_metadata_without_importing_module(self):
        marker = self.folder / "imported.txt"
        self.write_action("safe.py", f'''ACTION_ID = "safe_action"\nDESCRIPTION = "Safe test action"\nfrom pathlib import Path\ndef run():\n    return "ok"\nPath({str(marker)!r}).write_text("imported")\n''')
        items = self.manager.discover()
        self.assertEqual([item.action_id for item in items], ["safe_action"])
        self.assertFalse(marker.exists())

    def test_executes_only_when_execute_is_called(self):
        self.write_action("hello.py", 'ACTION_ID = "hello"\nDESCRIPTION = "Says hello"\ndef run():\n    return "hello from action"\n')
        self.assertEqual(self.manager.execute("hello"), "hello from action")

    def test_rejects_invalid_metadata_and_missing_run(self):
        self.write_action("bad_id.py", 'ACTION_ID = "Not Valid"\nDESCRIPTION = "Bad"\ndef run(): return "no"\n')
        self.write_action("no_run.py", 'ACTION_ID = "no_run"\nDESCRIPTION = "Missing run"\nVALUE = 1\n')
        self.assertEqual(self.manager.discover(), [])

    def test_duplicate_ids_are_excluded(self):
        source = 'ACTION_ID = "duplicate"\nDESCRIPTION = "Duplicate"\ndef run(): return "x"\n'
        self.write_action("one.py", source)
        self.write_action("two.py", source)
        self.assertEqual(self.manager.discover(), [])

    def test_repository_discovers_at_least_60_real_actions(self):
        found = ActionManager().discover()
        self.assertGreaterEqual(len(found), 60, [item.action_id for item in found])

    def test_action_manager_implementation_is_not_discovered(self):
        self.write_action(
            "action_manager.py",
            'ACTION_ID = "not_an_action"\n'
            'DESCRIPTION = "Internal manager module"\n'
            'def run(): return "should never be listed"\n',
        )
        self.write_action(
            "real_action.py",
            'ACTION_ID = "real_action"\n'
            'DESCRIPTION = "A real action"\n'
            'def run(): return "ok"\n',
        )
        self.assertEqual(
            [item.action_id for item in self.manager.discover()],
            ["real_action"],
        )

    def test_nested_files_are_not_discovered(self):
        nested = self.folder / "nested"
        nested.mkdir()
        (nested / "hidden.py").write_text('ACTION_ID = "hidden"\nDESCRIPTION = "Hidden"\ndef run(): return "x"\n', encoding="utf-8")
        self.assertEqual(self.manager.discover(), [])

    def test_missing_action_is_rejected(self):
        with self.assertRaises(ActionError):
            self.manager.execute("missing")

    def test_action_file_change_after_request_is_rejected(self):
        self.write_action("mutable.py", 'ACTION_ID = "mutable"\nDESCRIPTION = "Mutable action"\ndef run(): return "original"\n')
        manager = ActionManager(self.folder)
        router = CommandRouter(action_provider=manager)
        requested = router.route("run action mutable")
        self.write_action("mutable.py", 'ACTION_ID = "mutable"\nDESCRIPTION = "Mutable action"\ndef run(): return "changed"\n')
        with self.assertRaises(ActionError):
            requested.action()

    def test_non_text_return_is_rejected(self):
        self.write_action("wrong.py", 'ACTION_ID = "wrong_type"\nDESCRIPTION = "Wrong return"\ndef run(): return 42\n')
        with self.assertRaises(ActionError):
            self.manager.execute("wrong_type")



class TestActionCommandsAndPermissions(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp_dir.name)
        self.manager = ActionManager(self.folder)
        (self.folder / "hello.py").write_text(
            'ACTION_ID = "hello_action"\n'
            'DESCRIPTION = "A harmless test action"\n'
            'def run(): return "hello executed"\n',
            encoding="utf-8",
        )
        self.router = CommandRouter(action_provider=self.manager)
        self.policy = Niyantrak()
        self.policy.register_extension_action("extension:hello_action")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_list_actions_command(self):
        result = self.router.route("actions")
        self.assertTrue(result.handled)
        self.assertIn("hello_action", result.text)

    def test_natural_language_action_intent_is_local_and_confirmed(self):
        (self.folder / "calculate.py").write_text(
            'ACTION_ID = "calculate"\\n'
            'DESCRIPTION = "Calculate a basic arithmetic expression."\\n'
            'def run(): return "calculated: " + ACTION_ARGUMENTS\\n',
            encoding="utf-8",
        )
        result = self.router.route("please calculate 2 + 2")
        self.assertTrue(result.handled)
        self.assertTrue(result.requires_confirmation)
        self.assertIn("Arguments: 2 + 2", result.text)
        self.assertEqual(result.action_id, "extension:calculate")

    def test_run_action_requires_explicit_confirmation(self):
        result = self.router.route("run action hello_action")
        self.assertTrue(result.handled)
        self.assertTrue(result.requires_confirmation)
        self.assertEqual(result.action_id, "extension:hello_action")
        self.assertEqual(
            self.policy.evaluate(result.action_id).status,
            PermissionStatus.CONFIRMATION_REQUIRED,
        )
        self.assertTrue(self.policy.evaluate(result.action_id, confirmed=True).allowed)


    def test_assistant_manager_registers_and_gates_folder_actions(self):
        with patch("assistant.assistant_manager.Smriti"), \
             patch("assistant.assistant_manager.Gyaan"), \
             patch("assistant.assistant_manager.create_engine"), \
             patch("assistant.assistant_manager.SpeechEngine"), \
             patch("actions.action_manager.ActionManager.execute", return_value="EXECUTED") as execute:
            manager = AssistantManager()
            try:
                self.assertIn("extension:hello_webster", manager.niyantrak.registered_actions)
                result = manager.router.route("run action hello_webster")
                self.assertTrue(result.requires_confirmation)
                manager._handle_command_result(result)
                self.assertIs(manager._pending_command, result)
                execute.assert_not_called()

                manager._handle_confirmation("yes")
                execute.assert_called_once()
                self.assertEqual(execute.call_args.args, ("hello_webster",))
                self.assertIn("expected_hash", execute.call_args.kwargs)
                self.assertIsNone(manager._pending_command)
            finally:
                manager.shutdown()

    def test_unregistered_extension_action_is_denied(self):
        self.assertEqual(
            self.policy.evaluate("extension:not_registered", confirmed=True).status,
            PermissionStatus.DENIED,
        )

    def test_extension_registration_rejects_malformed_ids(self):
        self.assertFalse(self.policy.register_extension_action("open_url"))
        self.assertFalse(self.policy.register_extension_action("extension:../bad"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
