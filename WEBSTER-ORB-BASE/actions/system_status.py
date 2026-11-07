"""G5.17 — Read CPU, RAM and disk usage."""
ACTION_ID = "system_status"
DESCRIPTION = "Show a read-only summary of CPU, memory and disk usage."
from actions._desktop_helpers import system_status as _system_status
def run() -> str:
    return _system_status()
