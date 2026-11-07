"""G5.6 — Open an HTTP(S) website."""
ACTION_ID="open_website"
DESCRIPTION="Open a complete http:// or https:// URL in a new browser tab. Provide the URL."
from actions._desktop_helpers import open_website as _open_website,require_argument
def run() -> str:
    return _open_website(require_argument(ACTION_ARGUMENTS,"a website URL"))
