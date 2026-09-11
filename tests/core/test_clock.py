from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from timetracker.core.clock import FakeClock, SystemClock


def test_system_clock_is_utc_aware_and_monotonic_increases() -> None:
    clock = SystemClock(tz_name="Europe/Brussels")
    now = clock.now_utc()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)
    a = clock.monotonic()
    b = clock.monotonic()
    assert b >= a
    assert clock.tz_name() == "Europe/Brussels"


def test_system_clock_falls_back_to_a_valid_zone() -> None:
    # Whatever the host, the fallback must be a name zoneinfo accepts.
    from zoneinfo import ZoneInfo

    ZoneInfo(SystemClock().tz_name())


def test_fake_clock_advance_moves_both_clocks() -> None:
    start = datetime(2026, 3, 29, 0, 30, tzinfo=UTC)
    clock = FakeClock(now=start, monotonic=50.0)
    clock.advance(90)
    assert clock.now_utc() == start + timedelta(seconds=90)
    assert clock.monotonic() == 140.0


def test_fake_clock_step_wall_leaves_monotonic_alone() -> None:
    clock = FakeClock(monotonic=10.0)
    before = clock.now_utc()
    clock.step_wall(-3600)  # a manual clock change backwards
    assert clock.now_utc() == before - timedelta(hours=1)
    assert clock.monotonic() == 10.0


def test_fake_clock_rejects_naive_and_backwards() -> None:
    with pytest.raises(ValueError):
        FakeClock(now=datetime(2026, 1, 1))
    clock = FakeClock()
    with pytest.raises(ValueError):
        clock.advance(-1)
    with pytest.raises(ValueError):
        clock.jump_monotonic(-1)


def test_fake_clock_normalises_to_utc() -> None:
    from zoneinfo import ZoneInfo

    local = datetime(2026, 9, 11, 12, 0, tzinfo=ZoneInfo("Europe/Brussels"))
    clock = FakeClock(now=local)
    assert clock.now_utc() == datetime(2026, 9, 11, 10, 0, tzinfo=UTC)
    assert clock.now_utc().tzinfo == UTC
