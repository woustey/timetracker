"""EntryService: Add Time commits and undo (FR-310, FR-311, FR-314)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from timetracker.core.clock import FakeClock
from timetracker.core.models import RecordMethod
from timetracker.data.entry_repo import EntryRepo
from timetracker.data.label_repo import LabelRepo
from timetracker.services.entry_service import EntryService


def test_add_quick_anchors_to_now_and_marks_quickadd(
    entry_service: EntryService, entries: EntryRepo, clients: LabelRepo, clock: FakeClock, qtbot
) -> None:  # type: ignore[no-untyped-def]
    nike = clients.create("Nike")
    clock.set_now(datetime(2026, 9, 11, 12, 37, 42, tzinfo=UTC))
    with qtbot.waitSignal(entry_service.entries_changed, timeout=1000) as blocker:
        entry = entry_service.add_quick(1800, nike.id, None, "  emails  ")
    assert blocker.args == [[entry.uuid]]
    assert entry.record_method is RecordMethod.QUICKADD
    assert entry.duration_seconds == 1800
    assert entry.ended_at_utc == datetime(2026, 9, 11, 12, 37, tzinfo=UTC)
    assert entry.started_at_utc == entry.ended_at_utc - timedelta(minutes=30)
    assert entry.local_date == date(2026, 9, 11)
    assert entry.note == "emails"
    assert entry.client_id == nike.id
    assert entry.type_id is None
    assert clients.get(nike.id).last_used_at == clock.now_utc()
    assert entry_service.last_added == entry
    assert entry_service.today_total_seconds() == 1800
    assert entry_service.default_labels() == (nike.id, None)


def test_add_quick_past_date_uses_workday_start(entry_service: EntryService) -> None:
    from zoneinfo import ZoneInfo

    entry = entry_service.add_quick(3600, None, None, None, target_date=date(2026, 9, 8))
    local = entry.started_at_utc.astimezone(ZoneInfo("Europe/Brussels"))
    assert local == datetime(2026, 9, 8, 9, 0, tzinfo=ZoneInfo("Europe/Brussels"))
    assert entry.local_date == date(2026, 9, 8)


def test_unlabelled_entries_are_allowed(entry_service: EntryService) -> None:
    """P5: the service never blocks on labels; the matrix's Add button is the gate."""
    entry = entry_service.add_quick(60, None, None, None)
    assert entry.client_id is None and entry.type_id is None


def test_undo_last_removes_only_the_last_commit(
    entry_service: EntryService, entries: EntryRepo, qtbot
) -> None:  # type: ignore[no-untyped-def]
    first = entry_service.add_quick(600, None, None, "first")
    second = entry_service.add_quick(900, None, None, "second")
    with qtbot.waitSignal(entry_service.entries_changed, timeout=1000) as blocker:
        removed = entry_service.undo_last()
    assert removed == second
    assert blocker.args == [[second.uuid]]
    assert [e.id for e in entries.query()] == [first.id]
    assert entry_service.undo_last() is None  # only one level (FR-311)
    assert entries.count() == 1


def test_undo_after_external_delete_is_a_noop(
    entry_service: EntryService, entries: EntryRepo
) -> None:
    entry = entry_service.add_quick(600, None, None, None)
    entries.delete(entry.id)
    assert entry_service.undo_last() is None
