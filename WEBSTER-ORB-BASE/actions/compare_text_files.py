"""G5.38: Compare two small UTF-8 text files."""
from actions._file_helpers import compare_text_files as _compare_text_files
ACTION_ID = "compare_text_files"
DESCRIPTION = "Compare two recognised UTF-8 text files up to 64 KiB each and show a short diff."
def run() -> str:
    return _compare_text_files(ACTION_ARGUMENTS)
