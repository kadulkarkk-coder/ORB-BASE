"""G5.18 — Read battery level and charging state."""
ACTION_ID = "battery_status"
DESCRIPTION = "Show battery percentage, charging state and estimated remaining time when available."
from actions._desktop_helpers import battery_status as _battery_status
def run() -> str:
    return _battery_status()
