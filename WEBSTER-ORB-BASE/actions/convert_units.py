"""G5.36: Convert supported everyday measurement units."""
from actions._file_helpers import convert_units as _convert_units
ACTION_ID = "convert_units"
DESCRIPTION = "Convert supported length, mass, time, volume and temperature units, e.g. 5 km to miles."
def run() -> str:
    return _convert_units(ACTION_ARGUMENTS)
