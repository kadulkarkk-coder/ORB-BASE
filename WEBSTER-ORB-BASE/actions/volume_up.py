"""G5.11 — Increase system volume."""
ACTION_ID = "volume_up"
DESCRIPTION = "Increase system volume using the Windows media key."
from actions._desktop_helpers import volume_up as _volume_up
def run() -> str:
    return _volume_up()
