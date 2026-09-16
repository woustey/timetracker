"""The log window (PRD-01 §9.4; FR-501–FR-506, FR-508; FR-601/602 entry points).

Toolbar: date preset (+ custom range), client, type, method, search, Add entry…,
Delete, Undo delete, Export ▾. Table: sortable header → SQL ORDER BY, uniform
row heights, no per-row widgets (NFR-04). Footer: grand total and the
per-client / per-type subtotals, all SQL aggregates over the filter (FR-504).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, time
from pathlib import Path

from PySide6.QtCore import QDate, QItemSelection, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStatusBar,
    QTableView,
    QToolBar,
    QToolButton,
    QWidget,
)

from timetracker.core.clock import Clock
from timetracker.core.duration import format_hm
from timetracker.core.models import Dimension, RecordMethod
from timetracker.core.timeutil import local_date_for
from timetracker.data.entry_repo import EntryFilter, EntryRepo
from timetracker.services.entry_service import EntryService
from timetracker.services.export_service import ExportOptions, ExportService
from timetracker.services.import_service import ImportService
from timetracker.services.label_service import LabelService
from timetracker.services.settings_service import (
    KEY_EXPORT_PRESETS,
    KEY_FIRST_WEEKDAY,
    KEY_ROUNDING_MINUTES,
    KEY_ROUNDING_SCOPE,
    KEY_TIME_FORMAT,
    SettingsService,
)
from timetracker.ui.dialogs.add_entry import AddEntryDialog
from timetracker.ui.dialogs.export_options import ExportOptionsDialog
from timetracker.ui.dialogs.import_csv import ImportCsvDialog
from timetracker.ui.log.delegates import DateDelegate, DurationDelegate, LabelDelegate, TimeDelegate
from timetracker.ui.log.model import Col, EntryTableModel
from timetracker.ui.log.presets import DatePreset, preset_range

_ANY = "All"


class LogWindow(QMainWindow):
    closed = Signal()
    views_requested = Signal(object)  # local date or None — open the Day view (FR-509)

    def __init__(
        self,
        clock: Clock,
        repo: EntryRepo,
        entries: EntryService,
        labels: LabelService,
        settings: SettingsService,
        exporter: ExportService,
        parent: QWidget | None = None,
        *,
        importer: ImportService | None = None,
    ) -> None:
        super().__init__(parent)
        self._clock = clock
        self._repo = repo
        self._entries = entries
        self._labels = labels
        self._settings = settings
        self._exporter = exporter
        self._importer = importer
        self.setWindowTitle("Time Tracker — Log")
        self.resize(1080, 640)

        self.model = EntryTableModel(repo, entries, labels, self)

        # -- toolbar ---------------------------------------------------------
        bar = QToolBar("Filters")
        bar.setMovable(False)
        self.addToolBar(bar)

        self.preset = QComboBox()
        for p in DatePreset:
            self.preset.addItem(p.value, p.value)
        self.preset.setCurrentIndex(self.preset.findData(DatePreset.THIS_WEEK.value))
        self.preset.setAccessibleName("Date range")
        # The range is always shown, filled in from the preset; editing either
        # date switches the preset to "Custom range" so the affordance is obvious.
        self.date_from = QDateEdit()
        self.date_to = QDateEdit()
        for w, name in ((self.date_from, "From date"), (self.date_to, "To date")):
            w.setCalendarPopup(True)
            w.setDisplayFormat("ddd d MMM yyyy")
            w.setAccessibleName(name)
            w.setToolTip("Edit to set a custom range")
        self.client = QComboBox()
        self.client.setAccessibleName("Client filter")
        self.type = QComboBox()
        self.type.setAccessibleName("Type filter")
        self.method = QComboBox()
        self.method.setAccessibleName("Method filter")
        self.method.addItem(_ANY, None)
        for m in RecordMethod:
            self.method.addItem(m.display, m.value)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search notes…")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search notes")
        self.search.setMaximumWidth(220)

        bar.addWidget(QLabel(" Range "))
        bar.addWidget(self.preset)
        bar.addWidget(QLabel("  from "))
        bar.addWidget(self.date_from)
        bar.addWidget(QLabel(" to "))
        bar.addWidget(self.date_to)
        bar.addWidget(QLabel("  Client "))
        bar.addWidget(self.client)
        bar.addWidget(QLabel("  Type "))
        bar.addWidget(self.type)
        bar.addWidget(QLabel("  Method "))
        bar.addWidget(self.method)
        bar.addWidget(QLabel("  "))
        bar.addWidget(self.search)
        bar.addSeparator()

        self.add_action = QAction("Add entry…", self)
        self.add_action.setShortcut(QKeySequence("Ctrl+N"))
        self.add_action.triggered.connect(self.add_entry)
        self.delete_action = QAction("Delete", self)
        self.delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        self.delete_action.setEnabled(False)
        self.delete_action.triggered.connect(self.delete_selected)
        self.undo_action = QAction("Undo delete", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.setEnabled(False)
        self.undo_action.triggered.connect(self.undo_delete)
        bar.addAction(self.add_action)
        bar.addAction(self.delete_action)
        bar.addAction(self.undo_action)

        self.export_button = QToolButton()
        self.export_button.setText("Export")
        self.export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.export_menu = QMenu(self.export_button)
        self.export_csv_action = self.export_menu.addAction("CSV…")
        self.export_xlsx_action = self.export_menu.addAction("Excel (XLSX)…")
        self.export_csv_action.triggered.connect(lambda: self.export("csv"))
        self.export_xlsx_action.triggered.connect(lambda: self.export("xlsx"))
        self._preset_separator = self.export_menu.addSeparator()
        self.preset_actions: list[QAction] = []  # FR-608: one click per preset
        self.export_button.setMenu(self.export_menu)
        bar.addWidget(self.export_button)
        self._rebuild_preset_menu()
        self.views_action = QAction("Day view", self)
        self.views_action.setToolTip("Entries on a timeline, gaps visible (FR-509)")
        self.views_action.triggered.connect(self._open_day_view)
        bar.addAction(self.views_action)
        self.import_action = QAction("Import CSV…", self)
        self.import_action.setEnabled(importer is not None)
        self.import_action.triggered.connect(self.import_csv)
        bar.addAction(self.import_action)
        settings.setting_changed.connect(
            lambda key: self._rebuild_preset_menu() if key == KEY_EXPORT_PRESETS else None
        )

        # -- table -----------------------------------------------------------
        self.table = QTableView()
        self.table.setAccessibleName("Entries")
        self.table.setModel(self.model)
        self.table.setSortingEnabled(False)  # sorting is SQL; header clicks call sort_by()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSortIndicator(Col.START, Qt.SortOrder.DescendingOrder)
        header.sectionClicked.connect(self._on_header_clicked)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        for col, width in (
            (Col.FLAGS, 48),
            (Col.DATE, 130),
            (Col.START, 64),
            (Col.END, 64),
            (Col.DURATION, 70),
            (Col.CLIENT, 140),
            (Col.TYPE, 130),
            (Col.METHOD, 90),
        ):
            self.table.setColumnWidth(col, width)
        self.table.setItemDelegateForColumn(Col.DURATION, DurationDelegate(self.table))
        self.table.setItemDelegateForColumn(Col.DATE, DateDelegate(self.table))
        self.table.setItemDelegateForColumn(Col.START, TimeDelegate(self.table))
        self.table.setItemDelegateForColumn(Col.END, TimeDelegate(self.table))
        self.table.setItemDelegateForColumn(
            Col.CLIENT, LabelDelegate(Dimension.CLIENT, labels, self.table)
        )
        self.table.setItemDelegateForColumn(
            Col.TYPE, LabelDelegate(Dimension.TYPE, labels, self.table)
        )
        self.setCentralWidget(self.table)

        # -- footer ----------------------------------------------------------
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.totals = QLabel("")
        self.totals.setAccessibleName("Totals")
        self.status.addWidget(self.totals, 1)

        # -- wiring ----------------------------------------------------------
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self.apply_filters)
        self.preset.currentIndexChanged.connect(self._on_preset_changed)
        self.date_from.dateChanged.connect(lambda _d: self._on_date_edited())
        self.date_to.dateChanged.connect(lambda _d: self._on_date_edited())
        self.client.currentIndexChanged.connect(lambda _i: self.apply_filters())
        self.type.currentIndexChanged.connect(lambda _i: self.apply_filters())
        self.method.currentIndexChanged.connect(lambda _i: self.apply_filters())
        self.search.textChanged.connect(lambda _t: self._search_timer.start())
        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        entries.entries_changed.connect(lambda _uuids: self._on_entries_changed())
        labels.labels_changed.connect(lambda _d: self._reload_label_filters())
        settings.setting_changed.connect(self._on_setting_changed)
        exporter.export_finished.connect(self._on_export_finished)
        exporter.export_failed.connect(self._on_export_failed)

        self._reload_label_filters()
        self._on_preset_changed()

    # -- filters -----------------------------------------------------------------

    def today(self) -> date:
        return local_date_for(self._clock.now_utc(), self._clock.tz_name())

    def current_preset(self) -> DatePreset:
        return DatePreset(str(self.preset.currentData()))

    def set_preset(self, preset: DatePreset) -> None:
        self.preset.setCurrentIndex(self.preset.findData(preset.value))

    def _on_preset_changed(self, *_: object) -> None:
        preset = self.current_preset()
        if preset is DatePreset.ALL:
            self._show_range(None, None)
        elif preset is not DatePreset.CUSTOM:
            start, end = preset_range(preset, self.today(), self._settings.first_weekday)
            self._show_range(start, end)
        self.apply_filters()

    def _show_range(self, start: date | None, end: date | None) -> None:
        """Reflect a range in the two date editors without triggering a filter change."""
        for editor in (self.date_from, self.date_to):
            editor.blockSignals(True)
        if start is None or end is None:
            # "All time": show the span of what exists so the fields still mean something.
            bounds = self._repo.date_bounds()
            start, end = bounds if bounds else (self.today(), self.today())
        self.date_from.setDate(QDate(start.year, start.month, start.day))
        self.date_to.setDate(QDate(end.year, end.month, end.day))
        for editor in (self.date_from, self.date_to):
            editor.blockSignals(False)

    def _on_date_edited(self) -> None:
        """A hand-edited date means a custom range, whatever preset was showing."""
        if self.date_to.date() < self.date_from.date():
            self.date_to.blockSignals(True)
            self.date_to.setDate(self.date_from.date())
            self.date_to.blockSignals(False)
        if self.current_preset() is not DatePreset.CUSTOM:
            self.preset.blockSignals(True)
            self.set_preset(DatePreset.CUSTOM)
            self.preset.blockSignals(False)
        self.apply_filters()

    def current_filter(self) -> EntryFilter:
        preset = self.current_preset()
        if preset is DatePreset.ALL:
            start = end = None
        elif preset is DatePreset.CUSTOM:
            qf, qt = self.date_from.date(), self.date_to.date()
            start = date(qf.year(), qf.month(), qf.day())
            end = date(qt.year(), qt.month(), qt.day())
        else:
            start, end = preset_range(preset, self.today(), self._settings.first_weekday)
        method = self.method.currentData()
        return EntryFilter(
            date_from=start,
            date_to=end,
            client_id=self.client.currentData(),
            type_id=self.type.currentData(),
            record_method=RecordMethod(method) if method else None,
            note_contains=self.search.text().strip() or None,
        )

    def apply_filters(self) -> None:
        self.model.set_query(self.current_filter())
        self._update_totals()

    def _reload_label_filters(self) -> None:
        for combo, dim in ((self.client, Dimension.CLIENT), (self.type, Dimension.TYPE)):
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(_ANY, None)
            for label in self._labels.list(dim):
                combo.addItem(label.name, label.id)
            pos = combo.findData(current) if current is not None else 0
            combo.setCurrentIndex(pos if pos >= 0 else 0)
            combo.blockSignals(False)

    # -- sorting -----------------------------------------------------------------

    def sort_by(self, col: Col, descending: bool) -> None:
        self.table.horizontalHeader().setSortIndicator(
            col, Qt.SortOrder.DescendingOrder if descending else Qt.SortOrder.AscendingOrder
        )
        self.model.set_query(sort_col=col, desc=descending)

    def _on_header_clicked(self, section: int) -> None:
        col = Col(section)
        if col is Col.FLAGS:
            return
        descending = (
            not self.model.sort_descending
            if col is self.model.sort_column
            else col
            in (
                Col.START,
                Col.END,
                Col.DATE,
                Col.DURATION,
            )
        )
        self.sort_by(col, descending)

    # -- totals (FR-504) ---------------------------------------------------------

    def _update_totals(self) -> None:
        summary = self.model.summary
        count = summary.count
        parts = [
            f"{count} entr{'y' if count == 1 else 'ies'}",
            f"Total {format_hm(summary.seconds)}",
        ]
        if summary.by_client:
            parts.append(
                "Clients: "
                + ", ".join(f"{t.name or '—'} {format_hm(t.seconds)}" for t in summary.by_client)
            )
        if summary.by_type:
            parts.append(
                "Types: "
                + ", ".join(f"{t.name or '—'} {format_hm(t.seconds)}" for t in summary.by_type)
            )
        self.totals.setText("   ·   ".join(parts))

    def _on_setting_changed(self, key: str) -> None:
        if key in (KEY_FIRST_WEEKDAY, KEY_TIME_FORMAT):
            self._on_preset_changed()

    def _on_entries_changed(self) -> None:
        self.model.refresh()
        self._update_totals()
        self.undo_action.setEnabled(self._entries.can_undo_delete)

    # -- selection / delete / undo (FR-506) ----------------------------------------

    def selected_entry_ids(self) -> list[int]:
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        return [self.model.entry_at(r).id for r in rows]

    def _on_selection_changed(self, _sel: QItemSelection, _desel: QItemSelection) -> None:
        self.delete_action.setEnabled(bool(self.selected_entry_ids()))

    def delete_selected(self, *, confirm: bool = True) -> list[int]:
        ids = self.selected_entry_ids()
        if not ids:
            return []
        if confirm and len(ids) > 1:
            answer = QMessageBox.question(
                self,
                "Delete entries",
                f"Delete {len(ids)} entries? You can undo this until the app closes.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return []
        self._entries.delete(ids)
        self.status.showMessage(
            f"Deleted {len(ids)} entr{'y' if len(ids) == 1 else 'ies'} — Ctrl+Z to undo", 5000
        )
        return ids

    def undo_delete(self) -> None:
        restored = self._entries.undo_delete()
        if restored:
            self.status.showMessage(
                f"Restored {len(restored)} entr{'y' if len(restored) == 1 else 'ies'}", 3000
            )

    # -- add entry ---------------------------------------------------------------

    def add_entry(self) -> None:
        client_id, type_id = self._entries.default_labels()
        default_day = self.today()
        flt = self.model.filter
        if flt.date_from and flt.date_to and not (flt.date_from <= default_day <= flt.date_to):
            default_day = flt.date_to
        dialog = AddEntryDialog(self._labels, default_day, time(9, 0), client_id, type_id, self)
        if dialog.exec() != AddEntryDialog.DialogCode.Accepted:
            return
        seconds = dialog.duration_seconds()
        assert seconds is not None
        entry = self._entries.add_manual(
            dialog.local_date(),
            dialog.start_time(),
            seconds,
            dialog.client_id(),
            dialog.type_id(),
            dialog.note_text(),
        )
        self.reveal(entry.id, entry.local_date)

    def reveal(self, entry_id: int, local_date: date) -> None:
        """Make an entry visible — widening the date range if it falls outside — and select it."""
        flt = self.model.filter
        outside = (flt.date_from is not None and local_date < flt.date_from) or (
            flt.date_to is not None and local_date > flt.date_to
        )
        if outside:
            start = min(flt.date_from or local_date, local_date)
            end = max(flt.date_to or local_date, local_date)
            self.preset.blockSignals(True)
            self.set_preset(DatePreset.CUSTOM)
            self.preset.blockSignals(False)
            self._show_range(start, end)
            self.apply_filters()
            self.status.showMessage(
                f"Added on {local_date.strftime('%a %d %b')} — range widened to show it", 6000
            )
        row = self.model.row_of(entry_id)
        while row < 0 and self.model.canFetchMore():
            self.model.fetchMore()
            row = self.model.row_of(entry_id)
        if row >= 0:
            self.table.selectRow(row)
            self.table.scrollTo(self.model.index(row, Col.DATE))

    # -- export (FR-601/602) -----------------------------------------------------

    def export(self, fmt: str) -> None:
        options_dialog = self.make_export_dialog(fmt)
        if options_dialog.exec() != ExportOptionsDialog.DialogCode.Accepted:
            return
        self._settings.set(KEY_ROUNDING_MINUTES, options_dialog.rounding_minutes())
        self._settings.set(KEY_ROUNDING_SCOPE, options_dialog.rounding_scope().value)
        self._export_with(
            fmt,
            self.build_export_options(
                fmt,
                options_dialog.rounding_minutes(),
                options_dialog.rounding_scope(),
                columns=options_dialog.columns(),
            ),
            folder=options_dialog.folder_path(),
        )

    def make_export_dialog(self, fmt: str) -> ExportOptionsDialog:
        dialog = ExportOptionsDialog(
            fmt,
            self.model.total_count,
            self._settings.rounding_minutes,
            self._settings.rounding_scope,
            self,
            folder=self._settings.export_folder,
            preset_names=self._settings.export_presets().names(),
        )
        dialog.preset_saved.connect(self._settings.save_export_preset)
        return dialog

    def build_export_options(
        self,
        fmt: str,
        rounding_minutes: int,
        scope: object,
        *,
        columns: tuple[str, ...] | None = None,
    ) -> ExportOptions:
        from timetracker.core.rounding import RoundingScope

        assert isinstance(scope, RoundingScope)
        options = ExportOptions(
            flt=self.model.filter,
            rounding_minutes=rounding_minutes,
            scope=scope,
            csv_delimiter=self._settings.csv_delimiter,
        )
        return replace(options, columns=columns) if columns else options

    # -- presets (FR-608) --------------------------------------------------------

    def _rebuild_preset_menu(self) -> None:
        for action in self.preset_actions:
            self.export_menu.removeAction(action)
        self.preset_actions = []
        presets = self._settings.export_presets().presets
        self._preset_separator.setVisible(bool(presets))
        for preset in presets:
            action = QAction(f"{preset.name}  ({preset.fmt.upper()})", self.export_menu)
            action.setToolTip(f"Export the current view to {preset.folder or 'the export folder'}")
            action.triggered.connect(lambda _c=False, name=preset.name: self.run_preset(name))
            self.export_menu.addAction(action)
            self.preset_actions.append(action)

    def run_preset(self, name: str) -> Path | None:
        """One click: export the current view with the preset, no dialog. Returns the path."""
        preset = self._settings.export_presets().get(name)
        if preset is None:
            self.status.showMessage(f"Preset “{name}” no longer exists", 8000)
            return None
        folder = Path(preset.folder) if preset.folder else self._settings.export_folder
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._on_export_failed(f"Cannot use folder {folder}: {exc}")
            return None
        path = _unused_path(folder / self.default_export_name(preset.fmt))
        options = self.build_export_options(
            preset.fmt, preset.rounding_minutes, preset.scope, columns=preset.columns
        )
        self._pending_export = (preset.fmt, options)
        self._exporter.export(options, path)
        return path

    def default_export_name(self, fmt: str) -> str:
        flt = self.model.filter
        if flt.date_from and flt.date_to:
            span = f"{flt.date_from.isoformat()}_{flt.date_to.isoformat()}"
        else:
            span = "all"
        return f"timetracker_{span}.{fmt}"

    def _export_with(
        self,
        fmt: str,
        options: ExportOptions,
        suggested: str | None = None,
        *,
        folder: Path | None = None,
    ) -> None:
        folder = folder or self._settings.export_folder
        name = suggested or self.default_export_name(fmt)
        pattern = "CSV files (*.csv)" if fmt == "csv" else "Excel workbooks (*.xlsx)"
        chosen, _ = QFileDialog.getSaveFileName(self, "Export", str(folder / name), pattern)
        if not chosen:
            return
        path = Path(chosen)
        if path.suffix.lower() != f".{fmt}":
            path = path.with_suffix(f".{fmt}")
        self._pending_export = (fmt, options)
        self._exporter.export(options, path)

    def _on_export_finished(self, path: object) -> None:
        self.status.showMessage(f"Exported to {path}", 8000)

    def _on_export_failed(self, message: str) -> None:
        pending = getattr(self, "_pending_export", None)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Export failed")
        box.setText(message)
        retry = box.addButton("Choose another name…", QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is retry and pending is not None:
            fmt, options = pending
            self._export_with(
                fmt, options, suggested=self.default_export_name(fmt).replace(".", "-2.")
            )

    def _open_day_view(self) -> None:
        """Open the Day view on the selected entry's day, else the range start, else today."""
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if rows:
            entry = self.model.entry_at(rows[0].row())
            self.views_requested.emit(entry.local_date)
            return
        self.views_requested.emit(self.model.filter.date_to)

    # -- import (FR-805) ---------------------------------------------------------

    def import_csv(self, path: Path | None = None) -> ImportCsvDialog | None:
        """Pick a file (unless given), open the mapping dialog, report the outcome."""
        if self._importer is None:
            return None
        if path is None:
            chosen, _ = QFileDialog.getOpenFileName(
                self,
                "Import CSV",
                str(self._settings.export_folder),
                "CSV files (*.csv *.txt *.tsv);;All files (*)",
            )
            if not chosen:
                return None
            path = Path(chosen)
        dialog = ImportCsvDialog(
            self._importer,
            path,
            workday_start=self._settings.workday_start,
            tz_name=self._clock.tz_name(),
            parent=self,
        )
        dialog.finished.connect(lambda _code: self._on_import_finished(dialog))
        dialog.open()
        return dialog

    def _on_import_finished(self, dialog: ImportCsvDialog) -> None:
        outcome = dialog.outcome
        if outcome is None:
            return
        parts = [f"Imported {len(outcome.created)} entries"]
        if outcome.skipped_duplicates:
            parts.append(f"{outcome.skipped_duplicates} duplicates skipped")
        if outcome.skipped_errors:
            parts.append(f"{outcome.skipped_errors} unreadable rows skipped")
        new = outcome.new_clients + outcome.new_types
        if new:
            parts.append(f"new labels: {', '.join(new)}")
        message = "; ".join(parts)
        if outcome.created:
            # Widen the range to cover the import (the model already refreshed on
            # entries_changed), then land on the earliest imported row.
            first = min(outcome.created, key=lambda e: e.started_at_utc)
            last = max(outcome.created, key=lambda e: e.started_at_utc)
            self.reveal(last.id, last.local_date)
            self.reveal(first.id, first.local_date)
        self.status.showMessage(message, 10000)

    # -- events ------------------------------------------------------------------

    def closeEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        self._search_timer.stop()
        self.model.cancel_pending()
        super().closeEvent(event)  # type: ignore[arg-type]
        self.closed.emit()


def _unused_path(path: Path) -> Path:
    """``name.csv`` → ``name-2.csv`` … so a one-click preset never overwrites a file."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem}-{n}{path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1
