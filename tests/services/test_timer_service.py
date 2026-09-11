"""TimerService under a fake clock (PRD-02 §11 "Service")."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from timetracker.core.clock import FakeClock
from timetracker.core.models import RecordMethod, RunningTimer
from timetracker.data.entry_repo import EntryRepo
from timetracker.data.label_repo import LabelRepo
from timetracker.data.timer_repo import TimerRepo
from timetracker.services.timer_service import TimerService, TimerState


def test_idle_by_default(service: TimerService, timers: TimerRepo) -> None:
    assert service.state is TimerState.IDLE
    assert not service.is_running
    assert service.elapsed_seconds() == 0
    assert service.pending_recovery is None
    assert timers.get() is None
    with pytest.raises(RuntimeError):
        service.stop()


def test_start_persists_row_and_emits(
    service: TimerService, timers: TimerRepo, clock: FakeClock, qtbot
) -> None:  # type: ignore[no-untyped-def]
    with qtbot.waitSignals([service.started, service.state_changed, service.ticked], timeout=1000):
        timer = service.start(client_id=None, type_id=None, note="call")
    assert service.state is TimerState.RUNNING
    assert timer.started_at_utc == clock.now_utc()
    assert timer.tz_name == "Europe/Brussels"
    assert timer.note == "call"
    assert timers.get() == timer


def test_elapsed_uses_monotonic_and_stop_writes_entry(
    service: TimerService, entries: EntryRepo, timers: TimerRepo, clock: FakeClock, qtbot
) -> None:  # type: ignore[no-untyped-def]
    start = clock.now_utc()
    service.start()
    clock.advance(125)
    assert service.elapsed_seconds() == 125
    with qtbot.waitSignal(service.stopped, timeout=1000) as blocker:
        entry = service.stop()
    assert blocker.args == [entry]
    assert service.state is TimerState.IDLE
    assert timers.get() is None
    assert entry.record_method is RecordMethod.STOPWATCH
    assert entry.duration_seconds == 125
    assert entry.started_at_utc == start
    assert entry.ended_at_utc == start + timedelta(seconds=125)
    assert entries.count() == 1


def test_fr208_wall_clock_changes_do_not_alter_duration(
    service: TimerService, clock: FakeClock
) -> None:
    """DST transition / NTP step / manual clock edit mid-timer: duration is monotonic."""
    start = clock.now_utc()
    service.start()
    clock.advance(600)  # 10 real minutes
    clock.step_wall(3600)  # clock jumps forward an hour (DST spring-forward)
    clock.advance(300)  # 5 more real minutes
    clock.step_wall(-7200)  # someone sets the clock back two hours
    clock.advance(60)
    assert service.elapsed_seconds() == 960
    entry = service.stop()
    assert entry.duration_seconds == 960
    # The stop anchor is whatever the wall clock said — chronology only — but
    # never earlier than the start.
    assert entry.started_at_utc == start
    assert entry.ended_at_utc >= entry.started_at_utc


def test_fr208_across_a_real_dst_boundary(service: TimerService, clock: FakeClock) -> None:
    # Brussels, 29 March 2026: 02:00 CET → 03:00 CEST. Start at 01:30 local
    # (00:30 UTC), run 90 real minutes; local clock reads 04:00, duration is 90 min.
    clock.set_now(datetime(2026, 3, 29, 0, 30, tzinfo=UTC))
    service.start()
    clock.advance(90 * 60)
    entry = service.stop()
    assert entry.duration_seconds == 5400
    assert entry.local_date == datetime(2026, 3, 29).date()


def test_tick_emits_only_on_change(service: TimerService, clock: FakeClock, qtbot) -> None:  # type: ignore[no-untyped-def]
    service.start()
    seen: list[int] = []
    service.ticked.connect(seen.append)
    service.on_tick()  # 0 already emitted at start
    clock.advance(1)
    service.on_tick()
    service.on_tick()
    clock.advance(2)
    service.on_tick()
    assert seen == [1, 3]


def test_heartbeat_writes_durable_copy(
    service: TimerService, timers: TimerRepo, clock: FakeClock
) -> None:
    service.start()
    clock.advance(30)
    service.on_heartbeat()
    row = timers.get()
    assert row is not None
    assert row.accrued_seconds == 30
    assert row.heartbeat_accrued_sec == 30
    assert row.heartbeat_at_utc == clock.now_utc()
    clock.advance(30)
    service.on_heartbeat()
    row = timers.get()
    assert row is not None and row.heartbeat_accrued_sec == 60
    assert service.running is not None and service.running.heartbeat_accrued_sec == 60


def test_fr203_start_while_running_stops_and_saves_first(
    service: TimerService, entries: EntryRepo, clock: FakeClock
) -> None:
    service.start(note="first")
    clock.advance(100)
    second = service.start(note="second")
    assert entries.count() == 1
    saved = entries.recent(1)[0]
    assert saved.note == "first"
    assert saved.duration_seconds == 100
    assert service.running == second
    assert service.elapsed_seconds() == 0


def test_fr202_default_labels_from_most_recent_entry(
    service: TimerService, clients: LabelRepo, types: LabelRepo, clock: FakeClock
) -> None:
    assert service.default_labels() == (None, None)
    nike = clients.create("Nike")
    work = types.create("Work")
    service.start(nike.id, work.id)
    clock.advance(10)
    service.stop()
    assert service.default_labels() == (nike.id, work.id)
    assert clients.get(nike.id).last_used_at == clock.now_utc()
    assert types.get(work.id).last_used_at == clock.now_utc()


def test_labels_and_note_editable_while_running(
    service: TimerService, clients: LabelRepo, timers: TimerRepo, clock: FakeClock, qtbot
) -> None:  # type: ignore[no-untyped-def]
    nike = clients.create("Nike")
    service.start()
    clock.advance(42)
    with qtbot.waitSignal(service.labels_changed, timeout=1000):
        service.set_labels(nike.id, None)
    service.set_note("  ")  # blank → None
    service.set_note("drafting")
    row = timers.get()
    assert row is not None
    assert row.client_id == nike.id
    assert row.note == "drafting"
    assert row.accrued_seconds == 42
    entry = service.stop()
    assert entry.client_id == nike.id
    assert entry.note == "drafting"
    assert entry.duration_seconds == 42


def test_discard_drops_timer_without_entry(
    service: TimerService, entries: EntryRepo, timers: TimerRepo, clock: FakeClock
) -> None:
    service.start()
    clock.advance(10)
    service.discard()
    assert service.state is TimerState.IDLE
    assert timers.get() is None
    assert entries.count() == 0
    service.discard()  # idempotent


def test_today_total_excludes_live_timer(service: TimerService, clock: FakeClock) -> None:
    service.start()
    clock.advance(300)
    assert service.today_total_seconds() == 0
    service.stop()
    assert service.today_total_seconds() == 300
    assert service.started_local_time() == ""


def test_started_local_time_uses_timer_zone(service: TimerService, clock: FakeClock) -> None:
    clock.set_now(datetime(2026, 9, 11, 7, 5, tzinfo=UTC))  # 09:05 in Brussels (CEST)
    service.start()
    assert service.started_local_time() == "09:05"


# -- crash recovery (FR-207) ---------------------------------------------------


def _crashed_row(clock: FakeClock, **kw: object) -> RunningTimer:
    started = clock.now_utc() - timedelta(minutes=20)
    base: dict[str, object] = dict(
        started_at_utc=started,
        tz_name="Europe/Brussels",
        accrued_seconds=1170,
        paused_since_utc=None,
        client_id=None,
        type_id=None,
        note="before the crash",
        heartbeat_at_utc=started + timedelta(seconds=1170),
        heartbeat_accrued_sec=1170,
    )
    base.update(kw)
    return RunningTimer(**base)  # type: ignore[arg-type]


def test_recovery_offered_from_leftover_row_and_recovered(
    qapp,
    clock: FakeClock,
    timers: TimerRepo,
    entries: EntryRepo,
    clients: LabelRepo,
    types: LabelRepo,
) -> None:  # type: ignore[no-untyped-def]
    nike = clients.create("Nike")
    row = _crashed_row(clock, client_id=nike.id)
    timers.save(row)

    svc = TimerService(clock, timers, entries, clients, types)
    offer = svc.pending_recovery
    assert offer is not None
    assert offer.duration_seconds == 1170
    assert svc.state is TimerState.IDLE
    with pytest.raises(RuntimeError):
        svc.start()  # must resolve first

    entry = svc.recover()
    assert entry.duration_seconds == 1170
    assert entry.started_at_utc == row.started_at_utc
    assert entry.ended_at_utc == row.heartbeat_at_utc
    assert entry.client_id == nike.id
    assert entry.note == "before the crash"
    assert entry.record_method is RecordMethod.STOPWATCH
    assert svc.pending_recovery is None
    assert timers.get() is None
    assert clients.get(nike.id).last_used_at == clock.now_utc()
    svc.start()  # now allowed


def test_recovery_discarded(
    qapp,
    clock: FakeClock,
    timers: TimerRepo,
    entries: EntryRepo,
    clients: LabelRepo,
    types: LabelRepo,
) -> None:  # type: ignore[no-untyped-def]
    timers.save(_crashed_row(clock))
    svc = TimerService(clock, timers, entries, clients, types)
    assert svc.pending_recovery is not None
    svc.discard_recovery()
    assert svc.pending_recovery is None
    assert timers.get() is None
    assert entries.count() == 0
    svc.discard_recovery()  # idempotent
    with pytest.raises(RuntimeError):
        svc.recover()
