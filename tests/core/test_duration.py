from __future__ import annotations

import pytest

from timetracker.core.duration import format_hm, format_hms


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
