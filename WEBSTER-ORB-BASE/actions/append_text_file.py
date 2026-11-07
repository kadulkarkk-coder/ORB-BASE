"""G5.25: Append a small amount of text to an explicitly named file."""
from actions._file_helpers import append_text_file as _append_text_file
ACTION_ID = "append_text_file"
DESCRIPTION = "Append up to 16 KiB of text to an existing UTF-8 text file using: path | content."
def run() -> str:
    return _append_text_file(ACTION_ARGUMENTS)
