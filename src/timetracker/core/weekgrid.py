"""Weekly grid (FR-510, v1.1) — clients × days with per-cell totals, pure.

The repository hands over one grouped scan ``(client_id, local_date,
seconds)``; this arranges it into rows per client (largest week total first,
unlabelled entries last as "—"), a column per day of the week, and the
marginal totals. Seconds are summed, never rounded (P2): what the grid shows
is the same truth the log's totals show.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass(frozen=True, slots=True)
class GridRow:
    client_id: int | None
    name: str
    cells: tuple[int, ...]  # seconds per day, len == len(days)

    @property
    def total_seconds(self) -> int:
        return sum(self.cells)


@dataclass(frozen=True, slots=True)
class WeekGrid:
    days: tuple[date, ...]
    rows: tuple[GridRow, ...] = field(default_factory=tuple)

    @property
    def day_totals(self) -> tuple[int, ...]:
        return tuple(sum(r.cells[i] for r in self.rows) for i in range(len(self.days)))

    @property
    def total_seconds(self) -> int:
        return sum(r.total_seconds for r in self.rows)

    @property
    def is_empty(self) -> bool:
        return not self.rows


def week_days(anchor: date, first_weekday: int = 0) -> tuple[date, ...]:
    """The seven days of *anchor*'s week; ``first_weekday`` 0 = Monday … 6 = Sunday."""
    start = anchor - timedelta(days=(anchor.weekday() - first_weekday) % 7)
    return tuple(start + timedelta(days=i) for i in range(7))


def build_week_grid(
    cells: list[tuple[int | None, date, int]],
    days: tuple[date, ...],
    names: dict[int, str],
) -> WeekGrid:
    index = {d: i for i, d in enumerate(days)}
    per_client: dict[int | None, list[int]] = {}
    for client_id, day, seconds in cells:
        col = index.get(day)
        if col is None or seconds <= 0:
            continue
        per_client.setdefault(client_id, [0] * len(days))[col] += seconds
    rows = [
        GridRow(client_id, names.get(client_id, "—") if client_id is not None else "—", tuple(c))
        for client_id, c in per_client.items()
    ]
    rows.sort(key=lambda r: (r.client_id is None, -r.total_seconds, r.name.casefold()))
    return WeekGrid(days, tuple(rows))
