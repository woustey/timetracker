"""ImportService (FR-805): preview with duplicate detection, one-transaction commit, labels."""

from __future__ import annotations

from pathlib import Path

import pytest

from timetracker.core.clock import FakeClock
from timetracker.core.csv_import import ColumnMapping, guess_mapping
from timetracker.core.models import Dimension, RecordMethod
from timetracker.data.entry_repo import EntryRepo
from timetracker.services.entry_service import EntryService
from timetracker.services.import_service import ImportService
from timetracker.services.label_service import LabelService

CSV = (
    "Date,Start,End,Client,Category,Note\n"
    "2026-09-14,09:00,10:30,Nike,Work,kick-off\n"
    "2026-09-14,11:00,11:15,nike ,Phone,\n"
    "2026-09-15,09:00,09:45,ASICS,Work,\n"
    "nonsense,09:00,09:45,ASICS,Work,\n"
)


@pytest.fixture
def importer(
    qapp, clock: FakeClock, entries: EntryRepo, entry_service: EntryService, labels: LabelService
) -> ImportService:  # type: ignore[no-untyped-def]
    return ImportService(clock, entries, entry_service, labels)


def test_plan_then_commit_creates_entries_and_labels_once(
    importer: ImportService,
    entries: EntryRepo,
    entry_service: EntryService,
    labels: LabelService,
    tmp_path: Path,
    qtbot,
) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "old-tool.csv"
    path.write_text(CSV, encoding="utf-8")
    sample = importer.read(path)
    mapping = guess_mapping(sample.header)
    assert mapping == ColumnMapping(date=0, start=1, end=2, client=3, type=4, note=5)
    plan = importer.plan(sample, mapping)
    assert len(plan.parsed.rows) == 3 and len(plan.parsed.errors) == 1
    assert plan.duplicate_lines == frozenset()
    assert labels.find(Dimension.CLIENT, "Nike") is None  # preview creates nothing

    with qtbot.waitSignal(entry_service.entries_changed, timeout=1000) as blocker:
        outcome = importer.commit(plan)
    assert len(outcome.created) == 3
    assert len(blocker.args[0]) == 3  # announced once, with every uuid
    assert (outcome.skipped_duplicates, outcome.skipped_errors) == (0, 1)
    assert outcome.new_clients == ["ASICS", "Nike"]
    assert outcome.new_types == ["Phone", "Work"]
    nike = labels.find(Dimension.CLIENT, "Nike")
    assert nike is not None
    first, second, third = outcome.created
    assert first.record_method is RecordMethod.MANUAL
    assert (first.duration_seconds, first.client_id, first.note) == (5400, nike.id, "kick-off")
    assert second.client_id == nike.id  # "nike " normalised onto the same label
    assert entries.count() == 3

    # Importing the same file again: every good row is a duplicate and is skipped.
    plan2 = importer.plan(importer.read(path), mapping)
    assert len(plan2.duplicate_lines) == 3 and plan2.ready == []
    outcome2 = importer.commit(plan2)
    assert outcome2.created == [] and outcome2.skipped_duplicates == 3
    assert entries.count() == 3
    forced = importer.commit(plan2, skip_duplicates=False)
    assert len(forced.created) == 3 and entries.count() == 6


def test_commit_is_all_or_nothing(
    importer: ImportService, entries: EntryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "x.csv"
    path.write_text(CSV, encoding="utf-8")
    sample = importer.read(path)
    plan = importer.plan(sample, guess_mapping(sample.header))
    original = EntryRepo._insert_row  # noqa: SLF001
    calls = {"n": 0}

    def flaky(self: EntryRepo, new: object) -> int:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("disk full")
        return original(self, new)  # type: ignore[arg-type]

    monkeypatch.setattr(EntryRepo, "_insert_row", flaky)
    with pytest.raises(RuntimeError):
        importer.commit(plan)
    monkeypatch.undo()
    assert entries.count() == 0
    assert len(importer.commit(plan).created) == 3  # the connection is usable afterwards
