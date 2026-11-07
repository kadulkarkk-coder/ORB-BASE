"""G5.26: List a bounded set of entries in one existing folder."""
from actions._file_helpers import list_folder as _list_folder
ACTION_ID = "list_folder"
DESCRIPTION = "List up to 100 immediate entries in an explicitly named folder."
def run() -> str:
    return _list_folder(ACTION_ARGUMENTS)
