"""G5.41–G5.50 action: uptime_status."""
from actions._system_helpers import uptime_status

ACTION_ID = "uptime_status"
DESCRIPTION = "Reports system uptime and approximate last boot time."


def run() -> str:
    return uptime_status(ACTION_ARGUMENTS)
