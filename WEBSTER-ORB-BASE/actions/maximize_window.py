"""G5.5 — Maximize or restore the active window."""
ACTION_ID="maximize_window"
DESCRIPTION="Maximize the active window, or restore it if it is already maximized."
from actions._desktop_helpers import toggle_maximize_active_window
def run() -> str:
    return toggle_maximize_active_window()
