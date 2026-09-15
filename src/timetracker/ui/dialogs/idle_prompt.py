"""The four-way idle prompt (FR-209, FR-210) — Toggl's dialogue, copied almost exactly.

Non-modal and non-destructive: closing it with Esc or the window button answers
nothing; the timer keeps running with the idle time kept, and the prompt stays
reachable from the tray until answered or superseded.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from timetracker.core.duration import format_hms
from timetracker.core.timeutil import zone
from timetracker.services.idle_monitor import IdleOutcome, IdleSource, IdleSpan


class IdlePromptDialog(QDialog):
    answered = Signal(object)  # IdleOutcome

    def __init__(self, span: IdleSpan, tz_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("You were away")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self._tz = tz_name

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.summary.setAccessibleName("Idle summary")
        self.hint = QLabel("What should happen to that time?")

        self.keep = QPushButton("Keep it")
        self.keep.setToolTip("The away time stays on the timer")
        self.discard = QPushButton("Discard it")
        self.discard.setToolTip("Remove the away time; the timer keeps running")
        self.discard_stop = QPushButton("Discard and stop")
        self.discard_stop.setToolTip(
            "Remove the away time and stop the timer at the moment you left"
        )
        self.split = QPushButton("Log it separately")
        self.split.setToolTip(
            "Stop at the moment you left and record the away time as its own entry"
        )
        self.keep.setDefault(True)

        for button, outcome in (
            (self.keep, IdleOutcome.KEEP),
            (self.discard, IdleOutcome.DISCARD),
            (self.discard_stop, IdleOutcome.DISCARD_AND_STOP),
            (self.split, IdleOutcome.LOG_SEPARATELY),
        ):
            button.clicked.connect(lambda _=False, o=outcome: self._answer(o))

        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(self.hint)
        for button in (self.keep, self.discard, self.discard_stop, self.split):
            layout.addWidget(button)
        self.update_span(span)

    def update_span(self, span: IdleSpan) -> None:
        since = span.started_at_utc.astimezone(zone(self._tz)).strftime("%H:%M")
        how = "The machine was asleep" if span.source is IdleSource.SUSPEND else "No input"
        state = " and counting" if span.still_idle else ""
        self.summary.setText(
            f"{how} for {format_hms(span.seconds)}{state}, since {since}.\n"
            "The timer has kept running."
        )

    def _answer(self, outcome: IdleOutcome) -> None:
        self.answered.emit(outcome)
        self.accept()
