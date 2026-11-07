"""G5.22: Open one existing file with its default application."""
from actions._file_helpers import open_file as _open_file
ACTION_ID = "open_file"
DESCRIPTION = "Open an existing file using the operating system's default application."
def run() -> str:
    return _open_file(ACTION_ARGUMENTS)
