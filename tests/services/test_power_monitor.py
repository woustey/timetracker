"""PowerMonitor: suspend by tick drift, both deltas, clock-set-back warning."""

from __future__ import annotations

from timetracker.core.clock import FakeClock
from timetracker.services.power_monitor import PowerMonitor


def test_normal_ticks_are_silent(qapp, clock: FakeClock, qtbot) -> None:  # type: ignore[no-untyped-def]
    pm = PowerMonitor(clock)
    pm.start()
    with qtbot.assertNotEmitted(pm.resumed_from_suspend), qtbot.assertNotEmitted(pm.clock_set_back):
        for _ in range(10):
            clock.advance(1)
            pm.on_tick()
        clock.advance(4)  # a slow tick under load is not a suspend
        pm.on_tick()


def test_windows_style_sleep_reports_both_deltas(qapp, clock: FakeClock, qtbot) -> None:  # type: ignore[no-untyped-def]
    """Windows: the monotonic clock counts through sleep, so both deltas match."""
    pm = PowerMonitor(clock)
    pm.start()
    clock.advance(1)
    pm.on_tick()
    clock.advance(1 + 30 * 60)  # the tick that fires after a 30-minute sleep
    with qtbot.waitSignal(pm.resumed_from_suspend, timeout=1000) as blocker:
        pm.on_tick()
    assert blocker.args == [1800, 1800]


def test_linux_style_sleep_reports_no_monotonic_progress(qapp, clock: FakeClock, qtbot) -> None:  # type: ignore[no-untyped-def]
    """Linux: CLOCK_MONOTONIC pauses during suspend — only the wall clock jumps."""
    pm = PowerMonitor(clock)
    pm.start()
    clock.advance(1)
    pm.on_tick()
    clock.advance(1)
    clock.step_wall(30 * 60)
    with qtbot.waitSignal(pm.resumed_from_suspend, timeout=1000) as blocker:
        pm.on_tick()
    assert blocker.args == [1800, 0]


def test_clock_set_back_is_reported_not_treated_as_sleep(qapp, clock: FakeClock, qtbot) -> None:  # type: ignore[no-untyped-def]
    pm = PowerMonitor(clock)
    pm.start()
    clock.advance(1)
    clock.step_wall(-3600)
    with qtbot.assertNotEmitted(pm.resumed_from_suspend):
        with qtbot.waitSignal(pm.clock_set_back, timeout=1000) as blocker:
            pm.on_tick()
    assert blocker.args == [3599]
    # Subsequent ticks measure from the new baseline: no spurious suspend.
    clock.advance(1)
    with qtbot.assertNotEmitted(pm.resumed_from_suspend):
        pm.on_tick()


def test_start_resets_the_baseline(qapp, clock: FakeClock, qtbot) -> None:  # type: ignore[no-untyped-def]
    pm = PowerMonitor(clock)
    clock.advance(3600)  # time passes before the monitor is started
    pm.start()
    clock.advance(1)
    with qtbot.assertNotEmitted(pm.resumed_from_suspend):
        pm.on_tick()
