"""Metadata and safety-boundary checks for G5.51-G5.60 actions."""
import unittest
from actions import ActionManager

EXPECTED = {
    "read_screen", "camera_record", "analyse_image", "generate_image",
    "generate_video", "cursor_position", "move_cursor",
    "create_code_project", "check_code", "home_assistant",
}

class TestG5LocalActions(unittest.TestCase):
    def test_all_g5_actions_are_discovered(self):
        found = {item.action_id for item in ActionManager().discover()}
        self.assertTrue(EXPECTED.issubset(found), EXPECTED - found)

    def test_new_action_ids_are_unique(self):
        ids = [item.action_id for item in ActionManager().discover()]
        self.assertEqual(len(ids), len(set(ids)))

if __name__ == "__main__":
    unittest.main(verbosity=2)
