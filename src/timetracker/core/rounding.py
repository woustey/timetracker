"""Billing-increment rounding (FR-604–FR-606, PRD-02 §5.3).

Applied at export only; nothing here touches a stored record (P2). Scope is
applied *before* rounding: ``PER_ENTRY`` rounds each line, ``PER_GROUP`` sums
the (local day × client × type) group and rounds that sum once. Because the
export is one line per entry, the group's uplift is booked on the group's last
line so the lines still add up to the group total.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum

INCREMENTS = (0, 6, 10, 15, 30)  # minutes; 0 = none (FR-604)


class RoundingScope(Enum):
    PER_ENTRY = "per_entry"
    PER_GROUP = "per_group"  # day × client × type — the default (PRD-01 Q4)

    @property
    def display(self) -> str:
        return "per entry" if self is RoundingScope.PER_ENTRY else "per day × client × type"


def round_up(seconds: int, increment_minutes: int) -> int:
    """Round up to the next whole increment. Zero stays zero; negatives clamp to zero."""
    if increment_minutes <= 0 or seconds <= 0:
        return max(seconds, 0)
    step = increment_minutes * 60
    return ((seconds + step - 1) // step) * step


@dataclass(frozen=True, slots=True)
class BillableRow:
    """The minimum a rounding pass needs to know about a line."""

    key: object  # opaque, returned unchanged (an entry id, uuid, or index)
    local_date: date
    client_id: int | None
    type_id: int | None
    duration_seconds: int


def apply_rounding(
    rows: Sequence[BillableRow], increment_minutes: int, scope: RoundingScope
) -> dict[object, int]:
    """Billed seconds per ``row.key``. With increment 0 every row bills its raw duration."""
    if increment_minutes <= 0:
        return {r.key: max(0, r.duration_seconds) for r in rows}
    if scope is RoundingScope.PER_ENTRY:
        return {r.key: round_up(r.duration_seconds, increment_minutes) for r in rows}

    billed: dict[object, int] = {}
    groups: dict[tuple[date, int | None, int | None], list[BillableRow]] = {}
    for r in rows:
        groups.setdefault((r.local_date, r.client_id, r.type_id), []).append(r)
    for members in groups.values():
        raw = sum(max(0, m.duration_seconds) for m in members)
        target = round_up(raw, increment_minutes)
        for m in members:
            billed[m.key] = max(0, m.duration_seconds)
        billed[members[-1].key] += target - raw  # uplift on the last line of the group
    return billed


def total_billed(billed: Iterable[int]) -> int:
    return sum(billed)
