"""G5.19 — Read active network interfaces."""
ACTION_ID = "network_status"
DESCRIPTION = "List active network interfaces and their local IPv4 addresses."
from actions._desktop_helpers import network_status as _network_status
def run() -> str:
    return _network_status()
