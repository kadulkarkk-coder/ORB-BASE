"""G5.20 — Read local date, time and timezone."""
ACTION_ID = "current_datetime"
DESCRIPTION = "Report the current local date, time and UTC offset."
from actions._desktop_helpers import current_datetime as _current_datetime
def run() -> str:
    return _current_datetime()
