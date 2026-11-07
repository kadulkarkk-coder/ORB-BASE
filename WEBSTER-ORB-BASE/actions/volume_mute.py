"""G5.13 — Toggle system mute."""
ACTION_ID = "volume_mute"
DESCRIPTION = "Toggle system mute using the Windows media key."
from actions._desktop_helpers import volume_mute as _volume_mute
def run() -> str:
    return _volume_mute()
