"""``EntryTableModel``: a ``QAbstractTableModel`` over SQL-backed, paged rows (PRD-02 §8.3).

Filtering and sorting happen in SQL (``EntryRepo.export_rows``) rather than in
a proxy model: a Python ``filterAcceptsRow``/``lessThan`` over 50 000 rows
cannot meet NFR-04, ``WHERE``/``ORDER BY`` on the indexed table can. Rows are
fetched in pages of :data:`PAGE_SIZE` through ``fetchMore``; totals come from
SQL aggregates, never from the loaded page.

Edits go through ``EntryService`` (edit policy lives there); the row is then
replaced in place. Flags (edited, discrepancy, overlap) are painted by the
Flags column as glyphs *and* exposed as accessible descriptions (PRD-01 §9.5).

The overlap pass (FR-508) must look at every row in the filter, which costs
~150 ms at 50 000 rows. It runs right *after* the reset has painted (a
zero-timer), so filtering and sorting stay inside the NFR-04 budget and the
⧉ glyphs appear a beat later.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime, time
from enum import IntEnum
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    QTimer,
)

from timetracker.core.consistency import has_discrepancy
from timetracker.core.duration import format_hm, format_hms
from timetracker.core.models import Dimension, Entry
from timetracker.core.timeutil import zone
from timetracker.data.entry_repo import EntryFilter, EntryRepo, ExportRow, Summary
from timetracker.services.entry_service import EntryService
from timetracker.services.label_service import LabelService
from timetracker.ui.formatting import fmt_time

PAGE_SIZE = 1_000
GLYPH_EDITED = "✎"
GLYPH_DISCREPANCY = "⚠"
GLYPH_OVERLAP = "⧉"


class Col(IntEnum):
    FLAGS = 0
    DATE = 1
    START = 2
    END = 3
    DURATION = 4
    CLIENT = 5
    TYPE = 6
    METHOD = 7
    NOTE = 8


HEADERS = {
    Col.FLAGS: "",
    Col.DATE: "Date",
    Col.START: "Start",
    Col.END: "End",
    Col.DURATION: "Total",
    Col.CLIENT: "Client",
    Col.TYPE: "Type",
    Col.METHOD: "Method",
    Col.NOTE: "Note",
}

SORT_KEYS = {
    Col.DATE: "local_date",
    Col.START: "started_at_utc",
    Col.END: "ended_at_utc",
    Col.DURATION: "duration_seconds",
    Col.CLIENT: "client",
    Col.TYPE: "type",
    Col.METHOD: "record_method",
    Col.NOTE: "note",
}

EDITABLE = {Col.DATE, Col.START, Col.END, Col.DURATION, Col.CLIENT, Col.TYPE, Col.NOTE}
_ROOT = QModelIndex()  # module-level singleton default for the Qt parent argument


class EntryTableModel(QAbstractTableModel):
    def __init__(
        self,
        repo: EntryRepo,
        entries: EntryService,
        labels: LabelService,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._repo = repo
        self._entries = entries
        self._labels = labels
        self._rows: list[ExportRow] = []
        self._filter = EntryFilter()
        self._sort_col = Col.START
        self._desc = True
        self._total_count = 0
        self._summary = Summary(0, 0, [], [])
        self._overlaps: set[int] = set()
        self._overlap_generation = 0

    # -- query -----------------------------------------------------------------

    @property
    def filter(self) -> EntryFilter:
        return self._filter

    @property
    def sort_column(self) -> Col:
        return self._sort_col

    @property
    def sort_descending(self) -> bool:
        return self._desc

    @property
    def total_count(self) -> int:
        return self._total_count

    @property
    def summary(self) -> Summary:
        """Count, total and subtotals for the current filter (one grouped scan, FR-504)."""
        return self._summary

    def set_query(
        self, flt: EntryFilter | None = None, sort_col: Col | None = None, desc: bool | None = None
    ) -> None:
        if flt is not None:
            self._filter = flt
        if sort_col is not None and sort_col in SORT_KEYS:
            self._sort_col = sort_col
        if desc is not None:
            self._desc = desc
        self.beginResetModel()
        self._rows = []
        self._summary = self._repo.summary(self._filter)
        self._total_count = self._summary.count
        self._rows = self._page(0)
        self.endResetModel()
        self._schedule_overlaps()

    def refresh(self) -> None:
        """Reload the pages currently loaded (after an edit, delete or add elsewhere)."""
        loaded = max(len(self._rows), PAGE_SIZE)
        self.beginResetModel()
        self._summary = self._repo.summary(self._filter)
        self._total_count = self._summary.count
        self._rows = self._repo.export_rows(
            self._filter,
            newest_first=self._desc,
            limit=loaded,
            offset=0,
            sort_by=SORT_KEYS[self._sort_col],
        )
        self.endResetModel()
        self._schedule_overlaps()

    # -- overlap flags (FR-508), computed off the critical path ----------------

    def _schedule_overlaps(self) -> None:
        self._overlap_generation += 1
        generation = self._overlap_generation
        QTimer.singleShot(0, lambda: self._compute_overlaps(generation))

    def cancel_pending(self) -> None:
        """Invalidate deferred work (the window is closing)."""
        self._overlap_generation += 1

    def _compute_overlaps(self, generation: int) -> None:
        if generation != self._overlap_generation:
            return  # superseded by a newer query, or cancelled
        try:
            self._overlaps = self._repo.overlapping_ids(self._filter)
        except sqlite3.ProgrammingError:
            return  # connection already closed (shutdown race); nothing to paint
        if self._rows:
            self.dataChanged.emit(
                self.index(0, Col.FLAGS), self.index(len(self._rows) - 1, Col.FLAGS)
            )

    def compute_overlaps_now(self) -> None:
        """Synchronous variant for tests and for callers that need the flags immediately."""
        self._overlap_generation += 1
        self._compute_overlaps(self._overlap_generation)

    @property
    def overlapping_ids(self) -> set[int]:
        return set(self._overlaps)

    def _page(self, offset: int) -> list[ExportRow]:
        return self._repo.export_rows(
            self._filter,
            newest_first=self._desc,
            limit=PAGE_SIZE,
            offset=offset,
            sort_by=SORT_KEYS[self._sort_col],
        )

    # -- paging ----------------------------------------------------------------

    def canFetchMore(self, parent: QModelIndex | QPersistentModelIndex = _ROOT) -> bool:  # noqa: N802
        return not parent.isValid() and len(self._rows) < self._total_count

    def fetchMore(self, parent: QModelIndex | QPersistentModelIndex = _ROOT) -> None:  # noqa: N802
        if parent.isValid():
            return
        more = self._page(len(self._rows))
        if not more:
            self._total_count = len(self._rows)
            return
        self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows) + len(more) - 1)
        self._rows.extend(more)
        self.endInsertRows()

    def fetch_all(self) -> None:
        while self.canFetchMore():
            self.fetchMore()

    # -- structure -------------------------------------------------------------

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(Col)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:  # noqa: N802
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return HEADERS[Col(section)]
        return None

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.isValid() and Col(index.column()) in EDITABLE:
            base |= Qt.ItemFlag.ItemIsEditable
        return base

    # -- access ----------------------------------------------------------------

    def entry_at(self, row: int) -> Entry:
        return self._rows[row].entry

    def row_of(self, entry_id: int) -> int:
        for i, r in enumerate(self._rows):
            if r.entry.id == entry_id:
                return i
        return -1

    def row_flags(self, row: int) -> list[str]:
        e = self._rows[row].entry
        out: list[str] = []
        if e.is_edited:
            out.append("edited")
        if has_discrepancy(e):
            out.append("timestamps disagree with the duration")
        if e.id in self._overlaps:
            out.append("overlaps another entry")
        return out

    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        e = row.entry
        col = Col(index.column())
        tz = zone(e.tz_name)

        if role == Qt.ItemDataRole.DisplayRole:
            if col is Col.FLAGS:
                glyphs = []
                if e.is_edited:
                    glyphs.append(GLYPH_EDITED)
                if has_discrepancy(e):
                    glyphs.append(GLYPH_DISCREPANCY)
                if e.id in self._overlaps:
                    glyphs.append(GLYPH_OVERLAP)
                return " ".join(glyphs)
            if col is Col.DATE:
                return e.local_date.strftime("%a %d %b %Y")
            if col is Col.START:
                return fmt_time(e.started_at_utc.astimezone(tz))
            if col is Col.END:
                return fmt_time(e.ended_at_utc.astimezone(tz))
            if col is Col.DURATION:
                return format_hm(e.duration_seconds)
            if col is Col.CLIENT:
                return row.client_name or ""
            if col is Col.TYPE:
                return row.type_name or ""
            if col is Col.METHOD:
                return e.record_method.display
            if col is Col.NOTE:
                return (e.note or "").replace("\n", " ")
        elif role == Qt.ItemDataRole.EditRole:
            if col is Col.DATE:
                return e.local_date
            if col is Col.START:
                return e.started_at_utc.astimezone(tz).time().replace(second=0, microsecond=0)
            if col is Col.END:
                return e.ended_at_utc.astimezone(tz).time().replace(second=0, microsecond=0)
            if col is Col.DURATION:
                return e.duration_seconds
            if col is Col.CLIENT:
                return e.client_id
            if col is Col.TYPE:
                return e.type_id
            if col is Col.NOTE:
                return e.note or ""
        elif role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleDescriptionRole):
            if col is Col.FLAGS:
                return "; ".join(self.row_flags(index.row())) or None
            if col is Col.DURATION:
                text = format_hms(e.duration_seconds)
                if e.paused_seconds:
                    text += f" (paused {format_hms(e.paused_seconds)})"
                return text
            if col is Col.NOTE and e.note:
                return e.note
        elif role == Qt.ItemDataRole.TextAlignmentRole and col in (
            Col.START,
            Col.END,
            Col.DURATION,
        ):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def setData(
        self,
        index: QModelIndex | QPersistentModelIndex,
        value: Any,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:  # noqa: N802
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False
        col = Col(index.column())
        if col not in EDITABLE:
            return False
        e = self._rows[index.row()].entry
        tz = zone(e.tz_name)
        try:
            if col is Col.DURATION:
                seconds = int(value)
                if seconds == e.duration_seconds:
                    return False
                updated = self._entries.update(e.id, duration_seconds=seconds)
            elif col is Col.DATE:
                assert isinstance(value, date)
                if value == e.local_date:
                    return False
                updated = self._entries.move_to_date(e.id, value)
            elif col is Col.START:
                assert isinstance(value, time)
                local = e.started_at_utc.astimezone(tz)
                new_start = datetime.combine(local.date(), value, tzinfo=tz).astimezone(UTC)
                if new_start == e.started_at_utc:
                    return False
                updated = self._entries.update(e.id, started_at_utc=new_start)
            elif col is Col.END:
                assert isinstance(value, time)
                local = e.ended_at_utc.astimezone(tz)
                new_end = datetime.combine(local.date(), value, tzinfo=tz).astimezone(UTC)
                if new_end == e.ended_at_utc:
                    return False
                updated = self._entries.update(e.id, ended_at_utc=new_end)
            elif col is Col.CLIENT:
                client_id = None if value is None else int(value)
                if client_id == e.client_id:
                    return False
                updated = self._entries.update(e.id, client_id=client_id)
            elif col is Col.TYPE:
                type_id = None if value is None else int(value)
                if type_id == e.type_id:
                    return False
                updated = self._entries.update(e.id, type_id=type_id)
            else:  # NOTE
                note = str(value).strip() or None
                if note == e.note:
                    return False
                updated = self._entries.update(e.id, note=note)
        except (ValueError, TypeError):
            return False
        self._replace_row(index.row(), updated)
        return True

    def _replace_row(self, row: int, updated: Entry) -> None:
        names = (
            self._labels.get(Dimension.CLIENT, updated.client_id).name
            if updated.client_id is not None
            else None,
            self._labels.get(Dimension.TYPE, updated.type_id).name
            if updated.type_id is not None
            else None,
        )
        self._rows[row] = replace(
            self._rows[row], entry=updated, client_name=names[0], type_name=names[1]
        )
        self.dataChanged.emit(self.index(row, 0), self.index(row, len(Col) - 1))
        self._schedule_overlaps()
