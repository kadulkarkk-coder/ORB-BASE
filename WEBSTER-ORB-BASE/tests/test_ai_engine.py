"""Tests for the Buddhi AI provider selection and Gemini adapter."""

import sys
import types
import unittest
from unittest.mock import patch

import config
from assistant.ai_engine import (
    ClaudeEngine, GeminiEngine, OfflineEngine, OllamaEngine, Turn, create_engine,
)


class TestGeminiEngine(unittest.TestCase):
    def setUp(self):
        self.key_patch = patch("config.gemini_api_key", return_value="test-key")
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)

    def test_missing_key_returns_controlled_error(self):
        with patch("config.gemini_api_key", return_value=""):
            result = GeminiEngine().process("Hello")

        self.assertFalse(result.ok)
        self.assertIn("GEMINI_API_KEY", result.error)

    def test_successful_response_and_history_conversion(self):
        captured = {}

        class Part:
            def __init__(self, text):
                self.text = text

        class Content:
            def __init__(self, role, parts):
                self.role = role
                self.parts = parts

        class GenerateContentConfig:
            def __init__(self, **kwargs):
                self.values = kwargs

        class FakeModels:
            def generate_content(self, **kwargs):
                captured.update(kwargs)
                return types.SimpleNamespace(text="  Gemini is online.  ")

        class FakeClient:
            def __init__(self, api_key):
                self.api_key = api_key
                self.models = FakeModels()

        genai_module = types.ModuleType("google.genai")
        genai_module.types = types.SimpleNamespace(
            Part=Part,
            Content=Content,
            GenerateContentConfig=GenerateContentConfig,
        )
        genai_module.Client = FakeClient

        google_module = types.ModuleType("google")
        google_module.__path__ = []
        google_module.genai = genai_module

        with patch.dict(
            sys.modules,
            {"google": google_module, "google.genai": genai_module},
        ):
            engine = GeminiEngine(model="test-model")
            result = engine.process(
                "Current question",
                [Turn("user", "Earlier question"), Turn("assistant", "Earlier answer")],
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.text, "Gemini is online.")
        self.assertEqual(result.engine, "gemini")
        self.assertEqual(captured["model"], "test-model")
        self.assertEqual(
            [item.role for item in captured["contents"]],
            ["user", "model", "user"],
        )
        self.assertEqual(captured["contents"][-1].parts[0].text, "Current question")

    def test_create_engine_selects_gemini_when_configured(self):
        with patch.object(config.AI, "provider", "gemini"), patch(
            "config.gemini_api_key", return_value="test-key"
        ):
            engine = create_engine()

        self.assertIsInstance(engine, GeminiEngine)

    def test_gemini_without_key_uses_offline_engine_with_reason(self):
        with patch.object(config.AI, "provider", "gemini"), patch(
            "config.gemini_api_key", return_value=""
        ):
            engine = create_engine()

        self.assertIsInstance(engine, OfflineEngine)
        self.assertIn("GEMINI_API_KEY", engine.reason)


    def test_auto_provider_falls_back_offline_without_api_keys(self):
        with patch.object(config.AI, "provider", "auto"), \
             patch("config.gemini_api_key", return_value=""), \
             patch("config.openai_api_key", return_value=""), \
             patch("config.anthropic_api_key", return_value=""):
            engine = create_engine()

        self.assertIsInstance(engine, OfflineEngine)
        self.assertNotIn("GEMINI_API_KEY", engine.reason)


    def test_empty_provider_defaults_to_offline_without_keys(self):
        with patch.object(config.AI, "provider", ""), \\
             patch("config.gemini_api_key", return_value=""), \\
             patch("config.openai_api_key", return_value=""), \\
             patch("config.anthropic_api_key", return_value=""):
            engine = create_engine()

        self.assertIsInstance(engine, OfflineEngine)

    def test_create_engine_selects_ollama(self):
        with patch.object(config.AI, "provider", "ollama"):
            engine = create_engine()

        self.assertIsInstance(engine, OllamaEngine)

    def test_create_engine_selects_claude_when_key_is_configured(self):
        with patch.object(config.AI, "provider", "claude"), patch(
            "config.anthropic_api_key", return_value="test-anthropic-key"
        ):
            engine = create_engine()

        self.assertIsInstance(engine, ClaudeEngine)

    def test_claude_without_key_uses_offline_engine(self):
        with patch.object(config.AI, "provider", "claude"), patch(
            "config.anthropic_api_key", return_value=""
        ):
            engine = create_engine()

        self.assertIsInstance(engine, OfflineEngine)
        self.assertIn("ANTHROPIC_API_KEY", engine.reason)


if __name__ == "__main__":
    unittest.main(verbosity=2)
