"""G5.34: Count words and characters in a text file."""
from actions._file_helpers import word_count as _word_count
ACTION_ID = "word_count"
DESCRIPTION = "Count words and characters in a recognised UTF-8 text file up to 64 KiB."
def run() -> str:
    return _word_count(ACTION_ARGUMENTS)
