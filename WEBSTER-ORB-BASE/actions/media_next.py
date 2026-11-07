"""G5.15 — Skip to the next media track."""
ACTION_ID = "media_next"
DESCRIPTION = "Send the standard next-track media key to the active media player."
from actions._desktop_helpers import media_next as _media_next
def run() -> str:
    return _media_next()
