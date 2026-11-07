"""G5.24: Create a new UTF-8 text file without overwriting."""
from actions._file_helpers import create_text_file as _create_text_file
ACTION_ID = "create_text_file"
DESCRIPTION = "Create a new UTF-8 text file using: path | content. Existing files are never overwritten."
def run() -> str:
    return _create_text_file(ACTION_ARGUMENTS)
