"""
WEBSTER / JARVIS G4 — Speech Engine

Features
--------
- Speech recognition through SpeechRecognition + sounddevice.
- Streaming ElevenLabs text-to-speech.
- Interruptible playback (barge-in).
- Windows native speech fallback.
- macOS `say` and optional pyttsx3 fallbacks.
- Thread-safe cancellation and microphone handling.

Public API preserved:
    SpeechEngine()
    input_available
    recognizer_available
    playback_is_buffered
    unavailable_reason
    prepare_listen()
    cancel()
    listen()
    speak()
    stop_speaking()
"""

from __future__ import annotations

import logging
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Optional

import config


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Optional dependencies
# ---------------------------------------------------------------------

try:
    import numpy as np
except ImportError:
    np = None

try:
    import sounddevice as sd
except ImportError:
    sd = None

try:
    import speech_recognition as sr
except ImportError:
    sr = None


# ---------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------

@dataclass
class ListenResult:
    text: str = ""
    error: str = ""
    duration: float = 0.0

    @property
    def success(self) -> bool:
        return bool(self.text.strip()) and not self.error


# ---------------------------------------------------------------------
# Speech engine
# ---------------------------------------------------------------------

class SpeechEngine:

    INPUT_RATE = 16000
    INPUT_CHANNELS = 1
    INPUT_BLOCK_SIZE = 800

    OUTPUT_RATE = 24000
    OUTPUT_CHANNELS = 1

    BARGE_THRESHOLD = 0.035
    BARGE_BLOCKS = 4
    BARGE_IGNORE_SECONDS = 0.25

    def __init__(self):
        self._abort = threading.Event()
        self._playback_stop = threading.Event()
        self._barge_stop = threading.Event()
        self._barge_triggered = threading.Event()

        self._tts_lock = threading.RLock()
        self._listen_lock = threading.Lock()
        self._output_lock = threading.RLock()

        self._tts_process: Optional[subprocess.Popen] = None
        self._output_stream = None
        self._barge_thread: Optional[threading.Thread] = None
        self._pyttsx_engine = None

        self._last_error = ""
        self._is_speaking = False

    # -----------------------------------------------------------------
    # Availability
    # -----------------------------------------------------------------

    @property
    def input_available(self) -> bool:
        return sd is not None and np is not None

    @property
    def recognizer_available(self) -> bool:
        return sr is not None

    @property
    def playback_is_buffered(self) -> bool:
        # Playback is streamed where the selected backend supports it.
        return False

    @property
    def unavailable_reason(self) -> str:
        missing = []

        if np is None:
            missing.append("numpy")

        if sd is None:
            missing.append("sounddevice")

        if sr is None:
            missing.append("SpeechRecognition")

        if missing:
            return "Missing speech dependencies: " + ", ".join(missing)

        return ""

    # -----------------------------------------------------------------
    # Cancellation
    # -----------------------------------------------------------------

    def prepare_listen(self) -> None:
        """
        Reset cancellation before starting a new listening task.

        Call this from the manager immediately before submitting listen()
        to its worker thread.
        """
        self._abort.clear()

    def cancel(self) -> None:
        self._abort.set()
        self.stop_speaking()

    # -----------------------------------------------------------------
    # Microphone selection
    # -----------------------------------------------------------------
    @staticmethod
    def _resolve_device():
        if sd is None:
            return None

        try:
            configured = getattr(config, "MIC_DEVICE", None)

            # Ignore empty strings and whitespace.
            if isinstance(configured, str):
                configured = configured.strip() or None

            if configured is not None:
                # Validate the configured device.
                info = sd.query_devices(configured, kind="input")
                return int(info["index"])

            # Use Windows' configured default input device.
            default_input = sd.default.device[0]

            if default_input is not None and int(default_input) >= 0:
                info = sd.query_devices(int(default_input), kind="input")
                return int(info["index"])

            # Last resort: find the first device with input channels.
            devices = sd.query_devices()

            for index, device in enumerate(devices):
                if device["max_input_channels"] > 0:
                    return index

            raise RuntimeError("No microphone input device was found.")

        except Exception:
            logger.exception("Could not resolve microphone device.")
            raise RuntimeError("Could not resolve microphone device.")

    # -----------------------------------------------------------------
    # Listening
    # -----------------------------------------------------------------

    def listen(
        self,
        timeout: float = 8.0,
        phrase_time_limit: float = 12.0,
        on_level: Optional[Callable[[float], None]] = None,
    ) -> ListenResult:

        if not self.input_available:
            return ListenResult(
                error=self.unavailable_reason or "Audio input is unavailable."
            )

        if not self.recognizer_available:
            return ListenResult(error="SpeechRecognition is not installed.")

        if not self._listen_lock.acquire(blocking=False):
            return ListenResult(error="The microphone is already in use.")

        started = time.monotonic()

        try:
            recognizer = sr.Recognizer()
            recognizer.dynamic_energy_threshold = True
            recognizer.pause_threshold = 0.8
            recognizer.non_speaking_duration = 0.4

            device = self._resolve_device()

            frames = []
            speech_started = False
            silence_started = None
            first_audio_time = None

            max_duration = max(1.0, float(phrase_time_limit))
            initial_timeout = max(0.5, float(timeout))

            with sd.InputStream(
                samplerate=self.INPUT_RATE,
                channels=self.INPUT_CHANNELS,
                dtype="int16",
                blocksize=self.INPUT_BLOCK_SIZE,
                device=device,
            ) as stream:

                while not self._abort.is_set():
                    block, overflowed = stream.read(self.INPUT_BLOCK_SIZE)

                    if overflowed:
                        logger.debug("Microphone input overflow.")

                    audio = np.asarray(block, dtype=np.int16).reshape(-1)
                    frames.append(audio.copy())

                    rms = float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))
                    normalized_level = min(1.0, rms / 12000.0)

                    if on_level:
                        try:
                            on_level(normalized_level)
                        except Exception:
                            logger.debug("Input-level callback failed.", exc_info=True)

                    now = time.monotonic()

                    if rms > 450:
                        if not speech_started:
                            speech_started = True
                            first_audio_time = now

                        silence_started = None

                    elif speech_started:
                        if silence_started is None:
                            silence_started = now

                    if not speech_started and now - started >= initial_timeout:
                        return ListenResult(
                            error="No speech detected.",
                            duration=now - started,
                        )

                    if speech_started and first_audio_time is not None:
                        if now - first_audio_time >= max_duration:
                            break

                    if silence_started is not None:
                        if now - silence_started >= 0.8:
                            break

            if self._abort.is_set():
                return ListenResult(
                    error="Listening cancelled.",
                    duration=time.monotonic() - started,
                )

            if not frames or not speech_started:
                return ListenResult(
                    error="No speech detected.",
                    duration=time.monotonic() - started,
                )

            audio_data = np.concatenate(frames).astype(np.int16)
            audio_bytes = audio_data.tobytes()

            audio = sr.AudioData(
                audio_bytes,
                self.INPUT_RATE,
                2,
            )

            text = self._transcribe(recognizer, audio)

            return ListenResult(
                text=text,
                error="" if text else "I couldn't recognize that speech.",
                duration=time.monotonic() - started,
            )

        except Exception as exc:
            logger.exception("Speech input failed.")
            return ListenResult(
                error=f"Microphone error: {exc}",
                duration=time.monotonic() - started,
            )

        finally:
            self._listen_lock.release()

    def _transcribe(self, recognizer, audio) -> str:
        try:
            result = recognizer.recognize_google(audio)
            return result.strip() if result else ""

        except sr.UnknownValueError:
            return ""

        except sr.RequestError as exc:
            logger.warning("Speech recognition service error: %s", exc)
            self._last_error = str(exc)
            return ""

        except Exception:
            logger.exception("Transcription failed.")
            return ""

    # -----------------------------------------------------------------
    # Barge-in monitor
    # -----------------------------------------------------------------

    def _start_barge_monitor(
        self,
        callback: Optional[Callable[[], None]],
    ) -> None:

        if callback is None or not self.input_available:
            return

        self._barge_stop.clear()
        self._barge_triggered.clear()

        def monitor():
            try:
                device = self._resolve_device()
                started_at = time.monotonic()
                consecutive_voice_blocks = 0

                with sd.InputStream(
                    samplerate=self.INPUT_RATE,
                    channels=1,
                    dtype="int16",
                    blocksize=self.INPUT_BLOCK_SIZE,
                    device=device,
                ) as stream:

                    while not self._barge_stop.is_set():
                        if self._playback_stop.is_set():
                            break

                        block, _ = stream.read(self.INPUT_BLOCK_SIZE)
                        audio = np.asarray(block, dtype=np.int16).reshape(-1)

                        if time.monotonic() - started_at < self.BARGE_IGNORE_SECONDS:
                            continue

                        rms = float(
                            np.sqrt(np.mean(audio.astype(np.float32) ** 2))
                        )

                        if rms >= self.BARGE_THRESHOLD * 32768:
                            consecutive_voice_blocks += 1
                        else:
                            consecutive_voice_blocks = max(
                                0, consecutive_voice_blocks - 1
                            )

                        if consecutive_voice_blocks >= self.BARGE_BLOCKS:
                            self._barge_triggered.set()
                            self._playback_stop.set()
                            self._interrupt_output()

                            try:
                                callback()
                            except Exception:
                                logger.exception("Barge-in callback failed.")

                            break

            except Exception:
                # Some audio drivers cannot open input and output streams
                # simultaneously. Playback should continue in that case.
                logger.debug(
                    "Barge-in microphone monitor unavailable.",
                    exc_info=True,
                )

        self._barge_thread = threading.Thread(
            target=monitor,
            name="SpeechBargeMonitor",
            daemon=True,
        )
        self._barge_thread.start()

    def _stop_barge_monitor(self) -> None:
        self._barge_stop.set()

        thread = self._barge_thread

        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.7)

        self._barge_thread = None

    # -----------------------------------------------------------------
    # Output interruption
    # -----------------------------------------------------------------

    def _interrupt_output(self) -> None:
        with self._output_lock:
            stream = self._output_stream
            self._output_stream = None

            if stream is not None:
                try:
                    stream.abort()
                except Exception:
                    try:
                        stream.close()
                    except Exception:
                        pass

            process = self._tts_process

            if process is not None and process.poll() is None:
                try:
                    process.terminate()
                except Exception:
                    logger.debug("Could not terminate speech process.")

    def stop_speaking(self) -> None:
        self._playback_stop.set()
        self._interrupt_output()

        if sd is not None:
            try:
                sd.stop()
            except Exception:
                pass

        with self._tts_lock:
            self._is_speaking = False

    # -----------------------------------------------------------------
    # Main TTS entry point
    # -----------------------------------------------------------------

    def speak(
        self,
        text: str,
        on_level: Optional[Callable[[float], None]] = None,
        on_barge_in: Optional[Callable[[], None]] = None,
    ) -> bool:

        text = str(text or "").strip()

        if not text:
            return False

        if not getattr(config, "TTS_ENABLED", True):
            return False

        with self._tts_lock:
            self._playback_stop.clear()
            self._barge_stop.clear()
            self._barge_triggered.clear()
            self._is_speaking = True

        try:
            # Preferred: stream ElevenLabs audio as it is generated.
            if self._elevenlabs_configured():
                try:
                    if self._speak_elevenlabs_stream(
                        text,
                        on_level=on_level,
                        on_barge_in=on_barge_in,
                    ):
                        return True

                except Exception:
                    if self._barge_triggered.is_set():
                        return True

                    logger.exception("ElevenLabs streaming failed.")

                # Do not speak the same sentence again if playback was
                # already interrupted or partially started.
                if self._barge_triggered.is_set():
                    return True

            if self._playback_stop.is_set():
                return False

            # Native fallback.
            if sys.platform == "darwin":
                if self._speak_rendered(text, on_barge_in):
                    return True

            if self._speak_system(text, on_barge_in, on_level):
                return True

            if self._speak_pyttsx3(text, on_barge_in, on_level):
                return True

            return False

        finally:
            self._stop_barge_monitor()

            with self._tts_lock:
                self._is_speaking = False

            if on_level:
                try:
                    on_level(0.0)
                except Exception:
                    pass

    # -----------------------------------------------------------------
    # ElevenLabs configuration
    # -----------------------------------------------------------------

    @staticmethod
    def _elevenlabs_configured() -> bool:
        api_key = (
            getattr(config, "ELEVENLABS_API_KEY", "")
            or os.getenv("ELEVENLABS_API_KEY", "")
        )
        voice_id = (
            getattr(config, "ELEVENLABS_VOICE_ID", "")
            or os.getenv("ELEVENLABS_VOICE_ID", "")
        )

        return bool(api_key and voice_id)

    def _create_elevenlabs_client(self):
        from elevenlabs.client import ElevenLabs

        api_key = (
            getattr(config, "ELEVENLABS_API_KEY", "")
            or os.getenv("ELEVENLABS_API_KEY", "")
        )

        return ElevenLabs(api_key=api_key)

    def _elevenlabs_voice_id(self) -> str:
        return (
            getattr(config, "ELEVENLABS_VOICE_ID", "")
            or os.getenv("ELEVENLABS_VOICE_ID", "")
        )

    def _elevenlabs_model_id(self) -> str:
        return (
            getattr(config, "ELEVENLABS_MODEL_ID", "")
            or os.getenv("ELEVENLABS_MODEL_ID", "")
            or "eleven_flash_v2_5"
        )

    # -----------------------------------------------------------------
    # ElevenLabs streaming
    # -----------------------------------------------------------------

    def _speak_elevenlabs_stream(
        self,
        text: str,
        on_level=None,
        on_barge_in=None,
    ) -> bool:

        if sd is None:
            return False

        client = self._create_elevenlabs_client()

        audio_iterator = client.text_to_speech.stream(
            voice_id=self._elevenlabs_voice_id(),
            text=text,
            model_id=self._elevenlabs_model_id(),
            output_format="pcm_24000",
            optimize_streaming_latency=3,
        )

        iterator = iter(audio_iterator)

        # Wait for the first audio chunk, not the complete response.
        first_chunk = next(iterator, None)

        if not first_chunk:
            return False

        if self._playback_stop.is_set():
            return False

        stream = sd.RawOutputStream(
            samplerate=self.OUTPUT_RATE,
            channels=self.OUTPUT_CHANNELS,
            dtype="int16",
            blocksize=0,
        )

        stream.start()

        with self._output_lock:
            self._output_stream = stream

        self._start_barge_monitor(on_barge_in)

        try:
            self._write_pcm_chunk(stream, first_chunk, on_level)

            for chunk in iterator:
                if self._playback_stop.is_set():
                    break

                if not chunk:
                    continue

                self._write_pcm_chunk(stream, chunk, on_level)

            return True

        finally:
            with self._output_lock:
                if self._output_stream is stream:
                    self._output_stream = None

            try:
                if self._playback_stop.is_set():
                    stream.abort()
                else:
                    stream.stop()
            except Exception:
                pass

            try:
                stream.close()
            except Exception:
                pass

    # -----------------------------------------------------------------
    # PCM playback
    # -----------------------------------------------------------------

    def _write_pcm_chunk(
        self,
        stream,
        chunk: bytes,
        on_level=None,
    ) -> None:

        if self._playback_stop.is_set():
            return

        if not isinstance(chunk, (bytes, bytearray)):
            return

        # PCM signed 16-bit data must contain complete samples.
        chunk = bytes(chunk)

        if len(chunk) % 2:
            chunk = chunk[:-1]

        if not chunk:
            return

        # Small writes keep playback responsive to interruption.
        samples_per_block = 2400
        bytes_per_block = samples_per_block * 2

        for offset in range(0, len(chunk), bytes_per_block):
            if self._playback_stop.is_set():
                break

            block = chunk[offset:offset + bytes_per_block]

            if not block:
                continue

            stream.write(block)

            if on_level:
                self._report_playback_level(block, on_level)

    @staticmethod
    def _report_playback_level(
        pcm_bytes: bytes,
        callback: Callable[[float], None],
    ) -> None:

        if np is None or not pcm_bytes:
            return

        try:
            samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
            rms = float(np.sqrt(np.mean(samples * samples)))
            callback(min(1.0, rms / 12000.0))
        except Exception:
            logger.debug("Playback-level calculation failed.", exc_info=True)

    # -----------------------------------------------------------------
    # macOS rendered speech fallback
    # -----------------------------------------------------------------

    def _speak_rendered(self, text: str, on_barge_in=None) -> bool:
        if sys.platform != "darwin":
            return False

        if shutil.which("say") is None or sd is None:
            return False

        temp_path = None

        try:
            with tempfile.NamedTemporaryFile(
                suffix=".aiff",
                delete=False,
            ) as temp:
                temp_path = temp.name

            subprocess.run(
                ["say", "-o", temp_path, text],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60,
            )

            if self._playback_stop.is_set():
                return False

            import soundfile as sf

            audio, sample_rate = sf.read(
                temp_path,
                dtype="float32",
                always_2d=True,
            )

            self._start_barge_monitor(on_barge_in)

            sd.play(audio, sample_rate)

            while sd.get_stream().active:
                if self._playback_stop.wait(0.03):
                    sd.stop()
                    break

            return True

        except Exception:
            logger.debug("macOS speech fallback failed.", exc_info=True)
            return False

        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    # -----------------------------------------------------------------
    # Windows / Linux native speech
    # -----------------------------------------------------------------

    def _speak_system(
        self,
        text: str,
        on_barge_in=None,
        on_level=None,
    ) -> bool:

        system = platform.system()

        try:
            if system == "Windows":
                executable = shutil.which("powershell.exe") or shutil.which("pwsh")

                if not executable:
                    return False

                escaped = text.replace("'", "''")

                command = (
                    "Add-Type -AssemblyName System.Speech; "
                    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    f"$s.Speak('{escaped}'); "
                    "$s.Dispose()"
                )

                args = [
                    executable,
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    command,
                ]

            else:
                executable = shutil.which("espeak-ng") or shutil.which("espeak")

                if not executable:
                    return False

                args = [executable, text]

            process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            with self._output_lock:
                self._tts_process = process

            self._start_barge_monitor(on_barge_in)

            while process.poll() is None:
                if self._playback_stop.wait(0.03):
                    process.terminate()
                    break

            if process.poll() is None:
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    process.kill()

            return True

        except Exception:
            logger.debug("Native system speech failed.", exc_info=True)
            return False

        finally:
            with self._output_lock:
                self._tts_process = None

    # -----------------------------------------------------------------
    # pyttsx3 fallback
    # -----------------------------------------------------------------

    def _speak_pyttsx3(
        self,
        text: str,
        on_barge_in=None,
        on_level=None,
    ) -> bool:

        try:
            import pyttsx3

            engine = pyttsx3.init()
            self._pyttsx_engine = engine

            if self._playback_stop.is_set():
                engine.stop()
                return False

            engine.say(text)

            # pyttsx3's run loop is blocking. Run it in a worker thread
            # so the calling worker can still react to cancellation.
            finished = threading.Event()
            errors = []

            def run_engine():
                try:
                    engine.runAndWait()
                except Exception as exc:
                    errors.append(exc)
                finally:
                    finished.set()

            worker = threading.Thread(
                target=run_engine,
                name="PyttsxPlayback",
                daemon=True,
            )
            worker.start()

            self._start_barge_monitor(on_barge_in)

            while not finished.wait(0.04):
                if self._playback_stop.is_set():
                    try:
                        engine.stop()
                    except Exception:
                        pass
                    break

            worker.join(timeout=0.5)

            if errors:
                raise errors[0]

            return True

        except Exception:
            logger.debug("pyttsx3 fallback failed.", exc_info=True)
            return False

        finally:
            self._pyttsx_engine = None