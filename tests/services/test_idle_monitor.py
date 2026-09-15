"""IdleMonitor under a fake clock and a fake provider (FR-209, FR-210, FR-211)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from timetracker.core.clock import FakeClock
from timetracker.core.models import RecordMethod
from timetracker.data.entry_repo import EntryRepo
from timetracker.data.timer_repo import TimerRepo
from timetracker.platform.base import Unavailable
from timetracker.services.idle_monitor import IdleMonitor, IdleOutcome, IdleSource, IdleSpan
from timetracker.services.timer_service import TimerService


class FakeIdleProvider:
    name = "fake"

    def __init__(self) -> None:
        self.idle = 0.0
        self.fail = False

    def seconds_idle(self) -> float:
        if self.fail:
            raise OSError("provider broke")
        return self.idle


@pytest.fixture
def provider() -> FakeIdleProvider:
    return FakeIdleProvider()


@pytest.fixture
def monitor(
    qapp, clock: FakeClock, provider: FakeIdleProvider, service: TimerService
) -> IdleMonitor:  # type: ignore[no-untyped-def]
    return IdleMonitor(clock, provider, service, threshold_seconds=600)


def _run_idle(
    clock: FakeClock, provider: FakeIdleProvider, monitor: IdleMonitor, minutes: int
) -> None:
    """Advance *minutes* with no input, polling every 15 s like the real timer would."""
    for _ in range(minutes * 4):
        clock.advance(15)
        provider.idle += 15
        monitor.poll()


# -- detection ----------------------------------------------------------------------


def test_no_polling_when_idle(monitor: IdleMonitor, provider: FakeIdleProvider) -> None:
    provider.idle = 10_000
    monitor.poll()
    assert monitor.outstanding is None


def test_threshold_crossing_raises_once_with_correct_since(
    monitor: IdleMonitor, provider: FakeIdleProvider, service: TimerService, clock: FakeClock, qtbot
) -> None:  # type: ignore[no-untyped-def]
    service.start()
    clock.advance(300)
    left_at = clock.now_utc()
    emitted: list[IdleSpan] = []
    monitor.prompt_needed.connect(emitted.append)
    _run_idle(clock, provider, monitor, 9)
    assert emitted == []
    _run_idle(clock, provider, monitor, 1)  # crosses 10 minutes
    assert len(emitted) == 1
    span = emitted[0]
    assert span.source is IdleSource.INPUT
    assert span.started_at_utc == left_at
    assert span.seconds == 600
    assert span.counted_seconds == 600
    assert span.still_idle
    _run_idle(clock, provider, monitor, 5)
    assert len(emitted) == 1  # still one outstanding prompt, no re-raise
    assert monitor.outstanding is not None and monitor.outstanding.seconds == 900


def test_span_freezes_when_input_resumes(
    monitor: IdleMonitor, provider: FakeIdleProvider, service: TimerService, clock: FakeClock, qtbot
) -> None:  # type: ignore[no-untyped-def]
    service.start()
    _run_idle(clock, provider, monitor, 12)
    assert monitor.outstanding is not None and monitor.outstanding.still_idle
    # User comes back 5 s before the next poll.
    clock.advance(15)
    provider.idle = 5
    with qtbot.waitSignal(monitor.span_updated, timeout=1000):
        monitor.poll()
    span = monitor.outstanding
    assert span is not None
    assert not span.still_idle
    assert span.seconds == 12 * 60 + 10
    assert span.counted_seconds == span.seconds
    # Further polls do not grow a frozen span.
    _run_idle(clock, provider, monitor, 3)
    assert monitor.outstanding is not None and monitor.outstanding.seconds == 12 * 60 + 10


def test_threshold_zero_disables_input_idle(
    monitor: IdleMonitor, provider: FakeIdleProvider, service: TimerService, clock: FakeClock
) -> None:
    monitor.set_threshold_seconds(0)
    service.start()
    _run_idle(clock, provider, monitor, 30)
    assert monitor.outstanding is None
    # ...but suspend still counts (FR-211).
    monitor.on_suspend_resumed(1200, 1200)
    assert monitor.outstanding is not None


def test_unavailable_provider_still_handles_suspend(
    qapp, clock: FakeClock, service: TimerService, qtbot
) -> None:  # type: ignore[no-untyped-def]
    monitor = IdleMonitor(clock, Unavailable("no desktop"), service, threshold_seconds=600)
    assert not monitor.available
    assert monitor.unavailable_reason == "no desktop"
    service.start()
    monitor.poll()
    assert monitor.outstanding is None
    with qtbot.waitSignal(monitor.prompt_needed, timeout=1000):
        monitor.on_suspend_resumed(1800, 0)
    span = monitor.outstanding
    assert span is not None and span.source is IdleSource.SUSPEND
    assert span.seconds == 1800 and span.counted_seconds == 0 and not span.still_idle


def test_provider_failure_disables_gracefully(
    monitor: IdleMonitor, provider: FakeIdleProvider, service: TimerService
) -> None:
    service.start()
    provider.fail = True
    monitor.poll()
    assert not monitor.available
    assert "provider broke" in (monitor.unavailable_reason or "")


def test_stopping_the_timer_supersedes_the_prompt(
    monitor: IdleMonitor, provider: FakeIdleProvider, service: TimerService, clock: FakeClock, qtbot
) -> None:  # type: ignore[no-untyped-def]
    service.start()
    _run_idle(clock, provider, monitor, 11)
    assert monitor.outstanding is not None
    with qtbot.waitSignal(monitor.resolved, timeout=1000):
        service.stop()
    assert monitor.outstanding is None


# -- outcomes -----------------------------------------------------------------------


def _idle_then(
    monitor: IdleMonitor, provider: FakeIdleProvider, service: TimerService, clock: FakeClock
) -> IdleSpan:
    """Work 20 min, be away 15 min, come back: the prompt is up with a frozen 15-min span."""
    service.start()
    clock.advance(20 * 60)
    _run_idle(clock, provider, monitor, 15)
    provider.idle = 0
    monitor.poll()  # input resumed exactly at this poll
    span = monitor.outstanding
    assert span is not None and not span.still_idle
    assert span.seconds == 15 * 60
    return span


def test_keep(
    monitor: IdleMonitor, provider: FakeIdleProvider, service: TimerService, clock: FakeClock
) -> None:
    _idle_then(monitor, provider, service, clock)
    monitor.resolve(IdleOutcome.KEEP)
    assert service.is_running
    assert service.elapsed_seconds() == 35 * 60
    assert monitor.outstanding is None


def test_discard(
    monitor: IdleMonitor,
    provider: FakeIdleProvider,
    service: TimerService,
    clock: FakeClock,
    timers: TimerRepo,
) -> None:
    _idle_then(monitor, provider, service, clock)
    monitor.resolve(IdleOutcome.DISCARD)
    assert service.is_running
    assert service.elapsed_seconds() == 20 * 60
    row = timers.get()
    assert row is not None and row.heartbeat_accrued_sec == 20 * 60  # persisted at once
    clock.advance(60)
    assert service.elapsed_seconds() == 21 * 60  # keeps running


def test_discard_and_stop(
    monitor: IdleMonitor,
    provider: FakeIdleProvider,
    service: TimerService,
    clock: FakeClock,
    entries: EntryRepo,
) -> None:
    span = _idle_then(monitor, provider, service, clock)
    monitor.resolve(IdleOutcome.DISCARD_AND_STOP)
    assert not service.is_running
    (entry,) = entries.query()
    assert entry.duration_seconds == 20 * 60
    assert entry.ended_at_utc == span.started_at_utc  # stopped at the moment you left
    assert entry.record_method is RecordMethod.STOPWATCH


def test_log_separately(
    monitor: IdleMonitor,
    provider: FakeIdleProvider,
    service: TimerService,
    clock: FakeClock,
    entries: EntryRepo,
) -> None:
    span = _idle_then(monitor, provider, service, clock)
    monitor.resolve(IdleOutcome.LOG_SEPARATELY)
    assert not service.is_running
    work, idle = entries.query(newest_first=False)
    assert work.duration_seconds == 20 * 60
    assert work.ended_at_utc == span.started_at_utc
    assert idle.started_at_utc == span.started_at_utc
    assert idle.ended_at_utc == span.started_at_utc + timedelta(minutes=15)
    assert idle.duration_seconds == 15 * 60
    assert idle.note == "Idle"
    assert idle.client_id == work.client_id and idle.type_id == work.type_id
    assert idle.record_method is RecordMethod.STOPWATCH


# -- sleep/wake reconciliation across platforms (FR-211 + FR-208) -------------------


def test_sleep_on_windows_keep_and_discard(
    monitor: IdleMonitor, service: TimerService, clock: FakeClock
) -> None:
    """Monotonic counted through the sleep: keep changes nothing, discard removes 30 min."""
    service.start()
    clock.advance(10 * 60)
    clock.advance(30 * 60)  # asleep; both clocks advance
    monitor.on_suspend_resumed(1800, 1800)
    span = monitor.outstanding
    assert span is not None and span.seconds == 1800 and span.counted_seconds == 1800
    monitor.resolve(IdleOutcome.KEEP)
    assert service.elapsed_seconds() == 40 * 60

    monitor.on_suspend_resumed(1800, 1800)  # pretend a second nap
    clock.advance(30 * 60)
    monitor.resolve(IdleOutcome.DISCARD)
    assert service.elapsed_seconds() == 40 * 60  # the 30 min that were counted are gone


def test_sleep_on_linux_keep_and_discard(
    monitor: IdleMonitor, service: TimerService, clock: FakeClock
) -> None:
    """Monotonic paused during the sleep: keep adds 30 min, discard changes nothing."""
    service.start()
    clock.advance(10 * 60)
    clock.step_wall(30 * 60)  # asleep; only the wall clock moves
    monitor.on_suspend_resumed(1800, 0)
    monitor.resolve(IdleOutcome.KEEP)
    assert service.elapsed_seconds() == 40 * 60

    clock.step_wall(30 * 60)
    monitor.on_suspend_resumed(1800, 0)
    monitor.resolve(IdleOutcome.DISCARD)
    assert service.elapsed_seconds() == 40 * 60


def test_sleep_while_prompt_outstanding_extends_it(
    monitor: IdleMonitor, provider: FakeIdleProvider, service: TimerService, clock: FakeClock
) -> None:
    service.start()
    _run_idle(clock, provider, monitor, 12)
    first = monitor.outstanding
    assert first is not None
    clock.advance(20 * 60)
    monitor.on_suspend_resumed(1200, 1200)
    span = monitor.outstanding
    assert span is not None
    assert span.started_at_utc == first.started_at_utc
    assert span.seconds == 32 * 60
    assert span.counted_seconds == first.counted_seconds + 1200
    assert not span.still_idle
