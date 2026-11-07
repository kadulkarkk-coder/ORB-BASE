"""G5.41–G5.50 action: inspect_zip_archive."""
from actions._system_helpers import inspect_zip_archive

ACTION_ID = "inspect_zip_archive"
DESCRIPTION = "Inspects a ZIP archive and lists bounded entry metadata without extracting it."


def run() -> str:
    return inspect_zip_archive(ACTION_ARGUMENTS)
