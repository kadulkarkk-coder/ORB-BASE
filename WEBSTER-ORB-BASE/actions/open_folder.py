"""G5.7 — Open an existing folder."""
ACTION_ID="open_folder"
DESCRIPTION="Open an existing folder in the system file manager. Provide its path; quote paths containing spaces."
from actions._desktop_helpers import open_folder as _open_folder,require_argument
def run() -> str:
    return _open_folder(require_argument(ACTION_ARGUMENTS,"a folder path"))
