"""G5.30: Find a phrase in a bounded UTF-8 text file."""
from actions._file_helpers import find_text_in_file as _find_text_in_file
ACTION_ID = "find_text_in_file"
DESCRIPTION = "Find a phrase in an explicitly named text file (path | phrase), returning up to 50 matches."
def run() -> str:
    return _find_text_in_file(ACTION_ARGUMENTS)
