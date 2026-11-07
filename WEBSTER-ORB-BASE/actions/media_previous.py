"""G5.16 — Return to the previous media track."""
ACTION_ID = "media_previous"
DESCRIPTION = "Send the standard previous-track media key to the active media player."
from actions._desktop_helpers import media_previous as _media_previous
def run() -> str:
    return _media_previous()
