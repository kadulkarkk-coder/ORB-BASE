"""G5.27: Search filenames within a bounded folder depth."""
from actions._file_helpers import search_files as _search_files
ACTION_ID = "search_files"
DESCRIPTION = "Search filenames (not file contents) under a chosen folder, up to depth 4 and 50 results."
def run() -> str:
    return _search_files(ACTION_ARGUMENTS)
