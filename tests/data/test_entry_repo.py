"""EntryRepo: CRUD, paging, totals by SQL, and the duration-is-authoritative rule."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta

import pytest

from timetracker.core.clock import FakeClock
from timetracker.core.errors import NotFoundError, ValidationError
from timetracker.core.models import NewEntry, RecordMethod
from timetracker.data.entry_repo import EntryFilter, EntryRepo
from timetracker.data.label_repo import LabelRepo

BRU = "Europe/Brussels"


def _new(
    start: datetime,
    minutes: int,
    *,
    method: RecordMethod = RecordMethod.STOPWATCH,
    tz: str = BRU,
    **kw: object,
) -> NewEntry:
    return NewEntry(
        started_at_utc=start,
        ended_at_utc=start + timedelta(minutes=minutes),
        tz_name=tz,
        duration_seconds=minutes * 60,
        record_method=method,
        **kw,  # type: ignore[arg-type]
    )


def test_insert_and_get(entries: EntryRepo, clock: FakeClock) -> None:
    t0 = datetime(2026, 9, 11, 7, 0, tzinfo=UTC)
    e = entries.insert(_new(t0, 30, note="call"))
    assert e.id > 0
    assert len(e.uuid) == 36
    assert e.started_at_utc == t0
    assert e.ended_at_utc == t0 + timedelta(minutes=30)
    assert e.tz_name == BRU
    assert e.local_date == date(2026, 9, 11)
    assert e.duration_seconds == 1800
    assert e.paused_seconds == 0
    assert e.client_id is None and e.type_id is None
    assert e.note == "call"
    assert e.record_method is RecordMethod.STOPWATCH
    assert not e.is_edited
    assert e.created_at == e.modified_at == clock.now_utc()
    assert entries.get(e.id) == e
    assert entries.get_by_uuid(e.uuid) == e


def test_supplied_uuid_is_kept_and_unique(entries: EntryRepo) -> None:
    t0 = datetime(2026, 9, 11, 7, 0, tzinfo=UTC)
    e = entries.insert(_new(t0, 1, uuid="fixed-uuid"))
    assert e.uuid == "fixed-uuid"
    with pytest.raises(sqlite3.IntegrityError):
        entries.insert(_new(t0, 1, uuid="fixed-uuid"))


def test_duration_is_stored_not_derived(entries: EntryRepo) -> None:
    """FR-208 / §4.2: the timestamps may disagree with the duration; the duration wins."""
    t0 = datetime(2026, 9, 11, 7, 0, tzinfo=UTC)
    new = NewEntry(t0, t0 + timedelta(hours=2), BRU, 600, RecordMethod.STOPWATCH)
    e = entries.insert(new)
    assert e.duration_seconds == 600
    assert (e.ended_at_utc - e.started_at_utc).total_seconds() == 7200
    assert entries.total_seconds() == 600


def test_local_date_follows_tz_not_utc(entries: EntryRepo) -> None:
    # 22:30 UTC on 1 July is 00:30 on 2 July in Brussels.
    t0 = datetime(2026, 7, 1, 22, 30, tzinfo=UTC)
    e = entries.insert(_new(t0, 10))
    assert e.local_date == date(2026, 7, 2)
    assert entries.list_for_date(date(2026, 7, 2)) == [e]
    assert entries.list_for_date(date(2026, 7, 1)) == []


def test_constraints(entries: EntryRepo, conn: sqlite3.Connection) -> None:
    t0 = datetime(2026, 9, 11, 7, 0, tzinfo=UTC)
    with pytest.raises(ValidationError):
        entries.insert(NewEntry(t0, t0, BRU, -1, RecordMethod.STOPWATCH))
    # The CHECKs hold even if validation is bypassed.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO entry (uuid, started_at_utc, ended_at_utc, tz_name, local_date, "
            "duration_seconds, record_method, created_at, modified_at) "
            "VALUES ('u1', 'x', 'x', 'UTC', '2026-01-01', -5, 'STOPWATCH', 'x', 'x')"
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO entry (uuid, started_at_utc, ended_at_utc, tz_name, local_date, "
            "duration_seconds, record_method, created_at, modified_at) "
            "VALUES ('u2', 'x', 'x', 'UTC', '2026-01-01', 5, 'TELEPATHY', 'x', 'x')"
        )
    with pytest.raises(sqlite3.IntegrityError):  # FK to a client that does not exist
        entries.insert(_new(t0, 1, client_id=12345))


def test_query_order_paging_and_filters(
    entries: EntryRepo, clients: LabelRepo, types: LabelRepo
) -> None:
    nike = clients.create("Nike")
    adidas = clients.create("Adidas")
    email = types.create("Email/Chat")
    day1 = datetime(2026, 9, 8, 8, 0, tzinfo=UTC)
    day2 = datetime(2026, 9, 9, 8, 0, tzinfo=UTC)
    a = entries.insert(_new(day1, 10, client_id=nike.id, type_id=email.id, note="alpha"))
    b = entries.insert(_new(day1 + timedelta(hours=1), 20, client_id=adidas.id, note="beta"))
    c = entries.insert(
        _new(day2, 30, method=RecordMethod.QUICKADD, client_id=nike.id, note="100% gamma")
    )

    assert [e.id for e in entries.query()] == [c.id, b.id, a.id]
    assert [e.id for e in entries.query(newest_first=False)] == [a.id, b.id, c.id]
    assert [e.id for e in entries.query(limit=2)] == [c.id, b.id]
    assert [e.id for e in entries.query(limit=2, offset=2)] == [a.id]
    assert entries.recent(1) == [c]

    assert [e.id for e in entries.query(EntryFilter(client_id=nike.id))] == [c.id, a.id]
    assert [e.id for e in entries.query(EntryFilter(type_id=email.id))] == [a.id]
    assert [e.id for e in entries.query(EntryFilter(record_method=RecordMethod.QUICKADD))] == [c.id]
    assert [e.id for e in entries.query(EntryFilter(date_from=date(2026, 9, 9)))] == [c.id]
    assert [e.id for e in entries.query(EntryFilter(date_to=date(2026, 9, 8)))] == [b.id, a.id]
    assert [e.id for e in entries.query(EntryFilter(note_contains="ETA"))] == [b.id]
    assert [e.id for e in entries.query(EntryFilter(note_contains="100%"))] == [c.id]
    assert entries.query(EntryFilter(note_contains="%")) == [c]  # literal, not wildcard

    assert entries.count() == 3
    assert entries.count(EntryFilter(client_id=nike.id)) == 2


def test_totals_are_sql_aggregates_over_the_filter(entries: EntryRepo, clients: LabelRepo) -> None:
    nike = clients.create("Nike")
    day = datetime(2026, 9, 8, 8, 0, tzinfo=UTC)
    entries.insert(_new(day, 10, client_id=nike.id))
    entries.insert(_new(day + timedelta(hours=1), 25))
    entries.insert(_new(day + timedelta(days=1), 5, client_id=nike.id))
    assert entries.total_seconds() == 40 * 60
    assert entries.total_seconds(EntryFilter(client_id=nike.id)) == 15 * 60
    assert entries.total_seconds_for_date(date(2026, 9, 8)) == 35 * 60
    assert entries.total_seconds_for_date(date(2026, 1, 1)) == 0


def test_update_marks_edited_and_recomputes_local_date(
    entries: EntryRepo, clock: FakeClock
) -> None:
    t0 = datetime(2026, 9, 11, 7, 0, tzinfo=UTC)
    e = entries.insert(_new(t0, 30))
    clock.advance(120)
    moved = entries.update(e.id, started_at_utc=datetime(2026, 7, 1, 22, 30, tzinfo=UTC))
    assert moved.is_edited
    assert moved.local_date == date(2026, 7, 2)
    assert moved.modified_at == clock.now_utc()
    assert moved.created_at == e.created_at
    assert moved.duration_seconds == 1800  # untouched: never derived from the new timestamps

    edited = entries.update(e.id, duration_seconds=900, note="trimmed", client_id=None)
    assert edited.duration_seconds == 900
    assert edited.note == "trimmed"


def test_update_rejects_record_method_and_bad_values(entries: EntryRepo) -> None:
    t0 = datetime(2026, 9, 11, 7, 0, tzinfo=UTC)
    e = entries.insert(_new(t0, 30))
    with pytest.raises(ValidationError):
        entries.update(e.id, record_method=RecordMethod.QUICKADD)  # FR-505: never editable
    with pytest.raises(ValidationError):
        entries.update(e.id, duration_seconds=-1)
    with pytest.raises(ValidationError):
        entries.update(e.id, note="x" * 501)
    with pytest.raises(NotFoundError):
        entries.update(999, note="x")
    assert entries.update(e.id) == e  # no-op does not flag edited


def test_delete_and_restore(entries: EntryRepo) -> None:
    t0 = datetime(2026, 9, 11, 7, 0, tzinfo=UTC)
    e = entries.insert(_new(t0, 30, note="keep me"))
    removed = entries.delete(e.id)
    assert removed == e
    with pytest.raises(NotFoundError):
        entries.get(e.id)
    with pytest.raises(NotFoundError):
        entries.delete(e.id)

    back = entries.restore(removed)
    assert back.uuid == e.uuid
    assert back.note == "keep me"
    assert back.created_at == e.created_at
    assert entries.get_by_uuid(e.uuid) == back


def test_session_log_view(entries: EntryRepo, clients: LabelRepo, conn: sqlite3.Connection) -> None:
    nike = clients.create("Nike")
    t0 = datetime(2026, 9, 11, 7, 0, tzinfo=UTC)
    entries.insert(_new(t0, 30, client_id=nike.id))
    entries.insert(_new(t0 - timedelta(hours=1), 5, method=RecordMethod.QUICKADD))
    rows = conn.execute("SELECT * FROM v_session_log").fetchall()
    assert [(r["client"], r["record_method"], r["total_seconds"]) for r in rows] == [
        (None, "Add Time", 300),
        ("Nike", "Start-Stop", 1800),
    ]


# -- M5 additions ----------------------------------------------------------------


def test_sorting_in_sql_and_export_rows_join(
    entries: EntryRepo, clients: LabelRepo, types: LabelRepo
) -> None:
    nike = clients.create("Nike")
    zed = clients.create("Zed Corp")
    work = types.create("Work")
    day = datetime(2026, 9, 8, 8, 0, tzinfo=UTC)
    a = entries.insert(_new(day, 45, client_id=zed.id, type_id=work.id, note="b-note"))
    b = entries.insert(_new(day + timedelta(hours=1), 10, client_id=nike.id, note="a-note"))
    c = entries.insert(_new(day + timedelta(hours=2), 30))  # unlabelled

    by_dur = [e.id for e in entries.query(sort_by="duration_seconds", newest_first=False)]
    assert by_dur == [b.id, c.id, a.id]
    by_client = [e.id for e in entries.query(sort_by="client", newest_first=False)]
    assert by_client == [b.id, a.id, c.id]  # NULL client sorts last
    by_client_desc = [e.id for e in entries.query(sort_by="client", newest_first=True)]
    assert by_client_desc == [a.id, b.id, c.id]  # ...in both directions
    with pytest.raises(ValidationError):
        entries.query(sort_by="id; DROP TABLE entry")

    rows = entries.export_rows(newest_first=False)
    assert [(r.client_name, r.type_name) for r in rows] == [
        ("Zed Corp", "Work"),
        ("Nike", None),
        (None, None),
    ]


def test_totals_by_dimension(entries: EntryRepo, clients: LabelRepo, types: LabelRepo) -> None:
    from timetracker.core.models import Dimension

    nike = clients.create("Nike")
    work = types.create("Work")
    day = datetime(2026, 9, 8, 8, 0, tzinfo=UTC)
    entries.insert(_new(day, 10, client_id=nike.id, type_id=work.id))
    entries.insert(_new(day + timedelta(hours=1), 25, client_id=nike.id))
    entries.insert(_new(day + timedelta(hours=2), 5))
    by_client = entries.totals_by(Dimension.CLIENT)
    assert [(t.name, t.seconds, t.count) for t in by_client] == [
        ("Nike", 35 * 60, 2),
        (None, 300, 1),
    ]
    by_type = entries.totals_by(Dimension.TYPE, EntryFilter(client_id=nike.id))
    assert [(t.name, t.seconds) for t in by_type] == [(None, 25 * 60), ("Work", 10 * 60)]


def test_overlapping_ids_in_sql_matches_pure_oracle(entries: EntryRepo) -> None:
    from timetracker.core.consistency import overlapping_ids

    day = datetime(2026, 9, 8, 9, 0, tzinfo=UTC)
    a = entries.insert(_new(day, 30))
    b = entries.insert(_new(day + timedelta(minutes=20), 30))
    entries.insert(_new(day + timedelta(minutes=50), 10))  # touching, not overlapping
    d = entries.insert(_new(day + timedelta(hours=2), 30))
    e = entries.insert(_new(day + timedelta(hours=2, minutes=5), 1))
    entries.insert(_new(day + timedelta(days=1), 60))
    expected = {a.id, b.id, d.id, e.id}
    assert entries.overlapping_ids() == expected
    assert entries.overlapping_ids() == overlapping_ids(entries.query())
    assert entries.overlapping_ids(EntryFilter(date_from=date(2026, 9, 9))) == set()
