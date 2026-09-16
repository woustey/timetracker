"""Day-timeline layout (FR-509, v1.1) — pure geometry over one local day's entries.

Given the entries of a local date, produce what a canvas needs to paint:
blocks in minutes-of-day with a lane index (overlapping entries sit side by
side), the gaps between the covered spans (the unaccounted time the view
exists to make obvious), and the totals. Times are the entries' *anchors*
(``started_at_utc`` / ``ended_at_utc`` in the entry's own zone); a block whose
anchors disagree with its duration is still drawn by its anchors, since that
is where it sits on the day, and the discrepancy flag stays with the log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from timetracker.core.models import Entry
from timetracker.core.timeutil import zone

MINUTES_PER_DAY = 24 * 60


@dataclass(frozen=True, slots=True)
class Block:
    entry_id: int
    start_min: int  # minutes from local midnight, clamped to the day
    end_min: int  # > start_min (a zero-length entry gets one minute so it is visible)
    lane: int
    lanes: int  # how many lanes the overlapping cluster uses
    continues_before: bool = False  # started on an earlier day
    continues_after: bool = False  # ends on a later day


@dataclass(frozen=True, slots=True)
class Gap:
    start_min: int
    end_min: int

    @property
    def minutes(self) -> int:
        return self.end_min - self.start_min


@dataclass(frozen=True, slots=True)
class DayLayout:
    day: date
    blocks: list[Block] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)
    first_min: int | None = None  # earliest block start
    last_min: int | None = None  # latest block end
    tracked_seconds: int = 0  # sum of duration_seconds (the billed truth)
    covered_minutes: int = 0  # union of the anchored spans

    @property
    def gap_minutes(self) -> int:
        return sum(g.minutes for g in self.gaps)

    @property
    def is_empty(self) -> bool:
        return not self.blocks


def layout_day(entries: list[Entry], day: date, tz_name: str) -> DayLayout:
    """Lay out *entries* (any zone) on the local calendar *day* in *tz_name*."""
    tz = zone(tz_name)
    spans: list[tuple[int, int, Entry, bool, bool]] = []
    for e in entries:
        s, e_, before, after = _clip_to_day(e.started_at_utc, e.ended_at_utc, day, tz)
        if s is None or e_ is None:
            continue
        if e_ <= s:
            e_ = min(MINUTES_PER_DAY, s + 1)
            if e_ <= s:
                s = e_ - 1
        spans.append((s, e_, e, before, after))
    spans.sort(key=lambda t: (t[0], t[1], t[2].id))

    blocks = _assign_lanes(spans)
    covered = _union([(s, e_) for s, e_, *_ in spans])
    gaps = [
        Gap(a_end, b_start)
        for (_, a_end), (b_start, _) in zip(covered, covered[1:], strict=False)
        if b_start > a_end
    ]
    return DayLayout(
        day=day,
        blocks=blocks,
        gaps=gaps,
        first_min=covered[0][0] if covered else None,
        last_min=covered[-1][1] if covered else None,
        tracked_seconds=sum(max(0, t[2].duration_seconds) for t in spans),
        covered_minutes=sum(e_ - s for s, e_ in covered),
    )


def _clip_to_day(
    start_utc: datetime, end_utc: datetime, day: date, tz: ZoneInfo
) -> tuple[int | None, int | None, bool, bool]:
    day_start = datetime.combine(day, time(0, 0), tzinfo=tz)
    day_end = datetime.combine(day, time(23, 59, 59), tzinfo=tz)
    s_local = start_utc.astimezone(tz)
    e_local = end_utc.astimezone(tz)
    if e_local < day_start or s_local > day_end:
        return None, None, False, False
    before = s_local < day_start
    after = e_local > day_end
    s_min = 0 if before else s_local.hour * 60 + s_local.minute
    e_min = (
        MINUTES_PER_DAY
        if after
        else e_local.hour * 60 + e_local.minute + (1 if e_local.second else 0)
    )
    return s_min, min(MINUTES_PER_DAY, e_min), before, after


def _assign_lanes(spans: list[tuple[int, int, Entry, bool, bool]]) -> list[Block]:
    """Greedy interval colouring per overlapping cluster; lanes count is per cluster."""
    blocks: list[Block] = []
    cluster: list[tuple[int, int, Entry, bool, bool, int]] = []
    lane_ends: list[int] = []
    cluster_end = -1

    def flush() -> None:
        lanes = len(lane_ends)
        for s, e_, entry, before, after, lane in cluster:
            blocks.append(Block(entry.id, s, e_, lane, lanes, before, after))
        cluster.clear()
        lane_ends.clear()

    for s, e_, entry, before, after in spans:
        if cluster and s >= cluster_end:
            flush()
        lane = next((i for i, end in enumerate(lane_ends) if end <= s), None)
        if lane is None:
            lane = len(lane_ends)
            lane_ends.append(e_)
        else:
            lane_ends[lane] = e_
        cluster.append((s, e_, entry, before, after, lane))
        cluster_end = max(cluster_end, e_)
    if cluster:
        flush()
    return blocks


def _union(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for s, e_ in sorted(spans):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e_))
        else:
            merged.append((s, e_))
    return merged
