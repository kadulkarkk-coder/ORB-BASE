"""G5.3 — Switch to a visible window by title."""
ACTION_ID="switch_window"
DESCRIPTION="Bring a visible window whose title contains the supplied text to the foreground."
from actions._desktop_helpers import require_argument,switch_window as _switch_window
def run() -> str:
    return _switch_window(require_argument(ACTION_ARGUMENTS,"part of a window title"))
