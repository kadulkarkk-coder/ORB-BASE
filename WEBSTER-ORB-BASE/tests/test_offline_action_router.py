"""Focused tests for WEBSTER's dependency-free intent classifier."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from assistant.offline_action_router import OfflineActionRouter


def action(action_id, description):
    return SimpleNamespace(action_id=action_id, description=description)


class TestOfflineActionRouter(unittest.TestCase):
    def setUp(self):
        self.router = OfflineActionRouter()
        self.actions = [
            action("create_folder", "Create a new folder at a chosen path."),
            action("create_text_file", "Create and write a text file or document."),
            action("open_app", "Launch or open an installed desktop application."),
            action("read_screen", "Read visible text from the computer screen."),
            action("calculate", "Calculate a basic arithmetic expression."),
            action("search_files", "Find files by their names or file patterns."),
            action("check_code", "Review and debug source code."),
            action("camera_record", "Record a video using the connected camera."),
            action("generate_image", "Generate an image from a text description."),
        ]

    def test_folder_request_with_desktop_location(self):
        result = self.router.route(
            "Hey Webster, please make a folder for my Science Project on desktop",
            self.actions,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.action_id, "create_folder")
        self.assertEqual(result.arguments, "~/Desktop/Science Project")

    def test_folder_request_named_without_explicit_action_id(self):
        result = self.router.route(
            "Could you create a folder called Homework",
            self.actions,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.action_id, "create_folder")
        self.assertEqual(result.arguments, "Homework")

    def test_open_application_uses_user_supplied_app_as_argument(self):
        result = self.router.route("Please launch Spotify", self.actions)
        self.assertIsNotNone(result)
        self.assertEqual(result.action_id, "open_app")
        self.assertEqual(result.arguments, "Spotify")

    def test_calculator_understands_spoken_operators(self):
        result = self.router.route("calculate 18 times 24 plus 6", self.actions)
        self.assertIsNotNone(result)
        self.assertEqual(result.action_id, "calculate")
        self.assertEqual(result.arguments, "18 * 24 + 6")

    def test_question_form_arithmetic_is_recognized(self):
        result = self.router.route("what is 18 times 24", self.actions)
        self.assertIsNotNone(result)
        self.assertEqual(result.action_id, "calculate")
        self.assertEqual(result.arguments, "18 * 24")

    def test_screen_reading_is_not_confused_with_file_reading(self):
        result = self.router.route("read what's on my screen", self.actions)
        self.assertIsNotNone(result)
        self.assertEqual(result.action_id, "read_screen")

    def test_code_review_request(self):
        result = self.router.route("Can you debug my code?", self.actions)
        self.assertIsNotNone(result)
        self.assertEqual(result.action_id, "check_code")

    def test_unknown_question_abstains(self):
        result = self.router.route("Tell me an interesting fact about Saturn", self.actions)
        self.assertIsNone(result)

    def test_single_generic_noun_does_not_trigger(self):
        result = self.router.route("folder", self.actions)
        self.assertIsNone(result)

    def test_single_generic_noun_does_not_call_semantic_matcher(self):
        class SpySemanticMatcher:
            called = False

            def match(self, query, actions):
                self.called = True
                return ("create_folder", 0.99, ())

        matcher = SpySemanticMatcher()
        router = OfflineActionRouter(semantic_matcher=matcher)
        self.assertIsNone(router.route("folder", self.actions))
        self.assertFalse(matcher.called)


    def test_no_semantic_dependency_is_imported_implicitly(self):
        import builtins
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "assistant.local_semantic":
                raise AssertionError("offline routing must not auto-load/download embeddings")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=guarded_import):
            result = OfflineActionRouter().route(
                "prepare a new workspace container",
                self.actions,
            )
        self.assertIsNone(result)

    def test_semantic_fallback_handles_unfamiliar_wording(self):
        class FakeSemanticMatcher:
            def match(self, query, actions):
                self.query = query
                return ("create_folder", 0.81, ())
        matcher = FakeSemanticMatcher()
        router = OfflineActionRouter(semantic_matcher=matcher)
        result = router.route("prepare a new workspace container", self.actions)
        self.assertIsNotNone(result)
        self.assertEqual(result.action_id, "create_folder")
        self.assertEqual(matcher.query, "prepare a new workspace container")

    def test_semantic_fallback_can_abstain(self):
        class FakeSemanticMatcher:
            def match(self, query, actions):
                return None
        router = OfflineActionRouter(semantic_matcher=FakeSemanticMatcher())
        result = router.route("tell me a story about Saturn", self.actions)
        self.assertIsNone(result)

    def test_argument_extractor_supports_followup_context(self):
        router = OfflineActionRouter()
        combined = "create a folder on desktop called Science Project"
        self.assertEqual(
            router.extract_arguments(combined, "create_folder"),
            "~/Desktop/Science Project",
        )

    def test_input_order_does_not_change_clear_winner(self):
        query = "read the text visible on my screen"
        forward = self.router.route(query, self.actions)
        backward = self.router.route(query, list(reversed(self.actions)))
        self.assertEqual(forward.action_id, "read_screen")
        self.assertEqual(backward.action_id, "read_screen")


if __name__ == "__main__":
    unittest.main()
