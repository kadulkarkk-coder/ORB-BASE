
"""WEBSTER G3 speech input/output.

Normal speech transcription uses SpeechRecognition + Google.
Sleep-mode wake detection is handled separately by wake_word.py.

TTS backends remain optional:
1. ElevenLabs, when configured
2. macOS rendered speech
3. Native OS speech
4. pyttsx3 fallback

All blocking operations must run in worker threads.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import config

try:
    import numpy as np
except ImportError:
    np = None

try:
    import sounddevice as sd
except Exception:
    sd = None

try:
    import speech_recognition as sr
except ImportError:
    sr = None


LevelCallback = Callable[[float], None]
BargeInCallback = Callable[[], None]


def speech_envelope(t: float) -> float:
    syllable = 0.50 + 0.50 * math.sin(math.tau * 4.5 * t)
    phrase = 0.72 + 0.28 * math.sin(math.tau * 1.3 * t + 1.0)
    detail = 0.86 + 0.14 * math.sin(math.tau * 7.7 * t + 2.0)
    breath = 1.0 if math.sin(math.tau * 0.55 * t) > -0.65 else 0.22
    return max(0.05, min(1.0, syllable * phrase * detail * breath + 0.12))


@dataclass
class ListenResult:
    text: str = ""
    error: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.text) and self.error is None


class SpeechEngine:
    """Microphone capture, transcription and speech output."""

    def __init__(self) -> None:
        self._abort = threading.Event()
        self._tts_process: subprocess.Popen | None = None
        self._tts_lock = threading.RLock()

        self._barge_stop = threading.Event()
        self._barge_thread: threading.Thread | None = None
        self._barge_triggered = threading.Event()

        self._listen_lock = threading.Lock()

    # --------------------------------------------------------------
    # CAPABILITY
    # --------------------------------------------------------------

    @property
    def input_available(self) -> bool:
        if sd is None or np is None:
            return False
        try:
            return any(
                device["max_input_channels"] >= 1
                for device in sd.query_devices()
            )
        except Exception:
            return False

    @property
    def recognizer_available(self) -> bool:
        return sr is not None

    @property
    def playback_is_buffered(self) -> bool:
        if sd is None or np is None:
            return False
        if config.ELEVENLABS_API_KEY and config.ELEVENLABS_VOICE_ID:
            return True
        return sys.platform == "darwin" and shutil.which("say") is not None

    def unavailable_reason(self) -> str | None:
        if np is None:
            return "numpy is not installed."
        if sd is None:
            return "sounddevice is unavailable. Check PortAudio."
        if not self.input_available:
            return "No microphone was detected."
        if sr is None:
            return "SpeechRecognition is not installed."
        return None

    # --------------------------------------------------------------
    # MICROPHONE
    # --------------------------------------------------------------

    def cancel(self) -> None:
        """Cancel the current recording."""
        self._abort.set()

    def _resolve_device(self):
        spec = config.MIC_DEVICE
        if not spec:
            return None

        if spec.isdigit():
            return int(spec)

        needle = spec.lower()

        try:
            for index, device in enumerate(sd.query_devices()):
                if (
                    device["max_input_channels"] >= 1
                    and needle in device["name"].lower()
                ):
                    return index
        except Exception:
            pass

        return None

    def listen(self, on_level: LevelCallback | None = None) -> ListenResult:
        """Record one utterance and transcribe it."""
        reason = self.unavailable_reason()
        if reason:
            return ListenResult(error=reason)

        # Reset before recording starts, not after the worker has begun.
        self._abort.clear()

        rate = config.LISTEN_SAMPLE_RATE
        block = int(rate * 0.05)
        max_blocks = int(config.LISTEN_MAX_SECONDS / 0.05)
        silence_needed = max(
            1,
            int(config.LISTEN_SILENCE_SECONDS / 0.05),
        )

        frames: list[bytes] = []
        noise_floor = 0.0
        speech_started = False
        silent_run = 0

        try:
            with sd.InputStream(
                device=self._resolve_device(),
                samplerate=rate,
                channels=1,
                dtype="int16",
                blocksize=block,
            ) as stream:
                for index in range(max_blocks):
                    if self._abort.is_set():
                        break

                    data, _ = stream.read(block)
                    raw = bytes(data)
                    frames.append(raw)

                    samples = np.frombuffer(
                        raw, dtype="<i2"
                    ).astype(np.float32)

                    level = (
                        float(np.sqrt(np.mean(samples ** 2))) / 32768.0
                        if samples.size else 0.0
                    )

                    if on_level:
                        on_level(min(1.0, level * 12.0))

                    if index < 6:
                        noise_floor = max(noise_floor, level)
                        continue

                    threshold = max(noise_floor * 2.5, 0.012)

                    if level >= threshold:
                        speech_started = True
                        silent_run = 0
                    elif speech_started:
                        silent_run += 1
                        if silent_run >= silence_needed:
                            break

        except Exception as exc:
            return ListenResult(error=f"Microphone error: {exc}")

        finally:
            if on_level:
                on_level(0.0)

        if self._abort.is_set():
            return ListenResult(error="Listening cancelled.")

        if not speech_started:
            return ListenResult(error="No speech detected.")

        return self._transcribe(b"".join(frames), rate)

    def _transcribe(self, pcm: bytes, rate: int) -> ListenResult:
        if not pcm:
            return ListenResult(error="Nothing was recorded.")

        try:
            recognizer = sr.Recognizer()
            audio = sr.AudioData(pcm, rate, 2)
            text = recognizer.recognize_google(audio)

        except sr.UnknownValueError:
            return ListenResult(error="Speech was not intelligible.")
        except sr.RequestError as exc:
            return ListenResult(error=f"Speech service unreachable: {exc}")
        except Exception as exc:
            return ListenResult(error=f"Recognition failed: {exc}")

        text = (text or "").strip()

        if not text:
            return ListenResult(error="Speech was not intelligible.")

        return ListenResult(text=text)

    # --------------------------------------------------------------
    # AUTOMATIC BARGE-IN MONITOR
    # --------------------------------------------------------------

    def _start_barge_monitor(
        self,
        callback: BargeInCallback | None,
    ) -> None:
        """Watch microphone levels while TTS is playing.

        This is intentionally a level-based trigger, not transcription.
        It does not send audio anywhere.
        """
        if callback is None or sd is None or np is None:
            return

        self._barge_stop.clear()
        self._barge_triggered.clear()

        def monitor():
            rate = 16000
            block = 800
            consecutive = 0
            started = time.monotonic()

            try:
                with sd.InputStream(
                    device=self._resolve_device(),
                    samplerate=rate,
                    channels=1,
                    dtype="int16",
                    blocksize=block,
                ) as stream:
                    while not self._barge_stop.is_set():
                        data, _ = stream.read(block)
                        samples = np.frombuffer(
                            bytes(data), dtype="<i2"
                        ).astype(np.float32)

                        if samples.size == 0:
                            continue

                        rms = float(
                            np.sqrt(np.mean(samples ** 2))
                        ) / 32768.0

                        # Ignore the first 350 ms to avoid triggering
                        # on the initial TTS audio/device transient.
                        if time.monotonic() - started < 0.35:
                            continue

                        # Require sustained voice-level input.
                        # This reduces false triggers from brief clicks.
                        if rms > 0.045:
                            consecutive += 1
                        else:
                            consecutive = max(0, consecutive - 2)

                        if consecutive >= 5:
                            if not self._barge_triggered.is_set():
                                self._barge_triggered.set()
                                callback()
                            break

            except Exception:
                # Some audio drivers cannot open input while output
                # is active. In that case manual interruption remains
                # available through the UI.
                return

        self._barge_thread = threading.Thread(
            target=monitor,
            name="WEBSTER-BargeIn",
            daemon=True,
        )
        self._barge_thread.start()

    def _stop_barge_monitor(self) -> None:
        self._barge_stop.set()

        thread = self._barge_thread
        self._barge_thread = None

        if thread and thread.is_alive():
            thread.join(timeout=0.4)

    # --------------------------------------------------------------
    # SPEECH OUTPUT
    # --------------------------------------------------------------

    def speak(
        self,
        text: str,
        on_level: LevelCallback | None = None,
        on_barge_in: BargeInCallback | None = None,
    ) -> bool:
        """Speak text. Must be called from a worker thread."""
        text = (text or "").strip()

        if not text or not config.TTS_ENABLED:
            return False

        self._barge_triggered.clear()
        self._start_barge_monitor(on_barge_in)

        try:
            if self._speak_elevenlabs(text, on_level):
                return True

            if self._speak_rendered(text, on_level):
                return True

            return self._speak_system(text, on_level)

        finally:
            self._stop_barge_monitor()

            if on_level:
                on_level(0.0)

    def stop_speaking(self) -> None:
        """Stop active speech playback."""
        with self._tts_lock:
            process = self._tts_process

        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

        if sd is not None:
            try:
                sd.stop()
            except Exception:
                pass

    # --------------------------------------------------------------
    # ELEVENLABS — OPTIONAL, PRESERVED
    # --------------------------------------------------------------

    def _speak_elevenlabs(
        self,
        text: str,
        on_level: LevelCallback | None = None,
    ) -> bool:
        if not (
            config.ELEVENLABS_API_KEY
            and config.ELEVENLABS_VOICE_ID
        ):
            return False

        if np is None or sd is None:
            return False

        try:
            from elevenlabs.client import ElevenLabs
        except ImportError:
            return False

        try:
            client = ElevenLabs(
                api_key=config.ELEVENLABS_API_KEY
            )

            raw = b"".join(
                client.text_to_speech.convert(
                    voice_id=config.ELEVENLABS_VOICE_ID,
                    text=text,
                    model_id=config.ELEVENLABS_MODEL_ID,
                    output_format="pcm_24000",
                )
            )
        except Exception:
            return False

        if not raw or len(raw) < 2:
            return False

        try:
            if len(raw) % 2:
                raw = raw[:-1]

            samples = (
                np.frombuffer(raw, dtype="<i2").astype(np.float32)
                / 32768.0
            )

            sd.play(samples, 24000)

            if on_level:
                self._report_playback_level(
                    samples, 24000, on_level
                )

            sd.wait()

        except Exception:
            return False

        return not self._barge_triggered.is_set()

    # --------------------------------------------------------------
    # MACOS RENDERED SPEECH
    # --------------------------------------------------------------

    def _speak_rendered(
        self,
        text: str,
        on_level: LevelCallback | None = None,
    ) -> bool:
        if sys.platform != "darwin" or sd is None or np is None:
            return False

        say = shutil.which("say")
        if not say:
            return False

        path = (
            Path(tempfile.gettempdir())
            / f"jarvis_tts_{os.getpid()}.wav"
        )

        try:
            result = subprocess.run(
                [
                    say,
                    "-o",
                    str(path),
                    "--data-format=LEI16@22050",
                    text,
                ],
                capture_output=True,
                check=False,
            )

            if result.returncode != 0 or not path.is_file():
                return False

            with wave.open(str(path), "rb") as wf:
                if wf.getsampwidth() != 2:
                    return False

                rate = wf.getframerate()
                channels = wf.getnchannels()
                raw = wf.readframes(wf.getnframes())

        except (OSError, wave.Error, ValueError):
            return False

        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

        if len(raw) < 2:
            return False

        samples = np.frombuffer(
            raw[: len(raw) - (len(raw) % 2)],
            dtype="<i2",
        ).astype(np.float32) / 32768.0

        if channels > 1:
            samples = samples.reshape(-1, channels).mean(axis=1)

        if samples.size == 0:
            return False

        try:
            sd.play(samples, rate)

            if on_level:
                self._report_playback_level(
                    samples, rate, on_level
                )

            sd.wait()

        except Exception:
            return False

        return not self._barge_triggered.is_set()

    # --------------------------------------------------------------
    # SYSTEM VOICE
    # --------------------------------------------------------------

    def _speak_system(
        self,
        text: str,
        on_level: LevelCallback | None = None,
    ) -> bool:
        command: list[str] | None = None

        if sys.platform == "darwin" and shutil.which("say"):
            command = ["say", text]

        elif sys.platform == "win32":
            shell = (
                shutil.which("powershell.exe")
                or shutil.which("powershell")
                or shutil.which("pwsh")
            )

            if shell:
                safe = text.replace("'", "''")

                command = [
                    shell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "Add-Type -AssemblyName System.Speech; "
                    "(New-Object System.Speech.Synthesis."
                    "SpeechSynthesizer).Speak("
                    f"'{safe}')",
                ]

        else:
            for exe in ("espeak-ng", "espeak", "spd-say"):
                found = shutil.which(exe)
                if found:
                    command = [found, text]
                    break

        if command is None:
            return self._speak_pyttsx3(text)

        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(
                    subprocess, "CREATE_NO_WINDOW", 0
                ),
            )
        except OSError:
            return self._speak_pyttsx3(text)

        with self._tts_lock:
            self._tts_process = process

        try:
            if on_level is None:
                while process.poll() is None:
                    if self._barge_triggered.is_set():
                        process.terminate()
                        break
                    time.sleep(0.04)

            else:
                started = time.monotonic()

                while process.poll() is None:
                    if self._barge_triggered.is_set():
                        process.terminate()
                        break

                    on_level(
                        speech_envelope(
                            time.monotonic() - started
                        )
                    )

                    time.sleep(0.04)

        finally:
            with self._tts_lock:
                self._tts_process = None

        return (
            process.returncode == 0
            and not self._barge_triggered.is_set()
        )

    @staticmethod
    def _speak_pyttsx3(text: str) -> bool:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
            return True
        except Exception:
            return False

    # --------------------------------------------------------------
    # PLAYBACK LEVEL
    # --------------------------------------------------------------

    def _report_playback_level(
        self,
        samples,
        rate: int,
        on_level: LevelCallback,
    ) -> None:
        total = len(samples) / float(rate)
        window = max(1, rate // 25)
        started = time.monotonic()

        while True:
            if self._barge_triggered.is_set():
                break

            elapsed = time.monotonic() - started

            if elapsed >= total:
                break

            index = int(elapsed * rate)
            chunk = samples[index:index + window]

            if chunk.size:
                rms = float(
                    np.sqrt(
                        np.mean(chunk.astype(np.float32) ** 2)
                    )
                )
                on_level(min(1.0, rms * 4.5))

            time.sleep(0.04)
