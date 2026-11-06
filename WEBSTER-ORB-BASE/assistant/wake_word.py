
"""Offline Windows wake-word listener for WEBSTER G3.

Uses Windows PowerShell 5.1 + .NET System.Speech.
Microphone audio is processed locally by Windows.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from typing import Callable


class LocalWakeWordListener:
    def __init__(
        self,
        on_wake: Callable[[], None],
        on_error: Callable[[str], None] | None = None,
        phrase: str = "ON",
        confidence: float = 0.72,
    ):
        self.on_wake = on_wake
        self.on_error = on_error
        self.phrase = phrase.upper().strip()
        self.confidence = confidence

        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> str | None:
        """Start local wake detection. Returns an error or None."""
        with self._lock:
            if self.running:
                return None

            if shutil.which("powershell.exe") is None:
                return "Windows PowerShell 5.1 was not found."

            if self.phrase != "ON":
                return "This G3 wake listener is configured for the phrase ON."

            self._stop.clear()

            script = r"""
$ErrorActionPreference = "Stop"

try {
    Add-Type -AssemblyName System.Speech

    $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine

    $choices = New-Object System.Speech.Recognition.Choices
    $choices.Add("ON")

    $builder = New-Object System.Speech.Recognition.GrammarBuilder
    $builder.Append($choices)

    $grammar = New-Object System.Speech.Recognition.Grammar($builder)
    $recognizer.LoadGrammar($grammar)
    $recognizer.SetInputToDefaultAudioDevice()

    Register-ObjectEvent -InputObject $recognizer `
        -EventName SpeechRecognized `
        -Action {
            $result = $Event.SourceEventArgs.Result
            if ($result -and $result.Confidence -ge 0.72) {
                [Console]::Out.WriteLine("WEBSTER_WAKE_ON")
                [Console]::Out.Flush()
            }
        } | Out-Null

    [Console]::Out.WriteLine("WEBSTER_WAKE_READY")
    [Console]::Out.Flush()

    $recognizer.RecognizeAsync(
        [System.Speech.Recognition.RecognizeMode]::Multiple
    )

    while ($true) {
        Start-Sleep -Milliseconds 250
    }
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 2
}
"""

            try:
                self._process = subprocess.Popen(
                    [
                        "powershell.exe",
                        "-NoLogo",
                        "-NoProfile",
                        "-NonInteractive",
                        "-STA",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-Command",
                        script,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=getattr(
                        subprocess, "CREATE_NO_WINDOW", 0
                    ),
                )
            except OSError as exc:
                self._process = None
                return f"Could not start the local wake listener: {exc}"

            self._thread = threading.Thread(
                target=self._read_output,
                name="WEBSTER-LocalWakeWord",
                daemon=True,
            )
            self._thread.start()

        return None

    def _read_output(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return

        ready_seen = False

        try:
            for line in process.stdout:
                if self._stop.is_set():
                    break

                message = line.strip()

                if message == "WEBSTER_WAKE_READY":
                    ready_seen = True

                elif message == "WEBSTER_WAKE_ON":
                    self.on_wake()

            if not self._stop.is_set() and process.poll() is not None:
                detail = ""

                if process.stderr:
                    detail = process.stderr.read().strip()

                if not ready_seen:
                    detail = detail or (
                        "Windows could not initialize its local "
                        "speech recognizer. Check that a compatible "
                        "speech-recognition language is installed."
                    )

                if detail and self.on_error:
                    self.on_error(detail)

        except Exception as exc:
            if not self._stop.is_set() and self.on_error:
                self.on_error(f"Wake listener error: {exc}")

    def stop(self) -> None:
        """Stop the PowerShell recognizer and release its microphone."""
        self._stop.set()

        process = self._process
        self._process = None

        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=1.0)
            except OSError:
                pass

        thread = self._thread
        self._thread = None

        if thread and thread.is_alive():
            thread.join(timeout=1.0)
