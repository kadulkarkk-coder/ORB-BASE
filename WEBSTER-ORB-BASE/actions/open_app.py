"""G5.1 — Open an approved desktop application."""
ACTION_ID="open_app"
DESCRIPTION="Launch an application from WEBSTER's approved application list. Provide its name."
from actions._desktop_helpers import open_application,require_argument
def run() -> str:
    return open_application(require_argument(ACTION_ARGUMENTS,"an application name"))
