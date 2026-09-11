"""Commit toast with Undo (FR-311, PRD-02 §8.2).

A child widget with an opacity animation — not a ``QMessageBox``, which would
block (P5). Stays for :data:`TOAST_MS` (≥ 10 s per FR-311); Undo hides it.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

TOAST_MS = 10_000
FADE_MS = 250


class Toast(QFrame):
    undo_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setAutoFillBackground(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.message = QLabel("")
        self.message.setAccessibleName("Confirmation")
        self.undo_button = QPushButton("Undo")
        self.undo_button.setAccessibleName("Undo last entry")
        self.undo_button.setFlat(True)
        self.undo_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.undo_button.clicked.connect(self._on_undo)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 8, 8)
        layout.addWidget(self.message, 1)
        layout.addWidget(self.undo_button)

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(FADE_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.finished.connect(self._on_anim_finished)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(TOAST_MS)
        self._timer.timeout.connect(self.fade_out)
        self.hide()

    def show_message(self, text: str, *, undoable: bool = True) -> None:
        self.message.setText(text)
        self.undo_button.setVisible(undoable)
        self._anim.stop()
        self.show()
        self.raise_()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start()

    def fade_out(self) -> None:
        self._timer.stop()
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(0.0)
        self._anim.start()

    def dismiss_now(self) -> None:
        self._timer.stop()
        self._anim.stop()
        self._effect.setOpacity(0.0)
        self.hide()

    @property
    def is_active(self) -> bool:
        return self._timer.isActive()

    def _on_undo(self) -> None:
        self.dismiss_now()
        self.undo_requested.emit()

    def _on_anim_finished(self) -> None:
        if self._effect.opacity() == 0.0:
            self.hide()
