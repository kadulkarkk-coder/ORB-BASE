"""G5.23: Create a new folder without replacing existing content."""
from actions._file_helpers import create_folder as _create_folder
ACTION_ID = "create_folder"
DESCRIPTION = "Create a new folder at the explicitly supplied path; existing paths are never replaced."
def run() -> str:
    return _create_folder(ACTION_ARGUMENTS)
