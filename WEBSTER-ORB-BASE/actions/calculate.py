"""G5.21: Evaluate a bounded basic arithmetic expression."""
from actions._file_helpers import calculate as _calculate
ACTION_ID = "calculate"
DESCRIPTION = "Calculate a basic arithmetic expression without evaluating arbitrary Python."
def run() -> str:
    return _calculate(ACTION_ARGUMENTS)
