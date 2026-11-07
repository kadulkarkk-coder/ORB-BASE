"""G5.35: Report basic statistics for a text file."""
from actions._file_helpers import text_statistics as _text_statistics
ACTION_ID = "text_statistics"
DESCRIPTION = "Report line, character, word and UTF-8 byte counts for a text file up to 64 KiB."
def run() -> str:
    return _text_statistics(ACTION_ARGUMENTS)
