"""G5.29: Read a bounded UTF-8 text file."""
from actions._file_helpers import read_text_file as _read_text_file
ACTION_ID = "read_text_file"
DESCRIPTION = "Read up to 64 KiB from an explicitly named recognised UTF-8 text file."
def run() -> str:
    return _read_text_file(ACTION_ARGUMENTS)
