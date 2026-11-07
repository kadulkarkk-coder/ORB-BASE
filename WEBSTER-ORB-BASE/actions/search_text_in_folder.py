"""G5.39: Search inside a bounded set of text files."""
from actions._file_helpers import search_text_in_folder as _search_text_in_folder
ACTION_ID = "search_text_in_folder"
DESCRIPTION = "Search text in a chosen folder, bounded to depth 3, 1,000 files and 30 matches."
def run() -> str:
    return _search_text_in_folder(ACTION_ARGUMENTS)
