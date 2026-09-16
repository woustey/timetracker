"""TimerRepo: the singleton row and its heartbeat (FR-207)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from timetracker.core.clock import FakeClock
from timetracker.core.models import RunningTimer
from timetracker.data.timer_repo import TimerRepo


def _timer(start: datetime, **kw: object) -> RunningTimer:
    base: dict[str, object] = dict(
        started_at_utc=start,
        tz_name="Europe/Brussels",
        accrued_seconds=0,
        paused_since_utc=None,
        paused_seconds=0,
        client_id=None,
        type_id=None,
        note=None,
        heartbeat_at_utc=start,
        heartbeat_accrued_sec=0,
    )
    base.update(kw)
    return RunningTimer(**base)  # type: ignore[arg-type]


def test_empty_by_default(timer: TimerRepo) -> None:
    assert timer.get() is None
    assert timer.heartbeat(10, datetime(2026, 9, 11, tzinfo=UTC)) is False


def test_save_get_round_trip(timer: TimerRepo, clock: FakeClock) -> None:
    t = _timer(clock.now_utc(), note="drafting", accrued_seconds=5, heartbeat_accrued_sec=5)
    timer.save(t)
    assert timer.get() == t
    assert not t.is_paused


def test_save_replaces_the_singleton(
    timer: TimerRepo, clock: FakeClock, conn: sqlite3.Connection
) -> None:
    timer.save(_timer(clock.now_utc()))
    later = clock.now_utc() + timedelta(hours=1)
    timer.save(_timer(later, accrued_seconds=99))
    assert conn.execute("SELECT COUNT(*) FROM running_timer").fetchone()[0] == 1
    got = timer.get()
    assert got is not None
    assert got.started_at_utc == later
    assert got.accrued_seconds == 99


def test_id_check_constraint(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO running_timer (id, started_at_utc, tz_name, heartbeat_at_utc, "
            "heartbeat_accrued_sec) VALUES (2, 'x', 'UTC', 'x', 0)"
        )


def test_heartbeat_advances_durable_copy(timer: TimerRepo, clock: FakeClock) -> None:
    timer.save(_timer(clock.now_utc()))
    clock.advance(30)
    assert timer.heartbeat(30, clock.now_utc()) is True
    got = timer.get()
    assert got is not None
    assert got.accrued_seconds == 30
    assert got.heartbeat_accrued_sec == 30
    assert got.heartbeat_at_utc == clock.now_utc()
    assert got.started_at_utc == clock.now_utc() - timedelta(seconds=30)


def test_paused_since_round_trip(timer: TimerRepo, clock: FakeClock) -> None:
    paused = clock.now_utc() + timedelta(minutes=5)
    timer.save(_timer(clock.now_utc(), paused_since_utc=paused))
    got = timer.get()
    assert got is not None
    assert got.paused_since_utc == paused
    assert got.is_paused


def test_clear(timer: TimerRepo, clock: FakeClock) -> None:
    timer.save(_timer(clock.now_utc()))
    timer.clear()
    assert timer.get() is None
    timer.clear()  # idempotent
