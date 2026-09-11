"""Add Time anchoring (PRD-01 §9.3.4, PRD-02 §5.4).

An Add Time entry has a duration but no observed start and end; this assigns
them. Pure: no I/O, no Qt, every branch testable.

- target date is today  → ``end = now`` truncated to the minute, ``start = end − duration``
- any other date        → ``start = max(end of last entry that day, workday start)``,
                          ``end = start + duration``
- if ``end`` would cross midnight it is clamped to 23:59:59 and ``needs_review``
  is set. The *duration* is never changed by anchoring — the timestamps are a
  convenience, the duration is the claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from timetracker.core.clock import Clock
from timetracker.core.models import Entry
from timetracker.core.timeutil import local_date_for, zone

DEFAULT_WORKDAY_START = time(9, 0)


@dataclass(frozen=True, slots=True)
class Anchor:
    started_at_utc: datetime
    ended_at_utc: datetime
    tz_name: str
    needs_review: bool = False


def anchor(
    duration_s: int,
    target_date: date,
    existing: list[Entry],
    workday_start: time,
    clock: Clock,
) -> Anchor:
    if duration_s < 0:
        raise ValueError("duration must be >= 0")
    tz_name = clock.tz_name()
    tz = zone(tz_name)
    now = clock.now_utc()
    today = local_date_for(now, tz_name)
    span = timedelta(seconds=duration_s)

    # All span arithmetic happens in UTC: adding a timedelta to a zone-aware
    # local datetime is wall-clock arithmetic and silently loses or gains an
    # hour across a DST transition.
    if target_date == today:
        end = now.astimezone(tz).replace(second=0, microsecond=0).astimezone(UTC)
        return Anchor(end - span, end, tz_name)

    day_start = datetime.combine(target_date, workday_start, tzinfo=tz).astimezone(UTC)
    same_day = [e for e in existing if e.local_date == target_date]
    start = max(max(e.ended_at_utc for e in same_day), day_start) if same_day else day_start

    review = False
    end = start + span
    midnight = datetime.combine(target_date, time(23, 59, 59), tzinfo=tz).astimezone(UTC)
    if end > midnight:
        end = midnight
        review = True
        if start > end:
            start = end
    return Anchor(start, end, tz_name, review)
