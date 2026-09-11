"""Tray icons painted at runtime.

Three states per PRD-01 §9.1: idle (outline clock on a white face, so it reads on
a grey taskbar), running (filled clock in the accent colour) and attention (idle
clock with a badge). Rendered at 16, 22 and
32 px so Windows, X11 and HiDPI each get a crisp source. Replace with real
artwork under ``resources/`` when it exists; ``tray.py`` only calls
:func:`make_icon`.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap

_SIZES = (16, 22, 32)
_ACCENT = QColor("#2f80ed")
_BADGE = QColor("#e5484d")
_FACE = QColor("#ffffff")


class TrayState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    ATTENTION = "attention"


def make_icon(state: TrayState, foreground: QColor | None = None) -> QIcon:
    """Build a multi-resolution icon for *state*.

    ``foreground`` is the line colour for outline states; defaults to a neutral
    dark grey that reads on both light and dark trays.
    """
    fg = foreground or QColor("#3a3a3a")
    icon = QIcon()
    for size in _SIZES:
        icon.addPixmap(_render(state, size, fg))
    return icon


def _render(state: TrayState, size: int, fg: QColor) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    margin = max(1.0, size * 0.09)
    stroke = max(1.0, size * 0.11)
    face = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    centre = face.center()
    radius = face.width() / 2

    if state is TrayState.RUNNING:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(_ACCENT))
        p.drawEllipse(face)
        hand_colour = QColor("#ffffff")
    else:
        p.setPen(QPen(fg, stroke))
        p.setBrush(QBrush(_FACE))
        p.drawEllipse(face)
        hand_colour = fg

    # Hands: 12 o'clock and 3 o'clock.
    p.setPen(QPen(hand_colour, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(centre, QPointF(centre.x(), centre.y() - radius * 0.55))
    p.drawLine(centre, QPointF(centre.x() + radius * 0.4, centre.y()))

    if state is TrayState.ATTENTION:
        badge_r = size * 0.22
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(_BADGE))
        p.drawEllipse(QPointF(size - badge_r - 0.5, badge_r + 0.5), badge_r, badge_r)

    p.end()
    return pm
