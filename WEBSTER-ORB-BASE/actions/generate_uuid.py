"""G5.37: Generate a random UUID."""
from actions._file_helpers import generate_uuid as _generate_uuid
ACTION_ID = "generate_uuid"
DESCRIPTION = "Generate a new random UUID identifier; takes no arguments."
def run() -> str:
    return _generate_uuid(ACTION_ARGUMENTS)
