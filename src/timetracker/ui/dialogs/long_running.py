"""“Is this still running?” after the long-running threshold (PRD-01 §10). Never auto-stops."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from timetracker.core.duration import format_hm


class LongRunningDialog(QDialog):
    stop_requested = Signal()

    def __init__(self, elapsed: int, started_local: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Still running?")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        text = QLabel(
            f"The timer has been running for {format_hm(elapsed)}, since {started_local}.\n"
            "Is that right?"
        )
        text.setWordWrap(True)
        self.keep = QPushButton("Keep running")
        self.keep.setDefault(True)
        self.stop = QPushButton("Stop now")
        self.keep.clicked.connect(self.accept)
        self.stop.clicked.connect(self._stop)
        layout = QVBoxLayout(self)
        layout.addWidget(text)
        layout.addWidget(self.keep)
        layout.addWidget(self.stop)

    def _stop(self) -> None:
        self.stop_requested.emit()
        self.accept()
