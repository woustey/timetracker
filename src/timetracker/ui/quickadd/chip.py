"""Chip: one cell of the matrix (PRD-02 §8.2).

Two kinds share the class:

- **label** chips are checkable; a ``QButtonGroup`` on the column gives radio
  semantics (FR-306/307). A checked chip paints a filled background *and* a
  checkmark glyph, so colour is never the only signal (PRD-01 §9.5).
- **time** chips are not checkable; they emit :attr:`activated` with a flag
  saying whether Shift was held (FR-305) and paint a contribution-count badge.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QToolButton, QWidget

ACCENT = QColor("#2f80ed")
CHECK_GLYPH = "✓"


class ChipKind(Enum):
    TIME = "time"
    LABEL = "label"


class Chip(QToolButton):
    activated = Signal(bool)  # shift held

    def __init__(
        self,
        text: str,
        kind: ChipKind,
        *,
        value: object = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.kind = kind
        self.value = value
        self._count = 0
        self._shift_pending = False
        self.setText(text)
        self.setAccessibleName(text)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(30)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("chip", True)
        if kind is ChipKind.LABEL:
            self.setCheckable(True)
        self.clicked.connect(self._on_clicked)

    # -- time chips ----------------------------------------------------------

    @property
    def count(self) -> int:
        return self._count

    def set_count(self, count: int) -> None:
        count = max(0, count)
        if count != self._count:
            self._count = count
            self.setAccessibleDescription(f"added {count} times" if count else "")
            self.update()

    # -- events --------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        self._shift_pending = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        super().mousePressEvent(event)

    def _on_clicked(self) -> None:
        shift, self._shift_pending = self._shift_pending, False
        self.activated.emit(shift)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = self.rect()
        if self.kind is ChipKind.LABEL and self.isChecked():
            # The stylesheet fills a checked chip with the accent; the glyph is white on it.
            painter.setPen(QPen(QColor("white")))
            painter.drawText(
                rect.adjusted(0, 0, -8, 0),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                CHECK_GLYPH,
            )
        elif self.kind is ChipKind.TIME and self._count > 0:
            label = f"×{self._count}" if self._count > 1 else CHECK_GLYPH
            fm = QFontMetrics(self.font())
            w = fm.horizontalAdvance(label) + 10
            h = fm.height() + 2
            badge = QRect(rect.right() - w - 4, rect.top() + (rect.height() - h) // 2, w, h)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ACCENT)
            painter.drawRoundedRect(badge, h / 2, h / 2)
            painter.setPen(QPen(QColor("white")))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, label)
        painter.end()


CHIP_STYLE = """
QToolButton[chip="true"] {
    border: 1px solid palette(mid);
    border-radius: 6px;
    padding: 4px 22px 4px 10px;
    text-align: left;
    background: palette(button);
}
QToolButton[chip="true"]:hover { border-color: #2f80ed; }
QToolButton[chip="true"]:focus { border: 2px solid #2f80ed; }
QToolButton[chip="true"]:checked { background: #2f80ed; color: white; border-color: #2f80ed; }
"""
