"""G5.56: read the current pointer position."""
ACTION_ID = "cursor_position"
DESCRIPTION = "Report the current desktop cursor coordinates."

def run():
    try:
        from PySide6.QtGui import QCursor
        point = QCursor.pos()
        return f"Cursor position: x={point.x()}, y={point.y()}"
    except Exception as exc:
        return f"Cursor position is unavailable: {exc}"
