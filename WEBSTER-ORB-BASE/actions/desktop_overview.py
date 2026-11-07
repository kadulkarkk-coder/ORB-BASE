"""G5.10 — Open Windows Task View."""
ACTION_ID="desktop_overview"
DESCRIPTION="Use the Windows Win+Tab shortcut to open Task View."
from actions._desktop_helpers import show_desktop_overview
def run() -> str:
    return show_desktop_overview()
