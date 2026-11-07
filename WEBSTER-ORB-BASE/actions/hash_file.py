"""G5.33: Calculate a SHA-256 digest for a bounded file."""
from actions._file_helpers import hash_file as _hash_file
ACTION_ID = "hash_file"
DESCRIPTION = "Calculate a SHA-256 checksum for an explicitly selected file up to 100 MiB."
def run() -> str:
    return _hash_file(ACTION_ARGUMENTS)
