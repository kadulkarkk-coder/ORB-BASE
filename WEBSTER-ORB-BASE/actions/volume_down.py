"""G5.12 — Decrease system volume."""
ACTION_ID = "volume_down"
DESCRIPTION = "Decrease system volume using the Windows media key."
from actions._desktop_helpers import volume_down as _volume_down
def run() -> str:
    return _volume_down()
