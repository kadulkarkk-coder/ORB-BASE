"""G5.32: Rename an existing file in its current folder."""
from actions._file_helpers import rename_file as _rename_file
ACTION_ID = "rename_file"
DESCRIPTION = "Rename an existing file using: source file path | new filename; never overwrites."
def run() -> str:
    return _rename_file(ACTION_ARGUMENTS)
