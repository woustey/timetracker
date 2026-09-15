"""“Add entry…” form in the log window: explicit date, start, duration, labels, note.

Not in either PRD; added for M5 so scenario S3's back-dated entry has a direct
path (the matrix date stepper, FR-316, is *should*).
"""

from __future__ import annotations

from datetime import date, time

from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTimeEdit,
    QWidget,
)

from timetracker.core.duration import parse_duration
from timetracker.core.models import Dimension
from timetracker.services.label_service import LabelService
from timetracker.ui.label_combo import LabelCombo


class AddEntryDialog(QDialog):
    def __init__(
        self,
        labels: LabelService,
        default_date: date,
        default_start: time,
        default_client: int | None = None,
        default_type: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add entry")
        self.setModal(True)

        self.date = QDateEdit(QDate(default_date.year, default_date.month, default_date.day))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("ddd d MMM yyyy")
        self.start = QTimeEdit(QTime(default_start.hour, default_start.minute))
        self.start.setDisplayFormat("HH:mm")
        self.duration = QLineEdit()
        self.duration.setPlaceholderText("e.g. 1:30, 1h15, 45")
        self.duration.setAccessibleName("Duration")
        # Editable: typing a new name creates the label on Add (FR-401), as in the popover.
        self.client = LabelCombo(Dimension.CLIENT, labels)
        self.client.select(default_client)
        self.type = LabelCombo(Dimension.TYPE, labels)
        self.type.select(default_type)
        self.note = QLineEdit()
        self.note.setMaxLength(500)
        self.error = QLabel("")
        self.error.setStyleSheet("color: #e5484d;")
        self.error.hide()

        form = QFormLayout(self)
        form.addRow("Date", self.date)
        form.addRow("Start", self.start)
        form.addRow("Duration", self.duration)
        form.addRow("Client", self.client)
        form.addRow("Type", self.type)
        form.addRow("Note", self.note)
        form.addRow(self.error)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add")
        self.buttons.accepted.connect(self._validate)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.duration.setFocus()

    # -- values -----------------------------------------------------------------

    def local_date(self) -> date:
        q = self.date.date()
        return date(q.year(), q.month(), q.day())

    def start_time(self) -> time:
        q = self.start.time()
        return time(q.hour(), q.minute())

    def duration_seconds(self) -> int | None:
        return parse_duration(self.duration.text())

    def client_id(self) -> int | None:
        """Resolves (and creates, if new) the typed client. Call after acceptance."""
        return self.client.commit()

    def type_id(self) -> int | None:
        return self.type.commit()

    def note_text(self) -> str | None:
        return self.note.text().strip() or None

    def _validate(self) -> None:
        seconds = self.duration_seconds()
        if seconds is None or seconds <= 0:
            self.error.setText("Enter a duration such as 1:30, 1h15 or 45.")
            self.error.show()
            self.duration.setFocus()
            return
        self.accept()
