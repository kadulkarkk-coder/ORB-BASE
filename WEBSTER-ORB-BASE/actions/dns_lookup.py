"""G5.41–G5.50 action: dns_lookup."""
from actions._system_helpers import dns_lookup

ACTION_ID = "dns_lookup"
DESCRIPTION = "Looks up DNS addresses for one explicitly supplied hostname."


def run() -> str:
    return dns_lookup(ACTION_ARGUMENTS)
