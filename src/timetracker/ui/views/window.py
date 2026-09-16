"""The *Views* window (v1.1): a tab per view — *Day* (FR-509) and *Week*
(FR-510). Opened from the log's toolbar; double-clicking an entry in the Day
view asks the app to reveal it in the log, double-clicking a Week cell opens
that day."""

from __future__ import annotations

from datetime import date, time

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMainWindow, QTabWidget, QWidget

from timetracker.core.clock import Clock
from timetracker.data.entry_repo import EntryRepo
from timetracker.services.entry_service import EntryService
from timetracker.services.label_service import LabelService
from timetracker.services.settings_service import SettingsService
from timetracker.ui.views.day_view import DayView
from timetracker.ui.views.week_view import WeekView


class ViewsWindow(QMainWindow):
    closed = Signal()
    entry_activated = Signal(int, object)  # entry id, local date

    def __init__(
        self,
        clock: Clock,
        repo: EntryRepo,
        entries: EntryService,
        labels: LabelService,
        settings: SettingsService,
        *,
        workday_start: time = time(9, 0),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Time Tracker — Views")
        self.resize(760, 640)
        self.tabs = QTabWidget()
        self.day_view = DayView(clock, repo, entries, labels, workday_start=workday_start)
        self.day_view.entry_activated.connect(self.entry_activated.emit)
        self.tabs.addTab(self.day_view, "Day")
        self.week_view = WeekView(clock, repo, entries, labels, settings)
        self.week_view.day_requested.connect(self.show_day)
        self.tabs.addTab(self.week_view, "Week")
        self.setCentralWidget(self.tabs)

    def show_day(self, day: date | None = None) -> None:
        self.tabs.setCurrentWidget(self.day_view)
        if day is not None:
            self.day_view.set_day(day)
        else:
            self.day_view.refresh()
        self.show()
        self.raise_()
        self.activateWindow()

    def show_week(self, anchor: date | None = None) -> None:
        self.tabs.setCurrentWidget(self.week_view)
        if anchor is not None:
            self.week_view.set_week(anchor)
        else:
            self.week_view.refresh()
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        super().closeEvent(event)  # type: ignore[arg-type]
        self.closed.emit()
