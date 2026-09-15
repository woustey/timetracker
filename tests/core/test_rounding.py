"""Rounding (FR-604–FR-606) against PRD-01 Appendix B, plus the §11 properties."""

from __future__ import annotations

from datetime import date

import pytest

from timetracker.core.rounding import (
    INCREMENTS,
    BillableRow,
    RoundingScope,
    apply_rounding,
    round_up,
)

APPENDIX_B_MINUTES = (6, 11, 17, 26, 44)  # 104 minutes exact


def _rows(minutes: tuple[int, ...], **kw: object) -> list[BillableRow]:
    base = {"local_date": date(2026, 9, 8), "client_id": 1, "type_id": 1}
    base.update(kw)
    return [
        BillableRow(key=i, duration_seconds=m * 60, **base)  # type: ignore[arg-type]
        for i, m in enumerate(minutes)
    ]


@pytest.mark.parametrize(
    ("increment", "billed_minutes"),
    [(0, 104), (6, 114), (10, 130), (15, 135)],
)
def test_appendix_b_per_entry(increment: int, billed_minutes: int) -> None:
    billed = apply_rounding(_rows(APPENDIX_B_MINUTES), increment, RoundingScope.PER_ENTRY)
    assert sum(billed.values()) == billed_minutes * 60


@pytest.mark.parametrize(
    ("increment", "billed_minutes"),
    [(0, 104), (6, 108), (10, 110), (15, 105), (30, 120)],
)
def test_appendix_b_per_group_rounds_once(increment: int, billed_minutes: int) -> None:
    billed = apply_rounding(_rows(APPENDIX_B_MINUTES), increment, RoundingScope.PER_GROUP)
    assert sum(billed.values()) == billed_minutes * 60
    # Lines keep their raw value except the last of the group, which carries the uplift.
    raw = [m * 60 for m in APPENDIX_B_MINUTES]
    assert [billed[i] for i in range(4)] == raw[:4]
    assert billed[4] == raw[4] + (billed_minutes - 104) * 60


def test_fr606_three_two_minute_emails() -> None:
    """The worked case in FR-606: 3 × 2 min at 6 min bill 18 per entry, 6 per group."""
    rows = _rows((2, 2, 2))
    assert sum(apply_rounding(rows, 6, RoundingScope.PER_ENTRY).values()) == 18 * 60
    assert sum(apply_rounding(rows, 6, RoundingScope.PER_GROUP).values()) == 6 * 60


def test_groups_are_day_client_type() -> None:
    rows = [
        BillableRow(1, date(2026, 9, 8), 1, 1, 120),
        BillableRow(2, date(2026, 9, 8), 1, 1, 120),  # same group as 1
        BillableRow(3, date(2026, 9, 8), 2, 1, 120),  # other client
        BillableRow(4, date(2026, 9, 9), 1, 1, 120),  # other day
        BillableRow(5, date(2026, 9, 8), 1, None, 120),  # unlabelled type is its own group
    ]
    billed = apply_rounding(rows, 6, RoundingScope.PER_GROUP)
    assert billed == {1: 120, 2: 240, 3: 360, 4: 360, 5: 360}


def test_round_up_table() -> None:
    assert round_up(0, 6) == 0
    assert round_up(1, 6) == 360
    assert round_up(360, 6) == 360
    assert round_up(361, 6) == 720
    assert round_up(-5, 6) == 0
    assert round_up(100, 0) == 100
    assert INCREMENTS == (0, 6, 10, 15, 30)


@pytest.mark.parametrize("increment", INCREMENTS)
@pytest.mark.parametrize("seconds", [0, 1, 59, 60, 359, 360, 361, 3599, 3600, 86399])
def test_property_monotone_and_never_less(increment: int, seconds: int) -> None:
    out = round_up(seconds, increment)
    assert out >= seconds
    assert round_up(seconds + 1, increment) >= out
    if increment:
        assert out % (increment * 60) == 0
    else:
        assert out == seconds
