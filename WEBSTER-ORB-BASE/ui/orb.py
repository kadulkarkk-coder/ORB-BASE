
"""WEBSTER V6 — Fluid Watercolor Energy Orb."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from config import SHUTDOWN_SECONDS, STATE_COLORS, THEME


def _color(value, fallback="#168BEE"):
    if isinstance(value, QColor):
        return QColor(value)
    result = QColor(str(value))
    return result if result.isValid() else QColor(fallback)


def _alpha(c, value):
    result = QColor(c)
    result.setAlphaF(max(0.0, min(1.0, value)))
    return result


def _mix(a, b, amount):
    t = max(0.0, min(1.0, amount))
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
        round(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def _smooth(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


class OrbWidget(QWidget):
    """Organic animated orb with the original WEBSTER public API."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMinimumSize(140, 140)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, True
        )

        self._state = "IDLE"
        self._time = 0.0

        self._level = 0.0
        self._target_level = 0.0

        self._breathe = 0.0
        self._wobble = 0.10
        self._target_wobble = 0.10

        primary = _color(
            getattr(THEME, "primary", "#168BEE")
        )
        self._color = QColor(primary)
        self._target_color = QColor(primary)

        self._shutdown = None
        self._shutdown_alpha = 1.0

    # --------------------------------------------------
    # PUBLIC API — KEEP COMPATIBLE WITH WEBSTER
    # --------------------------------------------------

    def set_state(self, state: str):
        state = str(state).upper()
        self._state = state

        self._target_color = _color(
            STATE_COLORS.get(
                state,
                getattr(THEME, "primary", "#168BEE")
            )
        )

        self._target_wobble = {
            "IDLE": 0.10,
            "LISTENING": 0.55,
            "PROCESSING": 0.90,
            "SPEAKING": 0.75,
            "ERROR": 0.25,
            "SHUTDOWN": 0.0,
        }.get(state, 0.10)

    def set_level(self, level: float):
        try:
            self._target_level = max(
                0.0, min(1.0, float(level))
            )
        except (TypeError, ValueError):
            self._target_level = 0.0

    def start_shutdown(self):
        if self._shutdown is None:
            self._shutdown = 0.0
            self._target_color = QColor("#D8F4FF")

    @property
    def shutdown_complete(self) -> bool:
        return (
            self._shutdown is not None
            and self._shutdown >= 1.0
        )

    # --------------------------------------------------
    # ANIMATION CLOCK
    # --------------------------------------------------

    def tick(self, dt: float):
        dt = max(0.0, min(0.05, float(dt)))
        self._time += dt

        def approach(current, target, speed):
            return current + (
                target - current
            ) * (1.0 - math.exp(-speed * dt))

        self._level = approach(
            self._level, self._target_level, 12.0
        )

        self._wobble = approach(
            self._wobble, self._target_wobble, 4.0
        )

        self._breathe = (
            0.5 + 0.5 * math.sin(self._time * 1.15)
        )

        self._color = _mix(
            self._color,
            self._target_color,
            1.0 - math.exp(-3.0 * dt)
        )

        if self._shutdown is not None:
            duration = max(0.1, float(SHUTDOWN_SECONDS))
            self._shutdown = min(
                1.0, self._shutdown + dt / duration
            )
            self._shutdown_alpha = (
                1.0 - _smooth(self._shutdown)
            )

        self.update()

    # --------------------------------------------------
    # ORGANIC FLOWING WAVE
    # --------------------------------------------------

    def _draw_wave(
        self, painter, rect, phase, wave_color,
        strength, index
    ):
        """A broad, soft energy current that moves continuously."""

        w = rect.width()
        h = rect.height()

        left = rect.left()
        right = rect.right()
        center_y = rect.center().y()

        # Multiple moving points make the wave deform organically.
        speed = 1.0 + index * 0.19
        amp = h * (0.10 + self._wobble * 0.045)

        p1 = math.sin(phase * speed + index * 1.3)
        p2 = math.sin(phase * speed * 0.72 + 2.0 + index)
        p3 = math.cos(phase * speed * 0.85 + index * 2.1)

        y1 = center_y + p1 * amp
        y2 = center_y + p2 * amp * 1.5
        y3 = center_y + p3 * amp * 0.8

        ribbon = QPainterPath()
        ribbon.moveTo(left, y1)

        ribbon.cubicTo(
            left + w * 0.25, y1 - amp * 1.5,
            left + w * 0.29, y2 + amp,
            left + w * 0.52, y2
        )

        ribbon.cubicTo(
            left + w * 0.75, y2 - amp * 1.7,
            left + w * 0.80, y3 + amp,
            right, y3
        )

        ribbon.lineTo(right, y3 + amp * 3.2)

        ribbon.cubicTo(
            left + w * 0.78, y3 + amp * 4.0,
            left + w * 0.72, y2 + amp * 2.0,
            left + w * 0.50, y2 + amp * 2.8
        )

        ribbon.cubicTo(
            left + w * 0.27, y2 + amp * 3.7,
            left + w * 0.23, y1 + amp * 1.8,
            left, y1 + amp * 3.0
        )

        ribbon.closeSubpath()

        # Feathered transparency makes the ribbon blend into the orb.
        top = center_y - amp * 2.0
        bottom = center_y + amp * 5.0

        gradient = QLinearGradient(
            QPointF(0, top), QPointF(0, bottom)
        )

        gradient.setColorAt(
            0.0, _alpha(wave_color, 0.0)
        )
        gradient.setColorAt(
            0.24, _alpha(wave_color, strength * 0.20)
        )
        gradient.setColorAt(
            0.52, _alpha(wave_color, strength * 0.42)
        )
        gradient.setColorAt(
            0.76, _alpha(wave_color, strength * 0.16)
        )
        gradient.setColorAt(
            1.0, _alpha(wave_color, 0.0)
        )

        painter.fillPath(ribbon, gradient)

    # --------------------------------------------------
    # SOFT WATERCOLOUR FIELDS
    # --------------------------------------------------

    def _draw_bloom(
        self, painter, rect, phase, bloom_color, strength
    ):
        """Large drifting color formation with feathered edges."""

        center = QPointF(
            rect.center().x()
            + math.sin(phase) * rect.width() * 0.07,

            rect.center().y()
            + math.cos(phase * 0.8) * rect.height() * 0.07
        )

        gradient = QRadialGradient(
            center,
            max(rect.width(), rect.height()) * 0.82
        )

        gradient.setColorAt(
            0.0, _alpha(bloom_color, strength)
        )
        gradient.setColorAt(
            0.45, _alpha(bloom_color, strength * 0.65)
        )
        gradient.setColorAt(
            0.78, _alpha(bloom_color, strength * 0.18)
        )
        gradient.setColorAt(
            1.0, _alpha(bloom_color, 0.0)
        )

        painter.fillRect(rect, gradient)

    # --------------------------------------------------
    # MAIN RENDERER
    # --------------------------------------------------

    def paintEvent(self, event):
        side = float(min(self.width(), self.height()))

        if side <= 2:
            return

        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform
        )

        cx = self.width() * 0.5
        cy = self.height() * 0.5

        # Gentle physical breathing.
        pulse_strength = {
            "IDLE": 0.020,
            "LISTENING": 0.032,
            "PROCESSING": 0.045,
            "SPEAKING": 0.050,
            "ERROR": 0.015,
            "SHUTDOWN": 0.0,
        }.get(self._state, 0.020)

        pulse = (
            1.0
            + math.sin(self._time * 2.0)
            * pulse_strength
        )

        pulse += self._level * 0.025

        radius = side * 0.39 * pulse

        collapse = (
            _smooth(self._shutdown)
            if self._shutdown is not None else 0.0
        )

        radius *= 1.0 - 0.94 * collapse

        orb_rect = QRectF(
            cx - radius, cy - radius,
            radius * 2.0, radius * 2.0
        )

        painter.setOpacity(self._shutdown_alpha)

        painter.save()

        # All internal energy stays inside this circular mask.
        clip = QPainterPath()
        clip.addEllipse(orb_rect)
        painter.setClipPath(clip)

        # BASE: icy white -> cyan -> electric blue.
        base = QLinearGradient(
            orb_rect.topLeft(),
            orb_rect.bottomLeft()
        )

        base.setColorAt(0.00, QColor("#F8FDFF"))
        base.setColorAt(0.19, QColor("#E3F7FF"))
        base.setColorAt(0.40, QColor("#A8E5FF"))
        base.setColorAt(0.63, QColor("#43B8FF"))
        base.setColorAt(0.84, QColor("#1688F2"))
        base.setColorAt(1.00, QColor("#075BD6"))

        painter.fillRect(orb_rect, base)

        t = self._time
        energy = self._level

        # Large moving watercolor fields.
        bloom_rect = QRectF(
            cx - radius * 1.1,
            cy - radius * 1.1,
            radius * 2.2,
            radius * 2.2
        )

        self._draw_bloom(
            painter,
            bloom_rect,
            t * 0.24,
            QColor("#FFFFFF"),
            0.37
        )

        self._draw_bloom(
            painter,
            bloom_rect.translated(
                math.sin(t * 0.19) * radius * 0.12,
                math.cos(t * 0.17) * radius * 0.08
            ),
            t * 0.20 + 1.5,
            QColor("#37D4FF"),
            0.32 + energy * 0.12
        )

        self._draw_bloom(
            painter,
            bloom_rect.translated(
                math.cos(t * 0.16) * radius * 0.09,
                math.sin(t * 0.21) * radius * 0.10
            ),
            t * 0.18 + 3.0,
            QColor("#0878ED"),
            0.34 + energy * 0.14
        )

        # Three broad overlapping energy currents.
        # These are intentionally soft, not sharp stripes.
        wave_rect = QRectF(
            cx - radius * 1.15,
            cy - radius * 1.15,
            radius * 2.3,
            radius * 2.3
        )

        speed = {
            "IDLE": 0.75,
            "LISTENING": 1.45,
            "PROCESSING": 2.25,
            "SPEAKING": 1.75,
            "ERROR": 0.9,
            "SHUTDOWN": 0.0,
        }.get(self._state, 0.75)

        phase = t * speed

        self._draw_wave(
            painter, wave_rect, phase,
            QColor("#D6F9FF"),
            0.75 + energy * 0.30, 0
        )

        self._draw_wave(
            painter, wave_rect, -phase * 0.78 + 2.0,
            QColor("#43C7FF"),
            0.65 + energy * 0.35, 1
        )

        self._draw_wave(
            painter, wave_rect, phase * 0.58 + 4.0,
            QColor("#0875E8"),
            0.55 + energy * 0.35, 2
        )

        # Upper-right subtle warm reflection.
        warm = QRadialGradient(
            QPointF(
                cx + radius * 0.35,
                cy - radius * 0.70
            ),
            radius * 0.66
        )

        warm.setColorAt(
            0.0, QColor(255, 248, 231, 48)
        )
        warm.setColorAt(
            0.55, QColor(255, 248, 231, 15)
        )
        warm.setColorAt(
            1.0, QColor(255, 248, 231, 0)
        )

        painter.fillRect(orb_rect, warm)

        # Soft white illumination.
        sheen = QRadialGradient(
            QPointF(
                cx - radius * 0.28,
                cy - radius * 0.56
            ),
            radius * 0.92
        )

        sheen.setColorAt(
            0.0, QColor(255, 255, 255, 75)
        )
        sheen.setColorAt(
            0.45, QColor(255, 255, 255, 20)
        )
        sheen.setColorAt(
            1.0, QColor(255, 255, 255, 0)
        )

        painter.fillRect(orb_rect, sheen)

        # State tint stays subtle and blue-dominant.
        if self._state not in ("IDLE", "SHUTDOWN"):
            tint = QRadialGradient(
                QPointF(
                    cx + radius * 0.15,
                    cy + radius * 0.20
                ),
                radius
            )

            tint.setColorAt(
                0.0, _alpha(self._color, 0.10)
            )
            tint.setColorAt(
                1.0, _alpha(self._color, 0.0)
            )

            painter.fillRect(orb_rect, tint)

        # Audio-reactive internal light.
        if energy > 0.01:
            response = QRadialGradient(
                QPointF(cx, cy),
                radius * (0.65 + energy * 0.3)
            )

            response.setColorAt(
                0.0,
                QColor(220, 250, 255, int(18 + energy * 42))
            )
            response.setColorAt(
                0.55,
                QColor(120, 220, 255, int(8 + energy * 20))
            )
            response.setColorAt(
                1.0, QColor(120, 220, 255, 0)
            )

            painter.fillRect(orb_rect, response)

        painter.restore()

        # Soft external halo.
        halo_rect = orb_rect.adjusted(
            -radius * 0.20,
            -radius * 0.20,
            radius * 0.20,
            radius * 0.20
        )

        halo = QRadialGradient(
            orb_rect.center(),
            radius * 1.18
        )

        halo.setColorAt(
            0.70, QColor(40, 157, 255, 22)
        )
        halo.setColorAt(
            0.88, QColor(40, 157, 255, 10)
        )
        halo.setColorAt(
            1.0, QColor(40, 157, 255, 0)
        )

        painter.setOpacity(self._shutdown_alpha * 0.72)
        painter.fillRect(halo_rect, halo)

        painter.end()
