"""Add Time anchoring (PRD-01 §9.3.4, PRD-02 §5.4) — pure, exhaustively testable."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from timetracker.core.anchoring import DEFAULT_WORKDAY_START, anchor
from timetracker.core.clock import FakeClock
from timetracker.core.models import Entry, RecordMethod

BRU = ZoneInfo("Europe/Brussels")


def _entry(start_local: datetime, minutes: int, idx: int = 1) -> Entry:
    start = start_local.astimezone(UTC)
    end = start + timedelta(minutes=minutes)
    return Entry(
        id=idx,
        uuid=f"u{idx}",
        started_at_utc=start,
        ended_at_utc=end,
        tz_name="Europe/Brussels",
        local_date=start_local.date(),
        duration_seconds=minutes * 60,
        paused_seconds=0,
        client_id=None,
        type_id=None,
        note=None,
        record_method=RecordMethod.QUICKADD,
        is_edited=False,
        created_at=start,
        modified_at=start,
    )


@pytest.fixture
def clock() -> FakeClock:
    # Friday 11 Sep 2026, 14:37:42 in Brussels (12:37:42 UTC).
    return FakeClock(now=datetime(2026, 9, 11, 12, 37, 42, tzinfo=UTC), tz="Europe/Brussels")


def test_today_ends_now_truncated_to_minute(clock: FakeClock) -> None:
    a = anchor(30 * 60, date(2026, 9, 11), [], DEFAULT_WORKDAY_START, clock)
    assert a.ended_at_utc == datetime(2026, 9, 11, 12, 37, tzinfo=UTC)
    assert a.started_at_utc == datetime(2026, 9, 11, 12, 7, tzinfo=UTC)
    assert a.tz_name == "Europe/Brussels"
    assert not a.needs_review


def test_today_may_start_before_workday_start_without_review(clock: FakeClock) -> None:
    # 14:37 local − 10 h = 04:37: today's rule anchors backwards from now, no clamp.
    a = anchor(10 * 3600, date(2026, 9, 11), [], DEFAULT_WORKDAY_START, clock)
    assert a.started_at_utc.astimezone(BRU).time() == time(4, 37)
    assert not a.needs_review


def test_past_date_without_entries_starts_at_workday_start(clock: FakeClock) -> None:
    a = anchor(90 * 60, date(2026, 9, 8), [], time(9, 0), clock)
    assert a.started_at_utc.astimezone(BRU) == datetime(2026, 9, 8, 9, 0, tzinfo=BRU)
    assert a.ended_at_utc.astimezone(BRU) == datetime(2026, 9, 8, 10, 30, tzinfo=BRU)
    assert not a.needs_review


def test_past_date_starts_after_last_entry_of_that_day(clock: FakeClock) -> None:
    existing = [
        _entry(datetime(2026, 9, 8, 9, 0, tzinfo=BRU), 60, 1),
        _entry(datetime(2026, 9, 8, 13, 0, tzinfo=BRU), 45, 2),  # latest end 13:45
        _entry(datetime(2026, 9, 9, 16, 0, tzinfo=BRU), 60, 3),  # other day, ignored
    ]
    a = anchor(30 * 60, date(2026, 9, 8), existing, time(9, 0), clock)
    assert a.started_at_utc.astimezone(BRU) == datetime(2026, 9, 8, 13, 45, tzinfo=BRU)
    assert a.ended_at_utc.astimezone(BRU) == datetime(2026, 9, 8, 14, 15, tzinfo=BRU)
    assert not a.needs_review


def test_past_date_last_entry_before_workday_start_uses_workday_start(clock: FakeClock) -> None:
    existing = [_entry(datetime(2026, 9, 8, 6, 0, tzinfo=BRU), 30, 1)]  # ends 06:30
    a = anchor(15 * 60, date(2026, 9, 8), existing, time(9, 0), clock)
    assert a.started_at_utc.astimezone(BRU).time() == time(9, 0)
    assert not a.needs_review


def test_midnight_clamp_sets_needs_review(clock: FakeClock) -> None:
    existing = [_entry(datetime(2026, 9, 8, 22, 0, tzinfo=BRU), 60, 1)]  # ends 23:00
    a = anchor(2 * 3600, date(2026, 9, 8), existing, time(9, 0), clock)
    assert a.started_at_utc.astimezone(BRU) == datetime(2026, 9, 8, 23, 0, tzinfo=BRU)
    assert a.ended_at_utc.astimezone(BRU) == datetime(2026, 9, 8, 23, 59, 59, tzinfo=BRU)
    assert a.needs_review
    assert a.ended_at_utc >= a.started_at_utc


def test_day_already_full_clamps_to_end_of_day(clock: FakeClock) -> None:
    existing = [_entry(datetime(2026, 9, 8, 23, 30, tzinfo=BRU), 40, 1)]  # ends 00:10 next day
    a = anchor(600, date(2026, 9, 8), existing, time(9, 0), clock)
    assert a.needs_review
    assert a.ended_at_utc >= a.started_at_utc
    assert a.ended_at_utc.astimezone(BRU).date() == date(2026, 9, 8)


def test_zero_duration_and_negative(clock: FakeClock) -> None:
    a = anchor(0, date(2026, 9, 11), [], time(9, 0), clock)
    assert a.started_at_utc == a.ended_at_utc
    with pytest.raises(ValueError):
        anchor(-1, date(2026, 9, 11), [], time(9, 0), clock)


def test_anchoring_across_dst_day(clock: FakeClock) -> None:
    # 29 March 2026: 02:00→03:00. 90 minutes from 01:30 local ends at 04:00 local
    # (only 60 min of wall-clock labels pass), and the UTC span is exactly 90 min.
    a = anchor(90 * 60, date(2026, 3, 29), [], time(1, 30), clock)
    assert a.started_at_utc.astimezone(BRU) == datetime(2026, 3, 29, 1, 30, tzinfo=BRU)
    assert a.ended_at_utc - a.started_at_utc == timedelta(minutes=90)
    assert a.ended_at_utc.astimezone(BRU).time() == time(4, 0)


@pytest.mark.parametrize("duration", [1, 59, 60, 3599, 3600, 8 * 3600, 20 * 3600])
@pytest.mark.parametrize("day", [date(2026, 9, 11), date(2026, 9, 8), date(2026, 3, 29)])
def test_property_never_ends_before_start(clock: FakeClock, duration: int, day: date) -> None:
    existing = [_entry(datetime(2026, 9, 8, 21, 0, tzinfo=BRU), 120, 1)]
    a = anchor(duration, day, existing, time(9, 0), clock)
    assert a.ended_at_utc >= a.started_at_utc
