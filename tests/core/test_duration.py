from __future__ import annotations

import pytest

from timetracker.core.duration import format_hm, format_hms, parse_duration


@pytest.mark.parametrize(
    ("seconds", "hms", "hm"),
    [
        (0, "0:00:00", "0:00"),
        (59, "0:00:59", "0:00"),
        (60, "0:01:00", "0:01"),
        (3599, "0:59:59", "0:59"),
        (3600, "1:00:00", "1:00"),
        (4983, "1:23:03", "1:23"),
        (36 * 3600 + 5, "36:00:05", "36:00"),
        (-7, "0:00:00", "0:00"),
    ],
)
def test_formatting(seconds: int, hms: str, hm: str) -> None:
    assert format_hms(seconds) == hms
    assert format_hm(seconds) == hm


@pytest.mark.parametrize(
    ("text", "minutes"),
    [
        # PRD-02 §5.5 table
        ("45", 45),
        ("1:30", 90),
        ("1h15", 75),
        ("1h 15m", 75),
        ("0.75h", 45),
        ("90m", 90),
        ("1,5h", 90),
        # tolerance
        ("  2H  ", 120),
        ("1 H 5 MIN", 65),
        ("1hr30", 90),
        ("1hour", 60),
        ("15min", 15),
        ("15 minutes", 15),
        ("0:05", 5),
        ("2:5", 125),
        ("0", 0),
        ("1.5", 1.5),
        ("1h0m", 60),
    ],
)
def test_parse_duration(text: str, minutes: float) -> None:
    assert parse_duration(text) == int(minutes * 60)


@pytest.mark.parametrize(
    "text",
    ["", "   ", "abc", "-15", "1h15h", "h", "m", "1:2:3", "1.5.5", "15 apples", "1h -5m", "::"],
)
def test_parse_duration_rejects(text: str) -> None:
    assert parse_duration(text) is None
