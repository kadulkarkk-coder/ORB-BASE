"""G5.41–G5.50 action: python_environment."""
from actions._system_helpers import python_environment

ACTION_ID = "python_environment"
DESCRIPTION = "Reports Python version, executable, platform and virtual-environment status."


def run() -> str:
    return python_environment(ACTION_ARGUMENTS)
