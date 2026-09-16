"""CSV import (FR-805, v1.1): preview a mapped file, then write it in one transaction.

``core/csv_import.py`` does the reading and parsing; this resolves label
names to ids (creating labels through ``LabelService`` so the usual
normalisation and the ``labels_changed`` signal apply), flags rows that
already exist, and hands the batch to ``EntryService.add_many`` so the log
refreshes once. Imported rows carry the ``MANUAL`` record method: they are
data the user typed somewhere else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from pathlib import Path

from PySide6.QtCore import QObject

from timetracker.core.clock import Clock
from timetracker.core.csv_import import (
    ColumnMapping,
    CsvSample,
    DateOrder,
    ParsedRow,
    ParseResult,
    parse_rows,
    read_sample,
)
from timetracker.core.models import Dimension, Entry, NewEntry, RecordMethod
from timetracker.data.entry_repo import EntryRepo
from timetracker.services.entry_service import EntryService
from timetracker.services.label_service import LabelService


@dataclass(frozen=True, slots=True)
class ImportPlan:
    sample: CsvSample
    mapping: ColumnMapping
    parsed: ParseResult
    duplicate_lines: frozenset[int] = field(default_factory=frozenset)

    @property
    def ready(self) -> list[ParsedRow]:
        return [r for r in self.parsed.rows if r.line not in self.duplicate_lines]

    @property
    def duplicates(self) -> list[ParsedRow]:
        return [r for r in self.parsed.rows if r.line in self.duplicate_lines]


@dataclass(frozen=True, slots=True)
class ImportOutcome:
    created: list[Entry]
    skipped_duplicates: int
    skipped_errors: int
    new_clients: list[str]
    new_types: list[str]


class ImportService(QObject):
    def __init__(
        self,
        clock: Clock,
        repo: EntryRepo,
        entries: EntryService,
        labels: LabelService,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._clock = clock
        self._repo = repo
        self._entries = entries
        self._labels = labels

    # -- preview -------------------------------------------------------------

    def read(
        self, path: Path, delimiter: str | None = None, *, has_header: bool | None = None
    ) -> CsvSample:
        return read_sample(path, delimiter, has_header=has_header)

    def plan(
        self,
        sample: CsvSample,
        mapping: ColumnMapping,
        *,
        date_order: DateOrder = DateOrder.AUTO,
        workday_start: time = time(9, 0),
    ) -> ImportPlan:
        parsed = parse_rows(
            sample.rows,
            mapping,
            tz_name=self._clock.tz_name(),
            date_order=date_order,
            workday_start=workday_start,
            first_line=2 if sample.has_header else 1,
        )
        duplicates = frozenset(
            row.line
            for row in parsed.rows
            if self._repo.exists_like(self._to_new(row, resolve=False))
        )
        return ImportPlan(sample, mapping, parsed, duplicates)

    # -- commit --------------------------------------------------------------

    def commit(self, plan: ImportPlan, *, skip_duplicates: bool = True) -> ImportOutcome:
        rows = plan.ready if skip_duplicates else list(plan.parsed.rows)
        before_c = {lab.name for lab in self._labels.list_all(Dimension.CLIENT)}
        before_t = {lab.name for lab in self._labels.list_all(Dimension.TYPE)}
        news = [self._to_new(row, resolve=True) for row in rows]
        created = self._entries.add_many(news)
        after_c = {lab.name for lab in self._labels.list_all(Dimension.CLIENT)}
        after_t = {lab.name for lab in self._labels.list_all(Dimension.TYPE)}
        return ImportOutcome(
            created=created,
            skipped_duplicates=len(plan.parsed.rows) - len(rows),
            skipped_errors=len(plan.parsed.errors),
            new_clients=sorted(after_c - before_c),
            new_types=sorted(after_t - before_t),
        )

    # -- internals -----------------------------------------------------------

    def _to_new(self, row: ParsedRow, *, resolve: bool) -> NewEntry:
        client_id = self._label_id(Dimension.CLIENT, row.client, create=resolve)
        type_id = self._label_id(Dimension.TYPE, row.type, create=resolve)
        return NewEntry(
            started_at_utc=row.started_at_utc,
            ended_at_utc=row.ended_at_utc,
            tz_name=self._clock.tz_name(),
            duration_seconds=row.duration_seconds,
            record_method=RecordMethod.MANUAL,
            client_id=client_id,
            type_id=type_id,
            note=row.note,
        )

    def _label_id(self, dimension: Dimension, name: str | None, *, create: bool) -> int | None:
        if not name:
            return None
        if create:
            return self._labels.get_or_create(dimension, name).id
        found = self._labels.find(dimension, name)
        return found.id if found is not None else None
