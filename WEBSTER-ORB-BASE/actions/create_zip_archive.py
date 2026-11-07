"""G5.41–G5.50 action: create_zip_archive."""
from actions._system_helpers import create_zip_archive

ACTION_ID = "create_zip_archive"
DESCRIPTION = "Creates a ZIP archive from an existing folder without overwriting existing files."


def run() -> str:
    return create_zip_archive(ACTION_ARGUMENTS)
