"""G5.31: Copy a bounded file to a new path without overwriting."""
from actions._file_helpers import copy_file as _copy_file
ACTION_ID = "copy_file"
DESCRIPTION = "Copy an existing file up to 100 MiB to a new destination path without overwriting."
def run() -> str:
    return _copy_file(ACTION_ARGUMENTS)
