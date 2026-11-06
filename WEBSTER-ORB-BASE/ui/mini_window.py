
"""WEBSTER G4 floating orb, input bar and activity log."""

from __future__ import annotations

import logging
import time
from collections import deque

from PySide6.QtCore import Qt, QTimer, Slot, QPoint, QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QSizePolicy,
    QFrame,
    QListWidget,
    QListWidgetItem,
)

from assistant.assistant_manager import AssistantManager
from assistant.hotkey import GlobalHotkey
from config import (
    APP_NAME,
    HOTKEY,
    MINI_ALWAYS_ON_TOP,
    TARGET_FPS,
    THEME,
)
from system.system_monitor import SystemMonitor
from ui.orb import OrbWidget

logger = logging.getLogger(__name__)

COMPACT_SIZE = 190
CORNER_MARGIN = 24
DRAG_THRESHOLD = QApplication.startDragDistance()

CORNERS = (
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
)


class ActivityWindow(QWidget):
    """Separate lightweight activity log."""

    def __init__(self, parent=None):
        super().__init__(parent)

        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
        )
        if MINI_ALWAYS_ON_TOP:
            flags |= Qt.WindowType.WindowStaysOnTopHint

        self.setWindowFlags(flags)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )
        self.setFixedSize(390, 430)

        self.setStyleSheet("""
            QWidget {
                background: transparent;
                color: #263449;
                font-family: 'Segoe UI';
            }
            QFrame#activityCard {
                background: rgba(248, 250, 255, 245);
                border: 1px solid rgba(130, 150, 180, 85);
                border-radius: 18px;
            }
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
                padding: 6px;
                color: #334155;
                font-size: 12px;
            }
            QListWidget::item {
                background: rgba(225, 233, 246, 135);
                border-radius: 9px;
                padding: 9px;
                margin: 3px 0;
            }
            QPushButton {
                background: rgba(225, 233, 246, 180);
                border: 1px solid rgba(130, 150, 180, 90);
                border-radius: 9px;
                color: #52627a;
                padding: 5px 11px;
            }
            QPushButton:hover {
                background: rgba(210, 224, 246, 230);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("activityCard")
        layout.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(15, 14, 15, 14)
        card_layout.setSpacing(10)

        header = QHBoxLayout()

        title = QLabel("✧  WEBSTER ACTIVITY")
        title.setStyleSheet(
            "font-size: 12px; font-weight: 700; "
            "letter-spacing: 1px; color: #536a91;"
        )

        close_button = QPushButton("×")
        close_button.setFixedSize(30, 28)
        close_button.clicked.connect(self.hide)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(close_button)

        self.entries = QListWidget()
        self.entries.setWordWrap(True)

        footer = QHBoxLayout()
        self.count_label = QLabel("0 events")
        self.count_label.setStyleSheet(
            "color: #8491a5; font-size: 10px;"
        )

        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(self.clear)

        footer.addWidget(self.count_label)
        footer.addStretch()
        footer.addWidget(clear_button)

        card_layout.addLayout(header)
        card_layout.addWidget(self.entries, 1)
        card_layout.addLayout(footer)

        self.history = deque(maxlen=200)

    def add_entry(self, text, level="info"):
        timestamp = time.strftime("%H:%M:%S")
        entry = f"{timestamp}   {str(text)}"

        self.history.append(entry)

        item = QListWidgetItem(entry)

        colors = {
            "error": "#c24141",
            "warn": "#b7791f",
            "warning": "#b7791f",
            "assistant": "#536a91",
            "user": "#64748b",
            "info": "#52627a",
        }

        item.setForeground(
            Qt.GlobalColor.darkGray
            if level not in colors
            else __import__(
                "PySide6.QtGui", fromlist=["QColor"]
            ).QColor(colors[level])
        )

        self.entries.addItem(item)
        self.entries.scrollToBottom()
        self.count_label.setText(
            f"{len(self.history)} events"
        )

    def clear(self):
        self.history.clear()
        self.entries.clear()
        self.count_label.setText("0 events")

    def show_near_input(self, input_bar):
        screen = input_bar.screen()
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return

        area = screen.availableGeometry()

        x = area.center().x() - self.width() // 2
        y = input_bar.y() - self.height() - 12

        if y < area.top() + 10:
            y = input_bar.y() + input_bar.height() + 12

        self.move(x, y)
        self.show()
        self.raise_()


class InputBar(QWidget):
    """Lightweight floating input bar."""

    def __init__(self, assistant, activity, parent=None):
        super().__init__(parent)

        self.assistant = assistant
        self.activity = activity

        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
        )
        if MINI_ALWAYS_ON_TOP:
            flags |= Qt.WindowType.WindowStaysOnTopHint

        self.setWindowFlags(flags)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )
        self.setFixedSize(570, 72)

        self.setStyleSheet("""
            QWidget {
                background: transparent;
                font-family: 'Segoe UI';
            }
            QFrame#inputCard {
                background: rgba(248, 250, 255, 246);
                border: 1px solid rgba(135, 153, 183, 105);
                border-radius: 22px;
            }
            QLineEdit {
                background: transparent;
                border: none;
                color: #273449;
                font-size: 14px;
                padding: 8px 5px;
                selection-background-color: #c9d9f4;
            }
            QLineEdit::placeholder {
                color: #8996aa;
            }
            QPushButton {
                border: none;
                border-radius: 15px;
                font-size: 17px;
                color: #64748b;
                background: rgba(226, 233, 245, 155);
            }
            QPushButton:hover {
                background: rgba(210, 224, 246, 230);
                color: #405d8c;
            }
            QPushButton#sendButton {
                background: #dce8fb;
                color: #45669b;
                font-size: 20px;
                font-weight: 600;
            }
            QPushButton#sendButton:hover {
                background: #cbdcf8;
            }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("inputCard")
        outer.addWidget(card)

        row = QHBoxLayout(card)
        row.setContentsMargins(12, 9, 12, 9)
        row.setSpacing(9)

        self.mic = QPushButton("◉")
        self.mic.setFixedSize(43, 43)
        self.mic.setToolTip("Toggle microphone")
        self.mic.clicked.connect(self._toggle_mic)

        self.field = QLineEdit()
        self.field.setPlaceholderText(
            "Ask anything..."
        )
        self.field.returnPressed.connect(self._submit)

        self.activity_button = QPushButton("✧")
        self.activity_button.setFixedSize(43, 43)
        self.activity_button.setToolTip(
            "Show WEBSTER activity"
        )
        self.activity_button.clicked.connect(
            self._show_activity
        )

        self.send = QPushButton("↑")
        self.send.setObjectName("sendButton")
        self.send.setFixedSize(43, 43)
        self.send.clicked.connect(self._submit)

        row.addWidget(self.mic)
        row.addWidget(self.field, 1)
        row.addWidget(self.activity_button)
        row.addWidget(self.send)

    def show_centered(self):
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return

        area = screen.availableGeometry()

        x = area.center().x() - self.width() // 2
        y = area.bottom() - self.height() - 32

        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.field.setFocus()

    def _show_activity(self):
        if self.activity.isVisible():
            self.activity.hide()
        else:
            self.activity.show_near_input(self)

    def _submit(self):
        text = self.field.text().strip()
        if not text:
            return

        self.field.clear()
        self.activity.add_entry(
            f"You: {text}", "user"
        )
        self.assistant.submit_text(text)

    def _toggle_mic(self):
        if self.assistant.state.value.lower() == "listening":
            self.assistant.cancel_listening()
        else:
            self.assistant.start_listening()


class MiniWindow(QWidget):
    """Transparent, corner-dockable WEBSTER orb."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle(APP_NAME)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )

        flags = (
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
        )
        if MINI_ALWAYS_ON_TOP:
            flags |= Qt.WindowType.WindowStaysOnTopHint

        self.setWindowFlags(flags)
        self.setStyleSheet("background: transparent;")

        self._closing = False
        self._dragging = False
        self._click_candidate = False
        self._drag_offset = QPoint()
        self._drag_start = QPoint()
        self._dock_corner = "bottom-right"

        self.setFixedSize(COMPACT_SIZE, COMPACT_SIZE)

        self.monitor = SystemMonitor()
        self._latest_stats = None

        self.assistant = AssistantManager(
            stats_provider=lambda: self.monitor.latest
        )

        self._build_orb()

        self.activity = ActivityWindow()
        self.input_bar = InputBar(
            self.assistant,
            self.activity,
        )

        self._connect()

        self._last_frame = time.monotonic()
        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._on_frame)
        self._frame_timer.start(
            max(1, int(1000 / TARGET_FPS))
        )

        self.hotkey = GlobalHotkey(HOTKEY, self)
        self.hotkey.triggered.connect(self._on_hotkey)
        self._hotkey_error = self.hotkey.start()

        self.monitor.stats_ready.connect(self._on_system_stats)
        self.monitor.failed.connect(self._on_monitor_error)
        self.monitor.start()

        self._position_at_corner(self._dock_corner)

        QTimer.singleShot(300, self.assistant.greet)

    def _build_orb(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.orb = OrbWidget()
        self.orb.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )
        self.orb.setStyleSheet("background: transparent;")
        self.orb.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.orb.installEventFilter(self)
        self.orb.setMouseTracking(True)

        layout.addWidget(self.orb)

    def _connect(self):
        self.assistant.state_changed.connect(self._on_state)
        self.assistant.message.connect(self._on_message)
        self.assistant.log.connect(self._on_log)
        self.assistant.error.connect(self._on_error)
        self.assistant.level_changed.connect(self.orb.set_level)
        self.assistant.listening_changed.connect(
            self._on_listening_changed
        )
        self.assistant.ui_action.connect(self._on_ui_action)

    @Slot(str)
    def _on_state(self, state):
        self.orb.set_state(state)
        self.activity.add_entry(
            f"Assistant state: {state}", "info"
        )

    @Slot(str, str)
    def _on_message(self, speaker, text):
        self.activity.add_entry(
            f"{speaker}: {text}",
            "assistant" if speaker.lower() != "user" else "user",
        )

    @Slot(str)
    def _on_log(self, text):
        self.activity.add_entry(text, "info")

    @Slot(str)
    def _on_error(self, text):
        self.activity.add_entry(text, "error")

    @Slot(bool)
    def _on_listening_changed(self, listening):
        self.input_bar.mic.setText(
            "●" if listening else "◉"
        )

    @Slot(str)
    def _on_ui_action(self, action):
        if action == "clear_log":
            self.activity.clear()
        elif action == "quitting":
            self.orb.start_shutdown()
        elif action == "quit":
            self.close()

    def _on_system_stats(self, stats):
        self._latest_stats = stats

    def _on_monitor_error(self, message):
        logger.warning("System monitor: %s", message)
        self.activity.add_entry(message, "warn")

    # ---------------- Docking ----------------

    def _available_screen(self, position=None):
        screen = None

        if position is not None:
            screen = QGuiApplication.screenAt(position)

        if screen is None:
            screen = QGuiApplication.screenAt(
                self.frameGeometry().center()
            )

        return (
            screen
            or self.screen()
            or QGuiApplication.primaryScreen()
        )

    def _corner_position(self, corner, screen=None):
        screen = screen or self._available_screen()
        area = screen.availableGeometry()
        margin = CORNER_MARGIN
        w, h = self.width(), self.height()

        positions = {
            "top-left": QPoint(
                area.left() + margin,
                area.top() + margin,
            ),
            "top-right": QPoint(
                area.right() - w + 1 - margin,
                area.top() + margin,
            ),
            "bottom-left": QPoint(
                area.left() + margin,
                area.bottom() - h + 1 - margin,
            ),
            "bottom-right": QPoint(
                area.right() - w + 1 - margin,
                area.bottom() - h + 1 - margin,
            ),
        }

        return positions.get(
            corner, positions["bottom-right"]
        )

    def _position_at_corner(self, corner):
        self._dock_corner = corner
        self.move(
            self._corner_position(
                corner, self._available_screen()
            )
        )

    def _snap_to_nearest_corner(self, position=None):
        screen = self._available_screen(position)
        current = self.frameGeometry().topLeft()

        nearest = min(
            CORNERS,
            key=lambda corner: (
                current - self._corner_position(corner, screen)
            ).manhattanLength(),
        )

        self._position_at_corner(nearest)

    # ---------------- Interaction ----------------

    def eventFilter(self, watched, event):
        if watched is self.orb:
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    position = event.globalPosition().toPoint()
                    self._drag_start = position
                    self._drag_offset = (
                        position - self.frameGeometry().topLeft()
                    )
                    self._click_candidate = True
                    self._dragging = False
                    return True

            elif event.type() == QEvent.Type.MouseMove:
                if (
                    self._click_candidate
                    and event.buttons()
                    & Qt.MouseButton.LeftButton
                ):
                    position = event.globalPosition().toPoint()

                    if (
                        position - self._drag_start
                    ).manhattanLength() >= DRAG_THRESHOLD:
                        self._dragging = True

                    if self._dragging:
                        self.move(position - self._drag_offset)

                    return True

            elif event.type() == QEvent.Type.MouseButtonRelease:
                if (
                    event.button() == Qt.MouseButton.LeftButton
                    and self._click_candidate
                ):
                    position = event.globalPosition().toPoint()

                    if self._dragging:
                        self._snap_to_nearest_corner(position)
                    else:
                        self._toggle_input()

                    self._click_candidate = False
                    self._dragging = False
                    return True

        return super().eventFilter(watched, event)

    def _toggle_input(self):
        if self.input_bar.isVisible():
            self.input_bar.hide()
            self.activity.hide()
        else:
            self.input_bar.show_centered()

    @Slot()
    def _on_hotkey(self):
        self.show()
        self.raise_()
        self._toggle_input()

    # ---------------- Animation ----------------

    def _on_frame(self):
        now = time.monotonic()
        dt = min(0.1, now - self._last_frame)
        self._last_frame = now

        if self.isVisible() and not self.isMinimized():
            self.orb.tick(dt)

        if self.orb.shutdown_complete and self._closing:
            self.close()

    # ---------------- Shutdown ----------------

    def closeEvent(self, event):
        if self._closing:
            self._frame_timer.stop()
            event.accept()
            return

        self._closing = True
        self._frame_timer.stop()

        try:
            self.hotkey.stop()
            self.input_bar.close()
            self.activity.close()
            self.assistant.shutdown()

            if self.monitor.isRunning():
                self.monitor.stop()
                self.monitor.wait(2000)

        except Exception:
            logger.exception("Shutdown error")

        event.accept()
