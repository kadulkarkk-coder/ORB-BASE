"""WEBSTER V5 — Watercolor Energy Orb."""

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


def color(value, fallback="#168BEE"):
    if isinstance(value, QColor):
        return QColor(value)

    result = QColor(str(value))
    return result if result.isValid() else QColor(fallback)


def alpha_color(c, alpha):
    result = QColor(c)
    result.setAlphaF(max(0.0, min(1.0, alpha)))
    return result


def smoothstep(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def mix_color(a, b, amount):
    t = max(0.0, min(1.0, amount))

    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
        round(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def cloud_path(rect, phase, variant=0):
    """Create an organic, asymmetric watercolor cloud."""

    cx = rect.center().x()
    cy = rect.center().y()

    rx = rect.width() * 0.5
    ry = rect.height() * 0.5

    k = math.sin(phase + variant * 1.7)
    q = math.cos(phase * 0.83 + variant * 1.1)

    path = QPainterPath()

    path.moveTo(cx - rx * 0.94, cy - ry * 0.04)

    path.cubicTo(
        cx - rx * (0.82 + 0.05 * k),
        cy - ry * (0.92 + 0.04 * q),
        cx + rx * (0.25 + 0.06 * q),
        cy - ry * (1.02 - 0.03 * k),
        cx + rx * (0.92 - 0.04 * q),
        cy - ry * (0.43 + 0.05 * k),
    )

    path.cubicTo(
        cx + rx * (1.08 + 0.02 * k),
        cy + ry * (0.23 + 0.04 * q),
        cx + rx * (0.42 - 0.05 * q),
        cy + ry * (0.96 + 0.03 * k),
        cx - rx * (0.22 + 0.04 * k),
        cy + ry * (0.91 - 0.04 * q),
    )

    path.cubicTo(
        cx - rx * (0.84 - 0.03 * q),
        cy + ry * (0.83 + 0.04 * k),
        cx - rx * (1.06 + 0.02 * q),
        cy + ry * (0.39 - 0.04 * k),
        cx - rx * 0.94,
        cy - ry * 0.04,
    )

    path.closeSubpath()
    return path


class OrbWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMinimumSize(140, 140)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True
        )

        self._state = "IDLE"
        self._time = 0.0

        self._level = 0.0
        self._target_level = 0.0

        self._breathe = 0.0
        self._wobble = 0.10
        self._target_wobble = 0.10

        primary = color(getattr(THEME, "primary", "#168BEE"))

        self._color = QColor(primary)
        self._target_color = QColor(primary)

        self._shutdown = None
        self._shutdown_alpha = 1.0

    # -------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------

    def set_state(self, state: str):
        state = str(state).upper()
        self._state = state

        self._target_color = color(
            STATE_COLORS.get(
                state,
                getattr(THEME, "primary", "#168BEE")
            )
        )

        self._target_wobble = {
            "IDLE": 0.10,
            "LISTENING": 0.48,
            "PROCESSING": 0.72,
            "SPEAKING": 0.88,
            "ERROR": 0.22,
            "SHUTDOWN": 0.0,
        }.get(state, 0.10)

    def set_level(self, level: float):
        try:
            self._target_level = max(
                0.0,
                min(1.0, float(level))
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

    # -------------------------------------------------
    # ANIMATION
    # -------------------------------------------------

    def tick(self, dt: float):

        dt = max(0.0, min(0.05, float(dt)))
        self._time += dt

        def approach(current, target, rate):
            return current + (
                target - current
            ) * (1.0 - math.exp(-rate * dt))

        self._level = approach(
            self._level,
            self._target_level,
            12.0
        )

        self._wobble = approach(
            self._wobble,
            self._target_wobble,
            4.5
        )

        self._breathe = (
            0.5 + 0.5 * math.sin(self._time * 1.05)
        )

        self._color = mix_color(
            self._color,
            self._target_color,
            1.0 - math.exp(-3.0 * dt)
        )

        if self._shutdown is not None:

            duration = max(0.1, float(SHUTDOWN_SECONDS))

            self._shutdown = min(
                1.0,
                self._shutdown + dt / duration
            )

            self._shutdown_alpha = (
                1.0 - smoothstep(self._shutdown)
            )

        self.update()

    # -------------------------------------------------
    # WATERCOLOR CLOUD RENDERING
    # -------------------------------------------------

    def draw_cloud(
        self,
        painter,
        rect,
        phase,
        cloud_color,
        strength,
        variant
    ):

        path = cloud_path(rect, phase, variant)

        painter.save()

        painter.setClipPath(
            path,
            Qt.ClipOperation.IntersectClip
        )

        center = QPointF(
            rect.center().x()
            + math.sin(phase + variant)
            * rect.width() * 0.07,

            rect.center().y()
            + math.cos(phase * 0.8 + variant)
            * rect.height() * 0.06
        )

        radius = max(
            rect.width(),
            rect.height()
        ) * 0.78

        gradient = QRadialGradient(center, radius)

        gradient.setColorAt(
            0.0,
            alpha_color(cloud_color, strength)
        )

        gradient.setColorAt(
            0.48,
            alpha_color(cloud_color, strength * 0.68)
        )

        gradient.setColorAt(
            0.78,
            alpha_color(cloud_color, strength * 0.22)
        )

        gradient.setColorAt(
            1.0,
            alpha_color(cloud_color, 0.0)
        )

        painter.fillRect(
            rect.adjusted(-8, -8, 8, 8),
            gradient
        )

        painter.restore()

    # -------------------------------------------------
    # MAIN PAINT EVENT
    # -------------------------------------------------

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

        diameter = side * 0.78
        radius = diameter * 0.5

        cx = self.width() * 0.5
        cy = self.height() * 0.5

        collapse = 0.0

        if self._shutdown is not None:
            collapse = smoothstep(self._shutdown)

        scale = 1.0 - 0.94 * collapse
        radius *= scale

        orb_rect = QRectF(
            cx - radius,
            cy - radius,
            radius * 2.0,
            radius * 2.0
        )

        painter.setOpacity(self._shutdown_alpha)

        painter.save()

        # Perfect circular silhouette.
        circle = QPainterPath()
        circle.addEllipse(orb_rect)

        painter.setClipPath(circle)

        # -------------------------------------------------
        # BASE COLOR: WHITE -> CYAN -> ELECTRIC BLUE
        # -------------------------------------------------

        base = QLinearGradient(
            orb_rect.topLeft(),
            orb_rect.bottomLeft()
        )

        base.setColorAt(0.00, QColor("#F8FDFF"))
        base.setColorAt(0.18, QColor("#E4F7FF"))
        base.setColorAt(0.40, QColor("#A9E5FF"))
        base.setColorAt(0.64, QColor("#42B5FF"))
        base.setColorAt(0.84, QColor("#1688F2"))
        base.setColorAt(1.00, QColor("#075BD6"))

        painter.fillRect(orb_rect, base)

        # -------------------------------------------------
        # ORGANIC ENERGY FIELDS
        # -------------------------------------------------

        t = self._time
        energy = self._level
        motion = self._wobble

        drift = 0.025 + motion * 0.035

        cloud_w = radius * 1.72
        cloud_h = radius * 0.88

        # Upper white watercolor region.
        upper_rect = QRectF(
            cx - cloud_w * 0.50
            + math.sin(t * 0.20) * radius * drift,

            cy - radius * 0.62
            + math.cos(t * 0.17) * radius * 0.025,

            cloud_w,
            cloud_h
        )

        self.draw_cloud(
            painter,
            upper_rect,
            t * (0.16 + motion * 0.10),
            QColor("#FFFFFF"),
            0.76,
            0
        )

        # Middle cyan region.
        cyan_rect = QRectF(
            cx - radius * 0.98
            + math.sin(t * 0.24 + 1.2) * radius * drift,

            cy - radius * 0.18
            + math.cos(t * 0.19) * radius * 0.045,

            radius * 1.92,
            radius * 1.02
        )

        self.draw_cloud(
            painter,
            cyan_rect,
            t * (0.19 + motion * 0.13),
            QColor("#42D6FF"),
            0.47 + energy * 0.10,
            1
        )

        # Deep blue energy region.
        blue_rect = QRectF(
            cx - radius * 1.02
            + math.sin(t * 0.18 + 2.0) * radius * drift,

            cy + radius * 0.12
            + math.cos(t * 0.22 + 0.7) * radius * 0.035,

            radius * 2.04,
            radius * 1.10
        )

        self.draw_cloud(
            painter,
            blue_rect,
            t * (0.17 + motion * 0.16),
            QColor("#087BEE"),
            0.48 + energy * 0.18,
            2
        )

        # Bottom electric-blue depth.
        lower_rect = QRectF(
            cx - radius * 0.86
            + math.sin(t * 0.21 + 3.4) * radius * drift,

            cy + radius * 0.52
            + math.cos(t * 0.16 + 1.4) * radius * 0.025,

            radius * 1.72,
            radius * 0.78
        )

        self.draw_cloud(
            painter,
            lower_rect,
            t * (0.14 + motion * 0.12),
            QColor("#0056D8"),
            0.40 + energy * 0.15,
            3
        )

        # -------------------------------------------------
        # SUBTLE LIGHTING
        # -------------------------------------------------

        warm = QRadialGradient(
            QPointF(
                cx + radius * 0.35,
                cy - radius * 0.70
            ),
            radius * 0.66
        )

        warm.setColorAt(
            0.0,
            QColor(255, 248, 231, 58)
        )

        warm.setColorAt(
            0.55,
            QColor(255, 248, 231, 18)
        )

        warm.setColorAt(
            1.0,
            QColor(255, 248, 231, 0)
        )

        painter.fillRect(orb_rect, warm)

        sheen = QRadialGradient(
            QPointF(
                cx - radius * 0.28,
                cy - radius * 0.56
            ),
            radius * 0.92
        )

        sheen.setColorAt(
            0.0,
            QColor(255, 255, 255, 92)
        )

        sheen.setColorAt(
            0.42,
            QColor(255, 255, 255, 24)
        )

        sheen.setColorAt(
            1.0,
            QColor(255, 255, 255, 0)
        )

        painter.fillRect(orb_rect, sheen)

        # State tint, kept subtle so blue remains dominant.
        if self._state not in ("IDLE", "SHUTDOWN"):

            tint = QRadialGradient(
                QPointF(
                    cx + radius * 0.18,
                    cy + radius * 0.20
                ),
                radius * 1.05
            )

            tint.setColorAt(
                0.0,
                alpha_color(self._color, 0.12)
            )

            tint.setColorAt(
                1.0,
                alpha_color(self._color, 0.0)
            )

            painter.fillRect(orb_rect, tint)

        # Audio response.
        if energy > 0.015:

            response = QRadialGradient(
                QPointF(cx, cy + radius * 0.08),
                radius * (0.78 + energy * 0.18)
            )

            response.setColorAt(
                0.0,
                QColor(
                    210, 247, 255,
                    int(22 + energy * 34)
                )
            )

            response.setColorAt(
                0.55,
                QColor(
                    130, 221, 255,
                    int(10 + energy * 15)
                )
            )

            response.setColorAt(
                1.0,
                QColor(130, 221, 255, 0)
            )

            painter.fillRect(orb_rect, response)

        painter.restore()

        # -------------------------------------------------
        # SOFT EXTERIOR HALO
        # -------------------------------------------------

        if self._shutdown is None or collapse < 0.96:

            halo_rect = orb_rect.adjusted(
                -radius * 0.18,
                -radius * 0.18,
                radius * 0.18,
                radius * 0.18
            )

            halo = QRadialGradient(
                orb_rect.center(),
                radius * 1.18
            )

            halo.setColorAt(
                0.72,
                QColor(40, 157, 255, 22)
            )

            halo.setColorAt(
                0.88,
                QColor(40, 157, 255, 11)
            )

            halo.setColorAt(
                1.0,
                QColor(40, 157, 255, 0)
            )

            painter.setOpacity(
                self._shutdown_alpha * 0.72
            )

            painter.fillRect(halo_rect, halo)

        painter.end()