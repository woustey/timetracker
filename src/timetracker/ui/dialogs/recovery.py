"""Crash-recovery dialog (FR-207): offer the entry the last heartbeat vouches for."""

from __future__ import annotations

from enum import Enum

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from timetracker.core.duration import format_hms
from timetracker.core.timeutil import zone
from timetracker.services.timer_service import RecoveryOffer


class RecoveryChoice(Enum):
    RECOVER = "recover"
    DISCARD = "discard"


class RecoveryDialog(QDialog):
    def __init__(
        self,
        offer: RecoveryOffer,
        client_name: str | None,
        type_name: str | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Recover unsaved timer?")
        self.setModal(True)
        self.choice = RecoveryChoice.DISCARD

        t = offer.timer
        tz = zone(t.tz_name)
        started = t.started_at_utc.astimezone(tz).strftime("%a %d %b %H:%M")
        until = t.heartbeat_at_utc.astimezone(tz).strftime("%H:%M:%S")
        labels = " · ".join(x for x in (type_name, client_name) if x) or "no labels"

        text = QLabel(
            "A timer was running when Time Tracker last closed.\n\n"
            f"Started {started} — {labels}\n"
            f"Recorded up to {until}: {format_hms(offer.duration_seconds)}\n\n"
            "Recover it as an entry, or discard it?"
        )
        text.setWordWrap(True)

        buttons = QDialogButtonBox()
        self.recover_button = buttons.addButton(
            "Recover entry", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.discard_button = buttons.addButton(
            "Discard", QDialogButtonBox.ButtonRole.DestructiveRole
        )
        self.recover_button.setDefault(True)
        buttons.accepted.connect(self._recover)
        buttons.rejected.connect(self.reject)
        self.discard_button.clicked.connect(self._discard)

        layout = QVBoxLayout(self)
        layout.addWidget(text)
        layout.addWidget(buttons)

    def _recover(self) -> None:
        self.choice = RecoveryChoice.RECOVER
        self.accept()

    def _discard(self) -> None:
        self.choice = RecoveryChoice.DISCARD
        self.accept()
