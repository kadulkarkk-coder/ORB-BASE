"""G5.4 — Minimize the active window."""
ACTION_ID="minimize_window"
DESCRIPTION="Minimize the currently active desktop window."
from actions._desktop_helpers import minimize_active_window
def run() -> str:
    return minimize_active_window()
