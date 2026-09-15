from __future__ import annotations

from datetime import UTC, datetime, timedelta

from timetracker.core.consistency import has_discrepancy, overlapping_ids
from timetracker.core.models import Entry, RecordMethod


def _entry(idx: int, start_min: int, minutes: int, duration: int | None = None) -> Entry:
    start = datetime(2026, 9, 8, 9, 0, tzinfo=UTC) + timedelta(minutes=start_min)
    end = start + timedelta(minutes=minutes)
    return Entry(
        id=idx,
        uuid=f"u{idx}",
        started_at_utc=start,
        ended_at_utc=end,
        tz_name="UTC",
        local_date=start.date(),
        duration_seconds=(minutes if duration is None else duration) * 60,
        paused_seconds=0,
        client_id=None,
        type_id=None,
        note=None,
        record_method=RecordMethod.QUICKADD,
        is_edited=False,
        created_at=start,
        modified_at=start,
    )


def test_discrepancy_threshold() -> None:
    assert not has_discrepancy(_entry(1, 0, 30))
    assert not has_discrepancy(_entry(1, 0, 30, duration=31))  # 60 s off: tolerated
    assert has_discrepancy(_entry(1, 0, 30, duration=32))  # 120 s off: flagged
    assert has_discrepancy(_entry(1, 0, 30, duration=10))


def test_overlaps_flag_both_partners_only() -> None:
    a = _entry(1, 0, 30)  # 09:00–09:30
    b = _entry(2, 20, 30)  # 09:20–09:50 overlaps a
    c = _entry(3, 50, 10)  # 09:50–10:00 touches b, no overlap
    d = _entry(4, 120, 30)  # 11:00–11:30 alone
    e = _entry(5, 125, 1)  # inside d
    assert overlapping_ids([a, b, c, d, e]) == {1, 2, 4, 5}
    assert overlapping_ids([]) == set()
    assert overlapping_ids([a]) == set()
