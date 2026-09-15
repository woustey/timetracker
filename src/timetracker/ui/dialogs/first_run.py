"""First-run dialog (NFR-09, FR-409, FR-108). Shown once; then the popover opens itself.

One screen: a sentence on where the app lives, a box for the first few clients
(one per line — they become chips, FR-409's "prompt to add the first few"), and
the start-at-login checkbox (FR-108's "offered once on first run"). Every field
is optional; *Get started* with nothing filled in is fine.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class FirstRunDialog(QDialog):
    finished_setup = Signal(list, bool)  # client names, start at login

    def __init__(self, *, autostart_available: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome to Time Tracker")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumWidth(420)

        intro = QLabel(
            "Time Tracker lives in your system tray — look for the clock icon.\n"
            "Left-click it to start a timer or add time; right-click for the menu.\n\n"
            "Who do you work for? Add a few clients now (one per line) — they become\n"
            "one-click chips. You can always type new ones later."
        )
        intro.setWordWrap(True)
        self.clients = QPlainTextEdit()
        self.clients.setPlaceholderText("Nike\nAdidas\nASICS")
        self.clients.setAccessibleName("Clients, one per line")
        self.clients.setTabChangesFocus(True)
        self.clients.setMaximumHeight(110)
        self.autostart = QCheckBox("Start Time Tracker when I log in")
        self.autostart.setAccessibleName("Start at login")
        self.autostart.setChecked(autostart_available)
        self.autostart.setEnabled(autostart_available)
        if not autostart_available:
            self.autostart.setToolTip("Not available on this desktop session")

        self.start_button = QPushButton("Get started")
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self._finish)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.start_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(QLabel("Clients"))
        layout.addWidget(self.clients)
        layout.addWidget(self.autostart)
        layout.addLayout(buttons)
        self.clients.setFocus()

    def client_names(self) -> list[str]:
        seen: list[str] = []
        for line in self.clients.toPlainText().splitlines():
            name = " ".join(line.split())
            if name and name.casefold() not in {s.casefold() for s in seen}:
                seen.append(name)
        return seen

    def _finish(self) -> None:
        self.finished_setup.emit(self.client_names(), self.autostart.isChecked())
        self.accept()
