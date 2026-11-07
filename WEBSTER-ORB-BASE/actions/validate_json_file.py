"""G5.40: Validate a JSON file without modifying it."""
from actions._file_helpers import validate_json_file as _validate_json_file
ACTION_ID = "validate_json_file"
DESCRIPTION = "Validate the syntax of an explicitly selected .json file up to 64 KiB without changing it."
def run() -> str:
    return _validate_json_file(ACTION_ARGUMENTS)
