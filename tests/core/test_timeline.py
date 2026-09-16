"""core/timeline (FR-509): blocks, lanes for overlaps, gaps, day clipping, totals."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from timetracker.core.models import Entry, RecordMethod
from timetracker.core.timeline import layout_day

TZ = "Europe/Brussels"
DAY = date(2026, 9, 16)


def _entry(i: int, start_local_hm: str, minutes: int, *, day: date = DAY) -> Entry:
    h, m = (int(x) for x in start_local_hm.split(":"))
    from timetracker.core.timeutil import zone

    start = datetime.combine(day, datetime.min.time(), tzinfo=zone(TZ)).replace(hour=h, minute=m)
    start_utc = start.astimezone(UTC)
    return Entry(
        id=i,
        uuid=f"u{i}",
        started_at_utc=start_utc,
        ended_at_utc=start_utc + timedelta(minutes=minutes),
        tz_name=TZ,
        local_date=day,
        duration_seconds=minutes * 60,
        paused_seconds=0,
        client_id=None,
        type_id=None,
        note=None,
        record_method=RecordMethod.STOPWATCH,
        is_edited=False,
        created_at=start_utc,
        modified_at=start_utc,
    )


def test_blocks_gaps_and_totals() -> None:
    entries = [_entry(1, "09:00", 60), _entry(2, "10:30", 30), _entry(3, "13:00", 90)]
    lay = layout_day(entries, DAY, TZ)
    assert [(b.entry_id, b.start_min, b.end_min, b.lane, b.lanes) for b in lay.blocks] == [
        (1, 540, 600, 0, 1),
        (2, 630, 660, 0, 1),
        (3, 780, 870, 0, 1),
    ]
    assert [(g.start_min, g.end_min) for g in lay.gaps] == [(600, 630), (660, 780)]
    assert lay.gap_minutes == 150
    assert (lay.first_min, lay.last_min) == (540, 870)
    assert lay.tracked_seconds == 180 * 60 and lay.covered_minutes == 180
    assert not lay.is_empty


def test_overlaps_get_lanes_and_no_gap_inside_a_cluster() -> None:
    entries = [
        _entry(1, "09:00", 120),
        _entry(2, "09:30", 30),
        _entry(3, "10:00", 90),
        _entry(4, "12:00", 30),
    ]
    lay = layout_day(entries, DAY, TZ)
    lanes = {b.entry_id: (b.lane, b.lanes) for b in lay.blocks}
    assert lanes == {1: (0, 2), 2: (1, 2), 3: (1, 2), 4: (0, 1)}  # 3 reuses lane 1 after 2 ends
    assert [(g.start_min, g.end_min) for g in lay.gaps] == [(690, 720)]
    assert (
        lay.covered_minutes == 180 and lay.tracked_seconds == 270 * 60
    )  # double-booked time counts once


def test_clipping_and_zero_length() -> None:
    overnight = _entry(1, "23:00", 120)  # ends 01:00 next day
    next_day = _entry(2, "00:30", 30, day=DAY + timedelta(days=1))
    zero = _entry(3, "08:00", 0)
    lay = layout_day([overnight, next_day, zero], DAY, TZ)
    ids = {b.entry_id: b for b in lay.blocks}
    assert (ids[1].start_min, ids[1].end_min, ids[1].continues_after) == (1380, 1440, True)
    assert 2 not in ids
    assert (ids[3].start_min, ids[3].end_min) == (480, 481)
    tomorrow = layout_day([overnight, next_day], DAY + timedelta(days=1), TZ)
    first = {b.entry_id: b for b in tomorrow.blocks}[1]
    assert (first.start_min, first.end_min, first.continues_before) == (0, 60, True)
    assert layout_day([], DAY, TZ).is_empty
