"""G5.41–G5.50 action: process_summary."""
from actions._system_helpers import process_summary

ACTION_ID = "process_summary"
DESCRIPTION = "Reports process counts without exposing command-line details."


def run() -> str:
    return process_summary(ACTION_ARGUMENTS)
