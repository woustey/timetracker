"""Import from CSV with column mapping (FR-805, v1.1).

One dialog: the file's columns across the top as mapping combos (one per
entry field), delimiter / header / date-order controls, a preview table of
what would be written (errors in their own column), a summary line and an
**Import** button. Nothing is written until *Import*; the preview re-parses
on every change. Rows with errors are skipped, never guessed.
"""

from __future__ import annotations

from datetime import time
from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from timetracker.core.csv_import import FIELDS, ColumnMapping, CsvSample, DateOrder, guess_mapping
from timetracker.core.duration import format_hm
from timetracker.core.timeutil import zone
from timetracker.services.import_service import ImportOutcome, ImportPlan, ImportService

_FIELD_LABELS = {
    "date": "Date *",
    "start": "Start",
    "end": "End",
    "duration": "Duration",
    "client": "Client",
    "type": "Type",
    "note": "Note",
}
_PREVIEW_LIMIT = 50


class ImportCsvDialog(QDialog):
    def __init__(
        self,
        importer: ImportService,
        path: Path,
        *,
        workday_start: time = time(9, 0),
        tz_name: str = "UTC",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._importer = importer
        self._path = path
        self._workday_start = workday_start
        self._tz = zone(tz_name)
        self._sample: CsvSample | None = None
        self.plan: ImportPlan | None = None
        self.outcome: ImportOutcome | None = None
        self.setWindowTitle(f"Import {path.name}")
        self.setModal(True)
        self.resize(900, 560)

        root = QVBoxLayout(self)

        # -- file options ------------------------------------------------------
        options = QHBoxLayout()
        self.delimiter = QComboBox()
        self.delimiter.setAccessibleName("Delimiter")
        for label, value in (
            ("Semicolon ;", ";"),
            ("Comma ,", ","),
            ("Tab", "\t"),
            ("Pipe |", "|"),
        ):
            self.delimiter.addItem(label, value)
        self.has_header = QCheckBox("First row is a header")
        self.date_order = QComboBox()
        self.date_order.setAccessibleName("Date order")
        self.date_order.addItem("Date order: auto", DateOrder.AUTO.value)
        self.date_order.addItem("day/month/year", DateOrder.DMY.value)
        self.date_order.addItem("month/day/year", DateOrder.MDY.value)
        options.addWidget(self.delimiter)
        options.addWidget(self.has_header)
        options.addWidget(self.date_order)
        options.addStretch(1)
        root.addLayout(options)

        # -- mapping -----------------------------------------------------------
        box = QGroupBox("Columns")
        grid = QGridLayout(box)
        self.mapping_boxes: dict[str, QComboBox] = {}
        for i, field_name in enumerate(FIELDS):
            combo = QComboBox()
            combo.setAccessibleName(f"Column for {field_name}")
            self.mapping_boxes[field_name] = combo
            grid.addWidget(QLabel(_FIELD_LABELS[field_name]), 0, i)
            grid.addWidget(combo, 1, i)
        hint = QLabel(
            "Date is required; map a Duration column or both Start and End. Rows without a "
            "start are placed from the workday start. Durations: 1:30, 1h15, 90 (minutes), "
            "1.5 (hours)."
        )
        hint.setWordWrap(True)
        grid.addWidget(hint, 2, 0, 1, len(FIELDS))
        root.addWidget(box)

        # -- preview -----------------------------------------------------------
        self.preview = QTableWidget(0, 7)
        self.preview.setHorizontalHeaderLabels(
            ["Line", "Date", "Start", "Duration", "Client", "Type", "Note / problem"]
        )
        self.preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.preview.verticalHeader().setVisible(False)
        self.preview.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.preview, 1)

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        self.skip_duplicates = QCheckBox(
            "Skip rows that already exist (same start, duration, labels and note)"
        )
        self.skip_duplicates.setChecked(True)
        root.addWidget(self.skip_duplicates)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.import_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.import_button.setText("Import")
        self.buttons.accepted.connect(self._import)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        # -- first read --------------------------------------------------------
        self._loading = True
        self._read(None, None)
        self._loading = False
        self.delimiter.currentIndexChanged.connect(self._on_file_option_changed)
        self.has_header.toggled.connect(self._on_file_option_changed)
        self.date_order.currentIndexChanged.connect(self._on_control_changed)
        self.skip_duplicates.toggled.connect(self._on_control_changed)
        for combo in self.mapping_boxes.values():
            combo.currentIndexChanged.connect(self._on_control_changed)

    # -- reading and mapping -------------------------------------------------

    def _read(self, delimiter: str | None, has_header: bool | None) -> None:
        try:
            sample = self._importer.read(self._path, delimiter, has_header=has_header)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Import", f"Cannot read {self._path.name}:\n{exc}")
            self._sample = None
            self.import_button.setEnabled(False)
            return
        self._sample = sample
        was_loading = self._loading
        self._loading = True
        pos = self.delimiter.findData(sample.delimiter)
        if pos < 0:
            self.delimiter.addItem(repr(sample.delimiter), sample.delimiter)
            pos = self.delimiter.count() - 1
        self.delimiter.setCurrentIndex(pos)
        self.has_header.setChecked(sample.has_header)
        guess = guess_mapping(sample.header) if sample.has_header else ColumnMapping()
        for field_name, combo in self.mapping_boxes.items():
            combo.clear()
            combo.addItem("—", None)
            for i, name in enumerate(sample.header):
                combo.addItem(name or f"Column {i + 1}", i)
            idx = guess.index(field_name)
            combo.setCurrentIndex(0 if idx is None else idx + 1)
        self._loading = was_loading
        self._reparse()

    def _on_file_option_changed(self, *_: object) -> None:
        if self._loading:
            return
        self._read(str(self.delimiter.currentData()), self.has_header.isChecked())

    def _on_control_changed(self, *_: object) -> None:
        if not self._loading:
            self._reparse()

    def mapping(self) -> ColumnMapping:
        values = {}
        for field_name, combo in self.mapping_boxes.items():
            data = combo.currentData()
            values[field_name] = None if data is None else int(data)
        return ColumnMapping(**values)

    def set_mapping(self, mapping: ColumnMapping) -> None:
        self._loading = True
        for field_name, combo in self.mapping_boxes.items():
            idx = mapping.index(field_name)
            combo.setCurrentIndex(0 if idx is None else combo.findData(idx))
        self._loading = False
        self._reparse()

    # -- preview -------------------------------------------------------------

    def _reparse(self) -> None:
        if self._sample is None:
            return
        order = DateOrder(str(self.date_order.currentData()))
        self.plan = self._importer.plan(
            self._sample, self.mapping(), date_order=order, workday_start=self._workday_start
        )
        self._fill_preview(self.plan)

    def _fill_preview(self, plan: ImportPlan) -> None:
        problems = {e.line: e.message for e in plan.parsed.errors}
        shown: list[tuple[int, list[str], str]] = []  # line, cells, kind
        for row in plan.parsed.rows:
            local = row.started_at_utc.astimezone(self._tz)
            kind = "duplicate" if row.line in plan.duplicate_lines else "ok"
            shown.append(
                (
                    row.line,
                    [
                        local.strftime("%Y-%m-%d"),
                        ("~" if row.placed else "") + local.strftime("%H:%M"),
                        format_hm(row.duration_seconds),
                        row.client or "",
                        row.type or "",
                        row.note or "",
                    ],
                    kind,
                )
            )
        for line, message in problems.items():
            shown.append((line, ["", "", "", "", "", message], "error"))
        shown.sort(key=lambda t: t[0])
        shown = shown[:_PREVIEW_LIMIT]

        self.preview.setRowCount(len(shown))
        for r, (line, cells, kind) in enumerate(shown):
            items = [QTableWidgetItem(str(line) if line else "")] + [
                QTableWidgetItem(c) for c in cells
            ]
            for item in items:
                if kind == "error":
                    item.setForeground(QColor("#c0392b"))
                elif kind == "duplicate":
                    item.setForeground(QColor("#7f8c8d"))
                    item.setToolTip("Already in the log")
                self.preview.setItem(r, items.index(item), item)
        self.preview.resizeColumnsToContents()

        ready = plan.ready if self.skip_duplicates.isChecked() else list(plan.parsed.rows)
        n_dup = len(plan.duplicates)
        n_err = len(plan.parsed.errors)
        parts = [f"{len(ready)} rows will be imported"]
        if n_dup and self.skip_duplicates.isChecked():
            parts.append(f"{n_dup} already exist and are skipped")
        if n_err:
            parts.append(f"{n_err} cannot be read and are skipped")
        if len(plan.parsed.rows) + len(plan.parsed.errors) > _PREVIEW_LIMIT:
            parts.append(f"(preview shows the first {_PREVIEW_LIMIT})")
        if "~" in "".join(c[1][1] for c in shown):
            parts.append("~ = start time placed, none in the file")
        self.summary.setText("; ".join(parts) + ".")
        self.import_button.setEnabled(bool(ready))

    # -- commit --------------------------------------------------------------

    def _import(self) -> None:
        if self.plan is None:
            return
        try:
            self.outcome = self._importer.commit(
                self.plan, skip_duplicates=self.skip_duplicates.isChecked()
            )
        except Exception as exc:  # noqa: BLE001 - shown to the user, nothing was written
            QMessageBox.critical(self, "Import failed", f"Nothing was imported.\n\n{exc}")
            return
        self.accept()
