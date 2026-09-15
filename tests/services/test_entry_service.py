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


# -- M5: edits, manual add, delete/undo ---------------------------------------------


def test_edit_policy_duration_moves_end(entry_service: EntryService, clock: FakeClock) -> None:
    e = entry_service.add_quick(1800, None, None, None)
    edited = entry_service.update(e.id, duration_seconds=5400)
    assert edited.is_edited
    assert edited.duration_seconds == 5400
    assert edited.started_at_utc == e.started_at_utc
    assert edited.ended_at_utc == e.started_at_utc + timedelta(seconds=5400)


def test_edit_policy_start_shifts_both_end_moves_only_end(
    entry_service: EntryService, clock: FakeClock
) -> None:
    e = entry_service.add_quick(1800, None, None, None)
    new_start = e.started_at_utc - timedelta(days=3, hours=2)
    moved = entry_service.update(e.id, started_at_utc=new_start)
    assert moved.started_at_utc == new_start
    assert moved.ended_at_utc == new_start + timedelta(seconds=1800)
    assert moved.duration_seconds == 1800
    assert moved.local_date == (e.local_date - timedelta(days=3))

    later_end = moved.ended_at_utc + timedelta(minutes=10)
    stretched = entry_service.update(e.id, ended_at_utc=later_end)
    assert stretched.started_at_utc == new_start
    assert stretched.ended_at_utc == later_end
    assert stretched.duration_seconds == 1800  # never derived from the anchors


def test_move_to_date_keeps_time_of_day(entry_service: EntryService, clock: FakeClock) -> None:
    from zoneinfo import ZoneInfo

    clock.set_now(datetime(2026, 9, 11, 12, 37, tzinfo=UTC))  # 14:37 Brussels, Friday
    e = entry_service.add_quick(1800, None, None, None)  # 14:07–14:37 local
    moved = entry_service.move_to_date(e.id, date(2026, 9, 8))  # Tuesday
    local = moved.started_at_utc.astimezone(ZoneInfo("Europe/Brussels"))
    assert local == datetime(2026, 9, 8, 14, 7, tzinfo=ZoneInfo("Europe/Brussels"))
    assert moved.local_date == date(2026, 9, 8)
    assert moved.duration_seconds == 1800


def test_add_manual(entry_service: EntryService, clients: LabelRepo) -> None:
    from datetime import time
    from zoneinfo import ZoneInfo

    asics = clients.create("ASICS")
    e = entry_service.add_manual(date(2026, 9, 8), time(14, 0), 5400, asics.id, None, " gap ")
    tz = ZoneInfo("Europe/Brussels")
    assert e.started_at_utc.astimezone(tz) == datetime(2026, 9, 8, 14, 0, tzinfo=tz)
    assert e.ended_at_utc.astimezone(tz) == datetime(2026, 9, 8, 15, 30, tzinfo=tz)
    assert e.duration_seconds == 5400
    assert e.record_method is RecordMethod.MANUAL
    assert e.client_id == asics.id
    assert e.note == "gap"
    assert e.local_date == date(2026, 9, 8)


def test_delete_and_undo_stack(entry_service: EntryService, entries: EntryRepo, qtbot) -> None:  # type: ignore[no-untyped-def]
    a = entry_service.add_quick(60, None, None, "a")
    b = entry_service.add_quick(60, None, None, "b")
    c = entry_service.add_quick(60, None, None, "c")
    assert not entry_service.can_undo_delete
    with qtbot.waitSignal(entry_service.entries_changed, timeout=1000) as blocker:
        removed = entry_service.delete([a.id, b.id])
    assert {e.note for e in removed} == {"a", "b"}
    assert sorted(blocker.args[0]) == sorted([a.uuid, b.uuid])
    assert entries.count() == 1
    entry_service.delete([c.id])
    assert entries.count() == 0
    assert entry_service.can_undo_delete

    assert [e.note for e in entry_service.undo_delete()] == ["c"]
    assert entries.count() == 1
    restored = entry_service.undo_delete()
    assert {e.note for e in restored} == {"a", "b"}
    assert {e.uuid for e in restored} == {a.uuid, b.uuid}
    assert entries.count() == 3
    assert entry_service.undo_delete() == []
    assert not entry_service.can_undo_delete


def test_deleting_last_added_clears_toast_undo(entry_service: EntryService) -> None:
    e = entry_service.add_quick(60, None, None, None)
    entry_service.delete([e.id])
    assert entry_service.undo_last() is None  # the FR-311 undo cannot resurrect a deleted row
