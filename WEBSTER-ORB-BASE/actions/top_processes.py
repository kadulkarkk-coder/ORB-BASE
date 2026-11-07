"""G5.41–G5.50 action: top_processes."""
from actions._system_helpers import top_processes

ACTION_ID = "top_processes"
DESCRIPTION = "Shows up to ten processes with the highest memory use."


def run() -> str:
    return top_processes(ACTION_ARGUMENTS)
