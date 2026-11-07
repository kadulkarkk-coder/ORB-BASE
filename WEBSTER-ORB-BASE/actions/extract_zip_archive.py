"""G5.41–G5.50 action: extract_zip_archive."""
from actions._system_helpers import extract_zip_archive

ACTION_ID = "extract_zip_archive"
DESCRIPTION = "Safely extracts a ZIP archive into an existing folder without overwriting files."


def run() -> str:
    return extract_zip_archive(ACTION_ARGUMENTS)
