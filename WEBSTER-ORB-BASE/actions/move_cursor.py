"""G5.57: move pointer to an explicitly supplied screen coordinate."""
ACTION_ID = "move_cursor"
DESCRIPTION = "Move the visible mouse pointer to supplied x,y coordinates; does not click or type."

def run():
    try:
        parts = [int(p.strip()) for p in ACTION_ARGUMENTS.split(",")]
        if len(parts) != 2:
            return "Supply coordinates as x,y (for example: 500,300)."
        x, y = parts
        from PySide6.QtGui import QCursor
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            return "Cursor control requires WEBSTER's active PySide6 application."
        screen = app.primaryScreen().geometry()
        if not screen.contains(QPoint(x, y)):
            return f"Coordinates must be inside the primary display: {screen.width()} x {screen.height()}."
        QCursor.setPos(x, y)
        return f"Moved the pointer to x={x}, y={y}. No click or keystroke was sent."
    except ValueError:
        return "Coordinates must be whole numbers in x,y format."
    except Exception as exc:
        return f"Could not move cursor: {exc}"
