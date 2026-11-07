"""G5.41–G5.50 action: clipboard_copy."""
from actions._system_helpers import clipboard_copy

ACTION_ID = "clipboard_copy"
DESCRIPTION = "Copies explicitly supplied text to the desktop clipboard (up to 16 KiB)."


def run() -> str:
    return clipboard_copy(ACTION_ARGUMENTS)
