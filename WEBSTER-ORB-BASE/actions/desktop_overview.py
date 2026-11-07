"""G5.10 — Show the desktop."""
ACTION_ID="desktop_overview"
DESCRIPTION="Use the Windows Win+D shortcut to show the desktop."
from actions._desktop_helpers import show_desktop_overview
def run() -> str:
    return show_desktop_overview()
