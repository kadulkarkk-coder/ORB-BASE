"""G5.9 — Lock the Windows session."""
ACTION_ID="lock_screen"
DESCRIPTION="Lock the current Windows session."
from actions._desktop_helpers import lock_screen
def run() -> str:
    return lock_screen()
