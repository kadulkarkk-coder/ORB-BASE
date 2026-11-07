"""G5.14 — Toggle media playback."""
ACTION_ID = "media_play_pause"
DESCRIPTION = "Send the standard play/pause media key to the active media player."
from actions._desktop_helpers import media_play_pause as _media_play_pause
def run() -> str:
    return _media_play_pause()
