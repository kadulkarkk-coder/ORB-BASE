"""
WEBSTER / JARVIS G4 — Assistant Manager

Responsibilities
----------------
- Coordinate AI responses, commands, speech input and TTS.
- Manage assistant states and conversation history.
- Run blocking operations in QThreadPool workers.
- Support continuous listening.
- Support barge-in (interrupt TTS and return to listening).
- Handle command confirmations.
- Provide UI signals without directly manipulating widgets.

This module does NOT implement the G5 Actions system.
"""

from __future__ import annotations

import logging
import threading

from collections import deque
from enum import Enum
from typing import Callable, Optional, Any

from PySide6.QtCore import (
    QObject,
    QRunnable,
    QThreadPool,
    Signal,
    Slot,
    QTimer,
)

from assistant.ai_engine import AIResult, Turn, create_engine
from assistant.commands import CommandRouter, CommandResult
from assistant.speech import SpeechEngine
from memory import Smriti, SmritiError 

logger = logging.getLogger(__name__)


# =====================================================================
# ASSISTANT STATE
# =====================================================================

class AssistantState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    SLEEPING = "sleeping"
    ERROR = "error"


# =====================================================================
# BACKGROUND TASK SIGNALS
# =====================================================================

class _TaskSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


# =====================================================================
# BACKGROUND TASK
# =====================================================================

class _Task(QRunnable):
    """
    Executes a function in QThreadPool and reports its result.

    The separate QObject holds the signals because QRunnable itself
    is not a QObject.
    """

    def __init__(
        self,
        function: Callable,
        *args,
        **kwargs,
    ):
        super().__init__()

        self.function = function
        self.args = args
        self.kwargs = kwargs

        self.signals = _TaskSignals()

    @Slot()
    def run(self):
        try:
            result = self.function(
                *self.args,
                **self.kwargs,
            )

            self.signals.finished.emit(result)

        except Exception as exc:
            logger.exception(
                "Background task failed: %s",
                getattr(self.function, "__name__", "unknown task"),
            )

            self.signals.failed.emit(str(exc))


# =====================================================================
# ASSISTANT MANAGER
# =====================================================================

class AssistantManager(QObject):

    # -------------------------------------------------------------
    # UI SIGNALS — preserved for existing UI compatibility
    # -------------------------------------------------------------

    state_changed = Signal(str)

    message = Signal(str, str)

    log = Signal(str)

    error = Signal(str)

    level_changed = Signal(float)

    listening_changed = Signal(bool)

    ui_action = Signal(str)

    voice_mode_changed = Signal(bool)

    barge_in_detected = Signal()



    # -------------------------------------------------------------
    # INITIALIZATION
    # -------------------------------------------------------------

    def __init__(
        self,
        parent=None,
        stats_provider: Optional[Callable] = None,
    ):
        super().__init__(parent)

        # Thread pool
        self.pool = QThreadPool.globalInstance()

        # Core systems
        self.ai = create_engine()

        self.speech = SpeechEngine()

        self.router = CommandRouter(
            stats_provider=stats_provider,
        )

        # Assistant state
        self.state = AssistantState.IDLE

        self.history = deque(maxlen=24)

        # Runtime settings
        self.tts_enabled = True
        self.continuous = False

        self.sleeping = False
        self.busy = False
        self.shutting_down = False

        # Task references
        self._task = None
        self._listen_task = None
        self._speak_task = None

        # Command confirmation
        self._pending_command: Optional[CommandResult] = None

        # Conversation tracking
        self._last_prompt = ""

        # Synchronization
        self._lock = threading.RLock()

        # Persistent memory — independent of short-term conversation history.
        try:
            self.memory = Smriti()
            logger.info("Smriti memory initialized.")
            self.log.emit("Smriti memory online.")
        except (SmritiError, OSError):
            self.memory = None
            logger.exception("Smriti could not be initialized.")
            self.log.emit("Smriti is unavailable. Conversation history still works.")

        # Listening state
        self._listen_cancelled = False

        # Barge-in synchronization.
        # This Event is set directly by the speech worker callback,
        # before the Qt signal is delivered to the UI thread.
        self._barge_requested = threading.Event()

        self.barge_in_detected.connect(
            self._on_barge_in_detected
        )

        self.log.emit("Assistant manager initialized.")

    # =================================================================
    # STATE MANAGEMENT
    # =================================================================

    def _set_state(self, state: AssistantState):
        if not isinstance(state, AssistantState):
            state = AssistantState(state)

        if self.shutting_down and state not in {
            AssistantState.SLEEPING,
        }:
            return

        self.state = state

        self.state_changed.emit(state.value)

    # =================================================================
    # GREETING
    # =================================================================

    def greet(self):
        if self.shutting_down:
            return

        self.log.emit("Assistant initialized.")

        self.message.emit(
            "assistant",
            "Systems online. Ready to assist.",
        )

        # =================================================================
    # SMRITI — PERSISTENT MEMORY INTERFACE
    # =================================================================

    def _require_memory(self) -> Smriti:
        """Return the memory engine or raise a controlled error."""
        if self.memory is None:
            raise SmritiError(
                "Smriti is unavailable. Check the memory database."
            )
        return self.memory

    def save_memory(
        self,
        key: str,
        value: str,
        category: str = "general",
    ) -> int:
        """Explicitly save or update a persistent memory."""
        return self._require_memory().save(key, value, category)

    def get_memory(self, key: str) -> dict[str, Any] | None:
        """Retrieve one saved memory by its key."""
        return self._require_memory().get(key)

    def search_memories(
        self,
        query: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search saved memories."""
        return self._require_memory().search(query, limit)

    def list_memories(
        self,
        category: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List saved memories, optionally filtered by category."""
        return self._require_memory().list_memories(category, limit)

    def delete_memory(self, key: str) -> bool:
        """Delete one saved memory."""
        return self._require_memory().delete(key)

    def clear_memories(self, category: str | None = None) -> int:
        """Clear all memories or memories in one category."""
        return self._require_memory().clear(category)

    def memory_count(self) -> int:
        """Return the number of saved memories."""
        return self._require_memory().count()

    # =================================================================
    # TEXT INPUT
    # =================================================================

    def submit_text(self, text: str):
        text = (text or "").strip()

        if not text or self.shutting_down:
            return

        if self.sleeping:
            self.message.emit(
                "assistant",
                "I'm sleeping. Wake me first.",
            )
            return

        # Handle cancellation of a pending confirmation.
        if text.lower() in {
            "cancel",
            "never mind",
            "nevermind",
        }:
            if self._pending_command is not None:
                self._pending_command = None

                self.message.emit(
                    "assistant",
                    "Action cancelled.",
                )

                self._set_state(AssistantState.IDLE)
                return

        # Confirmation responses must not be treated as new AI prompts.
        if self._pending_command is not None:
            self._handle_confirmation(text)
            return

        # Avoid overlapping AI requests.
        if self.busy:
            self.log.emit(
                "A response is already being processed."
            )
            return

        # If a listening task is active, cancel its capture.
        if self._listen_task is not None:
            self._cancel_active_listening()

        # Stop current TTS without permanently cancelling future input.
        self._interrupt_speech()

        self.message.emit("user", text)

        self._last_prompt = text

        self._process_text(text)

    # =================================================================
    # AI PROCESSING
    # =================================================================

    def _process_text(self, text: str):
        if self.shutting_down:
            return

        if self.busy:
            self.log.emit("Assistant is busy.")
            return

        self.busy = True

        self._set_state(AssistantState.PROCESSING)

        task = _Task(
            self._respond,
            text,
        )

        task.signals.finished.connect(
            self._on_response_ready
        )

        task.signals.failed.connect(
            self._on_response_failed
        )

        self._task = task

        self.pool.start(task)

    def _respond(self, text: str) -> dict[str, Any]:
        """
        Runs outside the UI thread.

        First checks local commands, then sends unhandled prompts
        to the selected AI provider.
        """

        command = self.router.route(text)

        if command.handled:
            return {
                "kind": "command",
                "result": command,
            }

        with self._lock:
            conversation_context = list(self.history)

        result = self.ai.process(
            text,
            conversation_context,
        )

        if not isinstance(result, AIResult):
            return {
                "kind": "error",
                "text": "The AI provider returned an invalid response.",
            }

        if not result.ok:
            return {
                "kind": "error",
                "text": result.error or "The AI request failed.",
            }

        return {
            "kind": "ai",
            "text": result.text,
            "engine": result.engine,
        }

    # =================================================================
    # AI RESPONSE
    # =================================================================

    @Slot(object)
    def _on_response_ready(self, response):
        self.busy = False
        self._task = None

        if self.shutting_down:
            return

        if not isinstance(response, dict):
            self._on_response_failed(
                "Invalid response received."
            )
            return

        kind = response.get("kind")

        # ---------------------------------------------------------
        # Command response
        # ---------------------------------------------------------

        if kind == "command":
            self._handle_command_result(
                response.get("result")
            )
            return

        # ---------------------------------------------------------
        # AI error
        # ---------------------------------------------------------

        if kind == "error":
            text = response.get(
                "text",
                "An error occurred.",
            )

            self.message.emit("assistant", text)
            self.error.emit(text)

            self._set_state(AssistantState.ERROR)
            return

        # ---------------------------------------------------------
        # AI response
        # ---------------------------------------------------------

        if kind != "ai":
            self._on_response_failed(
                "Unknown response type."
            )
            return

        text = str(
            response.get("text", "")
        ).strip()

        engine = str(
            response.get("engine", "AI")
        )

        if not text:
            text = "I couldn't generate a response."

        # Save short-term conversation history safely.
        with self._lock:
            self.history.append(
                Turn("user", self._last_prompt)
            )

            self.history.append(
                Turn("assistant", text)
            )

        self.message.emit(
            "assistant",
            text,
        )

        self.log.emit(
            f"Response generated by {engine}."
        )

        if self.tts_enabled:
            self._speak(text)
        else:
            self._set_state(AssistantState.IDLE)

            if self.continuous:
                QTimer.singleShot(
                    250,
                    self.start_listening,
                )

    # =================================================================
    # COMMAND HANDLING
    # =================================================================

    def _handle_command_result(
        self,
        result: Optional[CommandResult],
    ):
        if self.shutting_down:
            return

        if result is None or not result.handled:
            self._set_state(AssistantState.IDLE)
            return

        # Commands requiring approval are never executed immediately.
        if result.requires_confirmation:
            self._pending_command = result

            self.message.emit(
                "assistant",
                result.text
                + "\n\nReply YES to confirm or NO to cancel.",
            )

            self._set_state(AssistantState.IDLE)
            return

        self._finish_command(result)

    def _handle_confirmation(self, answer: str):
        answer = (answer or "").strip().lower()

        positive = {
            "yes",
            "y",
            "confirm",
            "approved",
        }

        negative = {
            "no",
            "n",
            "cancel",
        }

        if answer not in positive | negative:
            self.message.emit(
                "assistant",
                "Please reply YES to confirm or NO to cancel.",
            )
            return

        command = self._pending_command

        self._pending_command = None

        if answer in negative:
            self.message.emit(
                "assistant",
                "Action cancelled.",
            )

            self._set_state(AssistantState.IDLE)
            return

        if command is not None:
            self._finish_command(command)

    def _finish_command(self, result: CommandResult):
        if self.shutting_down:
            return

        output = result.text or ""

        if result.action is not None:
            try:
                action_output = result.action()

                if action_output:
                    output = str(action_output)

            except Exception as exc:
                logger.exception("Command action failed.")

                output = f"Command failed: {exc}"

                self.error.emit(output)

        if output:
            self.message.emit(
                "assistant",
                output,
            )

        if result.ui_action:
            self.ui_action.emit(
                result.ui_action
            )

        if result.speak and self.tts_enabled and output:
            self._speak(output)
        else:
            self._set_state(AssistantState.IDLE)

            if self.continuous:
                QTimer.singleShot(
                    250,
                    self.start_listening,
                )

    # =================================================================
    # AI TASK FAILURE
    # =================================================================

    @Slot(str)
    def _on_response_failed(self, error_text: str):
        self.busy = False
        self._task = None

        if self.shutting_down:
            return

        logger.error(
            "AI response task failed: %s",
            error_text,
        )

        self.error.emit(error_text)

        self.message.emit(
            "assistant",
            f"Something went wrong: {error_text}",
        )

        self._set_state(AssistantState.ERROR)

    # =================================================================
    # SPEECH OUTPUT
    # =================================================================

    def _speak(self, text: str):
        if self.shutting_down:
            return

        if not self.tts_enabled:
            self._set_state(AssistantState.IDLE)
            return

        if not text or not text.strip():
            self._set_state(AssistantState.IDLE)
            return

        # Stop any previous playback before starting another response.
        self._interrupt_speech()

        self._barge_requested.clear()

        self._set_state(AssistantState.SPEAKING)

        task = _Task(
            self.speech.speak,
            text,
            None,
            self._notify_barge_in,
        )

        task.signals.finished.connect(
            self._on_speech_finished
        )

        task.signals.failed.connect(
            self._on_speech_failed
        )

        self._speak_task = task

        self.pool.start(task)

    def _notify_barge_in(self):
        """
        Called from the speech worker's monitor thread.

        Set the threading Event immediately, then notify the Qt thread.
        This avoids relying on the timing of queued Qt signal delivery.
        """

        if self.shutting_down:
            return

        self._barge_requested.set()

        self.barge_in_detected.emit()

    @Slot()
    def _on_barge_in_detected(self):
        if self.shutting_down:
            return

        self.log.emit(
            "Barge-in detected. Preparing to listen."
        )

    @Slot(object)
    def _on_speech_finished(self, _result=None):
        self._speak_task = None

        if self.shutting_down:
            return

        # Barge-in takes priority over normal continuous-mode handling.
        if self._barge_requested.is_set():
            self._barge_requested.clear()

            self.log.emit(
                "Speech interrupted. Listening for your command."
            )

            QTimer.singleShot(
                250,
                self._resume_after_barge_in,
            )
            return

        self._set_state(AssistantState.IDLE)

        if self.continuous and not self.sleeping:
            QTimer.singleShot(
                250,
                self.start_listening,
            )

    def _resume_after_barge_in(self):
        if self.shutting_down or self.sleeping:
            return

        if self.busy or self._listen_task is not None:
            return

        self.start_listening()

    @Slot(str)
    def _on_speech_failed(self, error_text: str):
        self._speak_task = None

        if self.shutting_down:
            return

        logger.error(
            "Speech output failed: %s",
            error_text,
        )

        self.error.emit(
            f"Speech output failed: {error_text}"
        )

        if self._barge_requested.is_set():
            self._barge_requested.clear()

            QTimer.singleShot(
                250,
                self._resume_after_barge_in,
            )
            return

        self._set_state(AssistantState.IDLE)

        if self.continuous and not self.sleeping:
            QTimer.singleShot(
                250,
                self.start_listening,
            )

    def _interrupt_speech(self):
        try:
            self.speech.stop_speaking()

        except Exception:
            logger.exception(
                "Could not interrupt speech."
            )

    # =================================================================
    # SPEECH INPUT
    # =================================================================

    def start_listening(self):
        if self.shutting_down:
            return

        if self.sleeping:
            return

        if self.busy:
            return

        if self._listen_task is not None:
            return

        if self._speak_task is not None:
            return

        # Reset the previous listening cancellation before starting
        # a fresh microphone capture.
        prepare = getattr(
            self.speech,
            "prepare_listen",
            None,
        )

        if callable(prepare):
            prepare()

        self._listen_cancelled = False

        self._set_state(
            AssistantState.LISTENING
        )

        self.listening_changed.emit(True)

        task = _Task(
            self.speech.listen
        )

        task.signals.finished.connect(
            self._on_listen_finished
        )

        task.signals.failed.connect(
            self._on_listen_failed
        )

        self._listen_task = task

        self.pool.start(task)

    @Slot(object)
    def _on_listen_finished(self, result):
        self._listen_task = None

        self.listening_changed.emit(False)

        if self.shutting_down:
            return

        if self.sleeping:
            return

        if self._listen_cancelled:
            self._listen_cancelled = False
            self._set_state(AssistantState.IDLE)
            return

        text = getattr(
            result,
            "text",
            "",
        ) if result else ""

        text = (text or "").strip()

        if text:
            self.submit_text(text)
            return

        listen_error = getattr(
            result,
            "error",
            "",
        ) if result else ""

        if listen_error:
            self.log.emit(
                f"Listening: {listen_error}"
            )

        self._set_state(
            AssistantState.IDLE
        )

        if self.continuous:
            QTimer.singleShot(
                300,
                self.start_listening,
            )

    @Slot(str)
    def _on_listen_failed(self, error_text: str):
        self._listen_task = None

        self.listening_changed.emit(False)

        if self.shutting_down or self.sleeping:
            return

        if self._listen_cancelled:
            self._listen_cancelled = False
            self._set_state(AssistantState.IDLE)
            return

        logger.error(
            "Listening task failed: %s",
            error_text,
        )

        self.error.emit(
            f"Listening failed: {error_text}"
        )

        self._set_state(
            AssistantState.ERROR
        )

        if self.continuous:
            QTimer.singleShot(
                700,
                self.start_listening,
            )

    def _begin_listening(self):
        self.start_listening()

    def _cancel_active_listening(self):
        if self._listen_task is None:
            return

        self._listen_cancelled = True

        try:
            self.speech.cancel()

        except Exception:
            logger.exception(
                "Could not cancel microphone capture."
            )

        self.listening_changed.emit(False)

    def cancel_listening(self):
        if self._listen_task is None:
            return

        self._cancel_active_listening()

        self._set_state(
            AssistantState.IDLE
        )

    # =================================================================
    # CONTINUOUS VOICE MODE
    # =================================================================

    def set_continuous(self, enabled: bool):
        if self.shutting_down:
            return

        enabled = bool(enabled)

        self.continuous = enabled

        self.voice_mode_changed.emit(
            self.continuous
        )

        if self.sleeping:
            return

        if self.continuous:
            self.log.emit(
                "Continuous voice mode enabled."
            )

            if (
                not self.busy
                and self._speak_task is None
                and self._listen_task is None
            ):
                QTimer.singleShot(
                    100,
                    self.start_listening,
                )

        else:
            self.log.emit(
                "Continuous voice mode disabled."
            )

            if self._listen_task is not None:
                self._cancel_active_listening()

    def toggle_voice(self):
        self.set_continuous(
            not self.continuous
        )

    # =================================================================
    # SLEEP / WAKE
    # =================================================================

    def sleep(self):
        if self.shutting_down or self.sleeping:
            return

        self.sleeping = True
        self.continuous = False

        self._pending_command = None

        self.voice_mode_changed.emit(False)

        if self._listen_task is not None:
            self._cancel_active_listening()

        self._interrupt_speech()

        self._stop_wake_listener()

        self.listening_changed.emit(False)

        self._set_state(
            AssistantState.SLEEPING
        )

        self.message.emit(
            "assistant",
            "Going to sleep.",
        )

        self._start_wake_listener()

    def _start_wake_listener(self):
        """
        Compatibility adapter.

        The current SpeechEngine does not implement wake-word detection.
        If a future or external speech adapter provides these methods,
        this manager can use them without changing its public API.
        """

        starter = getattr(
            self.speech,
            "start_wake_listener",
            None,
        )

        if callable(starter):
            try:
                starter(
                    self._on_wake_word,
                    self._on_wake_error,
                )

            except Exception as exc:
                self._on_wake_error(str(exc))

        else:
            self.log.emit(
                "Wake-word adapter is not available."
            )

    def _on_wake_word(self):
        if self.shutting_down:
            return

        self.sleeping = False

        self._stop_wake_listener()

        self._set_state(
            AssistantState.IDLE
        )

        self.message.emit(
            "assistant",
            "I'm awake.",
        )

        self.start_listening()

    def _on_wake_error(self, error_text: str):
        self.error.emit(
            f"Wake-word error: {error_text}"
        )

    def _stop_wake_listener(self):
        stopper = getattr(
            self.speech,
            "stop_wake_listener",
            None,
        )

        if callable(stopper):
            try:
                stopper()

            except Exception:
                logger.exception(
                    "Could not stop wake listener."
                )

    # =================================================================
    # TTS SETTINGS
    # =================================================================

    def set_tts_enabled(self, enabled: bool):
        self.tts_enabled = bool(enabled)

        if not self.tts_enabled:
            self._interrupt_speech()

            if not self.busy and self._listen_task is None:
                self._set_state(AssistantState.IDLE)

    # =================================================================
    # GENERAL TASK FAILURE
    # =================================================================

    @Slot(str)
    def _on_task_failed(self, error_text: str):
        """
        Backwards-compatible generic failure handler.
        Individual task types use their own handlers above.
        """

        if self.shutting_down:
            return

        self.error.emit(error_text)

        self.message.emit(
            "assistant",
            f"Something went wrong: {error_text}",
        )

        self._set_state(
            AssistantState.ERROR
        )

    # =================================================================
    # SHUTDOWN
    # =================================================================

    def shutdown(self):
        if self.shutting_down:
            return

        self.shutting_down = True

        self.continuous = False
        self.sleeping = True
        self.busy = False

        self._pending_command = None

        self._barge_requested.clear()

        self._stop_wake_listener()

        try:
            self.speech.cancel()

        except Exception:
            logger.exception(
                "Speech cancellation during shutdown failed."
            )

        self._interrupt_speech()

        self.listening_changed.emit(False)

        self._set_state(
            AssistantState.SLEEPING
        )

        self.log.emit(
            "Assistant manager shut down."
        )