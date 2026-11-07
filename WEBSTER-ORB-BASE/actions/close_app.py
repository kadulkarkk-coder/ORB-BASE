"""G5.2 — Gracefully request an approved application to close."""
ACTION_ID="close_app"
DESCRIPTION="Ask an approved Windows application to close normally. Provide its name; unsaved-work prompts remain with the app."
from actions._desktop_helpers import close_application,require_argument
def run() -> str:
    return close_application(require_argument(ACTION_ARGUMENTS,"an application name"))
