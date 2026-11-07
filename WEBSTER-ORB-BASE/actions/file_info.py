"""G5.28: Show metadata for one existing regular file."""
from actions._file_helpers import file_info as _file_info
ACTION_ID = "file_info"
DESCRIPTION = "Show the name, path, size, extension and modified time of one existing file."
def run() -> str:
    return _file_info(ACTION_ARGUMENTS)
