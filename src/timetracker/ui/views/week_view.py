"""Weekly grid (FR-510, v1.1): clients down, the seven days across, ``h:mm`` per
cell, a total row and column. Week boundaries follow the *first day of week*
setting; today's column is emphasised. Double-clicking a day cell opens the
Day view on that date.
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from timetracker.core.clock import Clock
from timetracker.core.duration import format_hm
from timetracker.core.models import Dimension
from timetracker.core.timeutil import local_date_for
from timetracker.core.weekgrid import WeekGrid, build_week_grid, week_days
from timetracker.data.entry_repo import EntryRepo
from timetracker.services.entry_service import EntryService
from timetracker.services.label_service import LabelService
from timetracker.services.settings_service import KEY_FIRST_WEEKDAY, SettingsService

_DAY_ROLE = Qt.ItemDataRole.UserRole


class WeekView(QWidget):
    day_requested = Signal(object)  # date — open the Day view there

    def __init__(
        self,
        clock: Clock,
        repo: EntryRepo,
        entries: EntryService,
        labels: LabelService,
        settings: SettingsService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._clock = clock
        self._repo = repo
        self._labels = labels
        self._settings = settings
        self._anchor = local_date_for(clock.now_utc(), clock.tz_name())
        self.grid = WeekGrid(week_days(self._anchor, settings.first_weekday))

        self.prev_button = QToolButton()
        self.prev_button.setText("‹")
        self.prev_button.setAccessibleName("Previous week")
        self.prev_button.clicked.connect(lambda: self.set_week(self._anchor - timedelta(days=7)))
        self.next_button = QToolButton()
        self.next_button.setText("›")
        self.next_button.setAccessibleName("Next week")
        self.next_button.clicked.connect(lambda: self.set_week(self._anchor + timedelta(days=7)))
        self.today_button = QToolButton()
        self.today_button.setText("This week")
        self.today_button.clicked.connect(
            lambda: self.set_week(local_date_for(self._clock.now_utc(), self._clock.tz_name()))
        )
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("d MMM yyyy")
        self.date_edit.setAccessibleName("Week of")
        self.date_edit.dateChanged.connect(lambda d: self.set_week(d.toPython()))
        self.week_label = QLabel("")
        self.totals = QLabel("")
        self.totals.setAccessibleName("Week total")

        header = QHBoxLayout()
        header.addWidget(self.prev_button)
        header.addWidget(self.date_edit)
        header.addWidget(self.next_button)
        header.addWidget(self.today_button)
        header.addWidget(self.week_label)
        header.addStretch(1)
        header.addWidget(self.totals)

        self.table = QTableWidget()
        self.table.setAccessibleName("Weekly grid")
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.addLayout(header)
        root.addWidget(self.table, 1)

        entries.entries_changed.connect(lambda _u: self.refresh())
        labels.labels_changed.connect(lambda _d: self.refresh())
        settings.setting_changed.connect(
            lambda key: self.refresh() if key == KEY_FIRST_WEEKDAY else None
        )
        self.set_week(self._anchor)

    # -- state ---------------------------------------------------------------

    @property
    def days(self) -> tuple[date, ...]:
        return self.grid.days

    def set_week(self, anchor: date) -> None:
        self._anchor = anchor
        if self.date_edit.date().toPython() != anchor:
            self.date_edit.blockSignals(True)
            self.date_edit.setDate(QDate(anchor.year, anchor.month, anchor.day))
            self.date_edit.blockSignals(False)
        self.refresh()

    def refresh(self) -> None:
        days = week_days(self._anchor, self._settings.first_weekday)
        cells = self._repo.totals_by_client_and_day(days[0], days[-1])
        names = {lab.id: lab.name for lab in self._labels.list_all(Dimension.CLIENT)}
        self.grid = build_week_grid(cells, days, names)
        self._fill()

    def _fill(self) -> None:
        grid = self.grid
        today = local_date_for(self._clock.now_utc(), self._clock.tz_name())
        first, last_day = grid.days[0].strftime("%a %d %b"), grid.days[-1].strftime("%a %d %b %Y")
        self.week_label.setText(f"{first} – {last_day}")
        self.totals.setText(f"Week total {format_hm(grid.total_seconds)}")
        bold = QFont(self.font())
        bold.setBold(True)

        self.table.clear()
        self.table.setColumnCount(len(grid.days) + 2)
        headers = ["Client"] + [d.strftime("%a %d") for d in grid.days] + ["Total"]
        self.table.setHorizontalHeaderLabels(headers)
        for col, day in enumerate(grid.days, start=1):
            item = self.table.horizontalHeaderItem(col)
            if item is not None and day == today:
                item.setFont(bold)
                item.setToolTip("Today")
        self.table.setRowCount(len(grid.rows) + 1)
        for r, row in enumerate(grid.rows):
            self.table.setItem(r, 0, QTableWidgetItem(row.name))
            for c, seconds in enumerate(row.cells, start=1):
                item = QTableWidgetItem(format_hm(seconds) if seconds else "")
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item.setData(_DAY_ROLE, grid.days[c - 1].isoformat())
                self.table.setItem(r, c, item)
            total = QTableWidgetItem(format_hm(row.total_seconds))
            total.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            total.setFont(bold)
            self.table.setItem(r, len(grid.days) + 1, total)
        last = len(grid.rows)
        label = QTableWidgetItem("Total")
        label.setFont(bold)
        self.table.setItem(last, 0, label)
        for c, seconds in enumerate(grid.day_totals, start=1):
            item = QTableWidgetItem(format_hm(seconds) if seconds else "")
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item.setFont(bold)
            item.setData(_DAY_ROLE, grid.days[c - 1].isoformat())
            self.table.setItem(last, c, item)
        grand = QTableWidgetItem(format_hm(grid.total_seconds))
        grand.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grand.setFont(bold)
        self.table.setItem(last, len(grid.days) + 1, grand)

    # -- interaction ---------------------------------------------------------

    def cell_text(self, row: int, col: int) -> str:
        item = self.table.item(row, col)
        return item.text() if item is not None else ""

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        item = self.table.item(row, col)
        raw = item.data(_DAY_ROLE) if item is not None else None
        if raw:
            self.day_requested.emit(date.fromisoformat(str(raw)))
