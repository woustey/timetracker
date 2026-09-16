"""core/weekgrid (FR-510): week boundaries per first-weekday setting, rows, marginals."""

from __future__ import annotations

from datetime import date

from timetracker.core.weekgrid import build_week_grid, week_days


def test_week_days_respect_first_weekday() -> None:
    wed = date(2026, 9, 16)
    assert week_days(wed)[0] == date(2026, 9, 14) and week_days(wed)[-1] == date(2026, 9, 20)
    assert week_days(wed, first_weekday=6)[0] == date(2026, 9, 13)  # Sunday-first
    assert week_days(date(2026, 9, 13), first_weekday=6)[0] == date(2026, 9, 13)
    assert week_days(date(2026, 9, 14), first_weekday=0)[0] == date(2026, 9, 14)


def test_grid_rows_sorted_by_total_unlabelled_last_and_marginals() -> None:
    days = week_days(date(2026, 9, 16))
    cells = [
        (1, date(2026, 9, 14), 3600),
        (1, date(2026, 9, 16), 1800),
        (2, date(2026, 9, 14), 7200),
        (None, date(2026, 9, 18), 600),
        (3, date(2026, 9, 30), 99999),  # outside the week: ignored
        (2, date(2026, 9, 15), 0),  # empty cell: ignored
    ]
    grid = build_week_grid(cells, days, {1: "Nike", 2: "ASICS"})
    assert [r.name for r in grid.rows] == ["ASICS", "Nike", "—"]
    assert grid.rows[1].cells == (3600, 0, 1800, 0, 0, 0, 0)
    assert grid.rows[1].total_seconds == 5400
    assert grid.day_totals == (10800, 0, 1800, 0, 600, 0, 0)
    assert grid.total_seconds == 13200
    assert build_week_grid([], days, {}).is_empty
