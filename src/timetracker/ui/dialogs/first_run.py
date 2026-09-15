"""First-run offer to start at login (FR-108: "offered once on first run"). Non-modal."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class AutostartOfferDialog(QDialog):
    answered = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Start at login?")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        text = QLabel(
            "Time Tracker lives in the tray. Start it automatically when you log in?\n"
            "You can change this any time in Settings."
        )
        text.setWordWrap(True)
        self.yes = QPushButton("Yes, start at login")
        self.yes.setDefault(True)
        self.no = QPushButton("No")
        self.yes.clicked.connect(lambda: self._answer(True))
        self.no.clicked.connect(lambda: self._answer(False))
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.no)
        buttons.addWidget(self.yes)
        layout = QVBoxLayout(self)
        layout.addWidget(text)
        layout.addLayout(buttons)

    def _answer(self, yes: bool) -> None:
        self.answered.emit(yes)
        self.accept()
