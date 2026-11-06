
"""Native global hotkey support for WEBSTER / J.A.R.V.I.S.

Windows uses RegisterHotKey through ctypes.
The Qt signal is emitted safely from the hotkey worker thread.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import platform
import threading
import time

from PySide6.QtCore import QObject, Signal


class GlobalHotkey(QObject):
    """Register and listen for a system-wide keyboard shortcut."""

    triggered = Signal()

    # Windows constants
    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012

    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008
    MOD_NOREPEAT = 0x4000

    VK_CODES = {
        **{chr(code): code for code in range(ord("A"), ord("Z") + 1)},
        **{str(number): 0x30 + number for number in range(10)},
        "SPACE": 0x20,
        "ENTER": 0x0D,
        "RETURN": 0x0D,
        "TAB": 0x09,
        "ESC": 0x1B,
        "ESCAPE": 0x1B,
        "F1": 0x70,
        "F2": 0x71,
        "F3": 0x72,
        "F4": 0x73,
        "F5": 0x74,
        "F6": 0x75,
        "F7": 0x76,
        "F8": 0x77,
        "F9": 0x78,
        "F10": 0x79,
        "F11": 0x7A,
        "F12": 0x7B,
    }

    MODIFIERS = {
        "CTRL": MOD_CONTROL,
        "CONTROL": MOD_CONTROL,
        "SHIFT": MOD_SHIFT,
        "ALT": MOD_ALT,
        "WIN": MOD_WIN,
        "WINDOWS": MOD_WIN,
    }

    def __init__(self, hotkey: str = "ctrl+shift+j", parent=None):
        super().__init__(parent)

        self.hotkey = hotkey
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._error: str | None = None
        self._registered = False

    @classmethod
    def _parse(cls, specification: str) -> tuple[int, int]:
        """Convert a shortcut such as ctrl+shift+j into Win32 values."""
        if not specification or not specification.strip():
            raise ValueError("No hotkey was configured.")

        parts = [
            part.strip().upper()
            for part in specification.replace("-", "+").split("+")
            if part.strip()
        ]

        if not parts:
            raise ValueError("The hotkey is empty.")

        key_name = parts[-1]
        modifiers = parts[:-1]

        if key_name not in cls.VK_CODES:
            raise ValueError(f"Unsupported hotkey key: {key_name}")

        modifier_flags = cls.MOD_NOREPEAT

        for modifier in modifiers:
            if modifier not in cls.MODIFIERS:
                raise ValueError(f"Unsupported hotkey modifier: {modifier}")
            modifier_flags |= cls.MODIFIERS[modifier]

        return modifier_flags, cls.VK_CODES[key_name]

    def start(self) -> str | None:
        """Start listening. Returns an error string, or None on success."""
        if self._thread and self._thread.is_alive():
            return None

        if platform.system() != "Windows":
            return "This G3 hotkey implementation currently requires Windows."

        try:
            self._modifiers, self._virtual_key = self._parse(self.hotkey)
        except ValueError as exc:
            return str(exc)

        self._stop_event.clear()
        self._ready_event.clear()
        self._error = None

        self._thread = threading.Thread(
            target=self._windows_loop,
            name="WEBSTER-GlobalHotkey",
            daemon=True,
        )
        self._thread.start()

        if not self._ready_event.wait(timeout=4.0):
            self.stop()
            return "The Windows hotkey listener did not start in time."

        return self._error

    def _windows_loop(self) -> None:
        """Own the Win32 message queue on a dedicated thread."""
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        # Declare API signatures explicitly for 64-bit Windows.
        user32.RegisterHotKey.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_uint,
        ]
        user32.RegisterHotKey.restype = ctypes.c_bool

        user32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.UnregisterHotKey.restype = ctypes.c_bool

        user32.GetMessageW.argtypes = [
            ctypes.POINTER(ctypes.wintypes.MSG),
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_uint,
        ]
        user32.GetMessageW.restype = ctypes.c_int

        user32.TranslateMessage.argtypes = [
            ctypes.POINTER(ctypes.wintypes.MSG)
        ]
        user32.DispatchMessageW.argtypes = [
            ctypes.POINTER(ctypes.wintypes.MSG)
        ]

        user32.PostThreadMessageW.argtypes = [
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        ]
        user32.PostThreadMessageW.restype = ctypes.c_bool

        kernel32.GetCurrentThreadId.restype = ctypes.c_uint

        # Create this thread's message queue before the main thread
        # attempts to post WM_QUIT to it.
        msg = ctypes.wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)

        self._thread_id = kernel32.GetCurrentThreadId()

        HOTKEY_ID = 1
        registered = user32.RegisterHotKey(
            None,
            HOTKEY_ID,
            self._modifiers,
            self._virtual_key,
        )

        if not registered:
            error_code = ctypes.get_last_error()
            self._error = (
                "Windows could not register "
                f"{self.hotkey!r}. It may already be in use "
                f"(Windows error {error_code})."
            )
            self._ready_event.set()
            return

        self._registered = True
        self._ready_event.set()

        try:
            while not self._stop_event.is_set():
                result = user32.GetMessageW(
                    ctypes.byref(msg), None, 0, 0
                )

                if result <= 0:
                    break

                if msg.message == self.WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    self.triggered.emit()

                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        finally:
            if self._registered:
                user32.UnregisterHotKey(None, HOTKEY_ID)
                self._registered = False

    def stop(self) -> None:
        """Stop the listener and release the registered shortcut."""
        self._stop_event.set()

        if self._thread_id and platform.system() == "Windows":
            try:
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                user32.PostThreadMessageW(
                    self._thread_id,
                    self.WM_QUIT,
                    0,
                    0,
                )
            except Exception:
                pass

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        self._thread = None
        self._thread_id = None
