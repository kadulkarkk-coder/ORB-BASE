"""G5.8 — Open an allowlisted Windows Settings page."""
ACTION_ID="open_settings"
DESCRIPTION="Open an approved Windows Settings page such as display, sound, bluetooth, network, apps or updates."
from actions._desktop_helpers import open_settings as _open_settings,require_argument
def run() -> str:
    return _open_settings(require_argument(ACTION_ARGUMENTS,"a settings page"))
