"""Row-level flags for the log (PRD-02 §4.2, FR-508). Flags, never corrects.

- **discrepancy**: ``|end − start − duration − paused| ≥ 120 s``. The duration is
  the measured fact; the timestamps are anchors. A large gap means the user
  edited one without the other and should look.
- **overlap** (FR-508): two entries whose ``[start, end)`` spans intersect.
  Overlap is never prevented — double-booking can be legitimate.
"""

from __future__ import annotations

from collections.abc import Iterable

from timetracker.core.models import Entry

DISCREPANCY_TOLERANCE_S = 120


def has_discrepancy(entry: Entry) -> bool:
    span = (entry.ended_at_utc - entry.started_at_utc).total_seconds()
    return abs(span - entry.duration_seconds - entry.paused_seconds) >= DISCREPANCY_TOLERANCE_S


def overlapping_ids(entries: Iterable[Entry]) -> set[int]:
    """Ids of entries that overlap at least one other entry. O(n log n)."""
    ordered = sorted(
        (e for e in entries if e.ended_at_utc > e.started_at_utc),
        key=lambda e: (e.started_at_utc, e.ended_at_utc),
    )
    flagged: set[int] = set()
    latest_end = None
    latest_id = None
    for e in ordered:
        if latest_end is not None and e.started_at_utc < latest_end:
            flagged.add(e.id)
            if latest_id is not None:
                flagged.add(latest_id)
        if latest_end is None or e.ended_at_utc > latest_end:
            latest_end, latest_id = e.ended_at_utc, e.id
    return flagged
