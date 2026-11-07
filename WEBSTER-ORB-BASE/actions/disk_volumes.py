"""G5.41–G5.50 action: disk_volumes."""
from actions._system_helpers import disk_volumes

ACTION_ID = "disk_volumes"
DESCRIPTION = "Lists mounted disk volumes with total, used and free space."


def run() -> str:
    return disk_volumes(ACTION_ARGUMENTS)
