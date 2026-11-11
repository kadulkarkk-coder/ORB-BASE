"""Optional, fully local Llama.cpp backend for GGUF instruction models.

This module never downloads model weights and never contacts a remote service.
If the Python runtime or model file is missing, the provider factory selects
WEBSTER's deterministic OfflineEngine instead.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

import config
from assistant.ai_engine import AIEngine, AIResult, OfflineEngine, Turn

logger = logging.getLogger(__name__)


class LlamaCppEngine(AIEngine):
    """CPU-first Llama 3.2 3B Instruct engine using llama-cpp-python."""

    name = "llama"

    def __init__(self) -> None:
        raw_model_path = Path(config.AI.local_model_path).expanduser()
        self.model_path = (
            raw_model_path if raw_model_path.is_absolute()
            else config.BASE_DIR / raw_model_path
        )
        self._llama = None
        self._offline: OfflineEngine | None = None
        self._load_error: str | None = None
        self._load_lock = threading.Lock()
        self._runtime = None

        try:
            from llama_cpp import Llama
            self._runtime = Llama
        except (ImportError, OSError) as exc:
            self._load_error = (
                "Local Llama runtime is unavailable. Install the optional "
                "llama-cpp-python dependency to enable the model."
            )
            logger.info("%s (%s)", self._load_error, exc)

    @property
    def unavailable_reason(self) -> str:
        if self._load_error:
            return self._load_error
        if not self.model_path.is_file():
            return (
                f"Local Llama model file was not found at '{self.model_path}'. "
                "Place the Llama 3.2 3B Instruct GGUF model there or set "
                "WEBSTER_LLAMA_MODEL in .env. Using the built-in local engine."
            )
        return "Local Llama is unavailable; using the built-in offline engine."

    @property
    def available(self) -> bool:
        return self._runtime is not None and self.model_path.is_file()

    @property
    def status(self) -> str:
        return "LOCAL" if self._offline is None else "OFFLINE"

    def _fallback(self, reason: str, prompt: str, history: list[Turn] | None) -> AIResult:
        logger.warning("Llama backend unavailable; switching to local offline mode: %s", reason)
        self._offline = OfflineEngine(reason)
        return self._offline.process(prompt, history)

    def _load(self):
        if self._llama is not None:
            return self._llama
        if self._offline is not None:
            return None
        if self._runtime is None:
            raise RuntimeError(self.unavailable_reason)
        if not self.model_path.is_file():
            raise FileNotFoundError(self.unavailable_reason)

        with self._load_lock:
            if self._llama is not None:
                return self._llama
            if self._offline is not None:
                return None
            self._llama = self._runtime(
                model_path=str(self.model_path),
                n_ctx=config.AI.local_context_size,
                n_threads=config.AI.local_threads,
                n_gpu_layers=0,
                verbose=False,
            )
        logger.info("Loaded local GGUF model: %s", self.model_path)
        return self._llama

    def process(self, prompt: str, history: list[Turn] | None = None) -> AIResult:
        prompt = (prompt or "").strip()
        if not prompt:
            return AIResult("Please enter a message.", self.name)

        if self._offline is not None:
            return self._offline.process(prompt, history)

        try:
            model = self._load()
            if model is None:
                return self._offline.process(prompt, history)
            messages = [{"role": "system", "content": config.AI.system_prompt}]
            for turn in (history or [])[-config.AI.history_limit:]:
                if turn.role in {"user", "assistant"} and turn.content.strip():
                    messages.append({"role": turn.role, "content": turn.content})
            messages.append({"role": "user", "content": prompt})

            response = model.create_chat_completion(
                messages=messages,
                temperature=0.6,
                top_p=0.9,
                max_tokens=config.AI.max_tokens,
            )
            choices = response.get("choices") or []
            text = (
                choices[0].get("message", {}).get("content", "").strip()
                if choices else ""
            )
            if not text:
                return AIResult("", self.name, ok=False, error="The local model returned no text.")
            return AIResult(text, self.name)
        except Exception as exc:
            reason = (
                f"Local Llama could not start or process this request ({type(exc).__name__}). "
                "WEBSTER has switched to its built-in offline engine."
            )
            return self._fallback(reason, prompt, history)
