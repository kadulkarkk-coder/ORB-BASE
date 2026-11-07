"""Tests for WEBSTER's flat action folder."""

import tempfile
import unittest
from pathlib import Path

from actions import ActionError, ActionManager


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

    def test_nested_files_are_not_discovered(self):
        nested = self.folder / "nested"
        nested.mkdir()
        (nested / "hidden.py").write_text('ACTION_ID = "hidden"\nDESCRIPTION = "Hidden"\ndef run(): return "x"\n', encoding="utf-8")
        self.assertEqual(self.manager.discover(), [])

    def test_missing_action_is_rejected(self):
        with self.assertRaises(ActionError):
            self.manager.execute("missing")

    def test_non_text_return_is_rejected(self):
        self.write_action("wrong.py", 'ACTION_ID = "wrong_type"\nDESCRIPTION = "Wrong return"\ndef run(): return 42\n')
        with self.assertRaises(ActionError):
            self.manager.execute("wrong_type")


if __name__ == "__main__":
    unittest.main(verbosity=2)
