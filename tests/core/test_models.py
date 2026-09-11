from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from timetracker.core.errors import ValidationError
from timetracker.core.models import (
    NewEntry,
    RecordMethod,
    clean_label_name,
    normalise_label_name,
)
from timetracker.core.timeutil import from_iso_utc, local_date_for, to_iso_utc


@pytest.mark.parametrize(
    ("raw", "norm"),
    [
        ("Nike", "nike"),
        ("nike", "nike"),
        ("Nike ", "nike"),
        ("  Nike", "nike"),
        ("Meeting /  Call", "meeting / call"),
        ("ASICS\tEurope", "asics europe"),
        ("Straße", "strasse"),  # casefold, not lower
    ],
)
def test_normalise_label_name(raw: str, norm: str) -> None:
    assert normalise_label_name(raw) == norm


def test_clean_label_name_keeps_casing_and_collapses_whitespace() -> None:
    assert clean_label_name("  Meeting /  Call ") == "Meeting / Call"
    with pytest.raises(ValidationError):
        clean_label_name("   ")


def test_iso_round_trip_truncates_to_seconds() -> None:
    instant = datetime(2026, 9, 11, 8, 4, 5, 999_000, tzinfo=UTC)
    text = to_iso_utc(instant)
    assert text == "2026-09-11T08:04:05Z"
    assert from_iso_utc(text) == instant.replace(microsecond=0)
    with pytest.raises(ValueError):
        to_iso_utc(datetime(2026, 9, 11))


@pytest.mark.parametrize(
    ("utc", "tz", "expected"),
    [
        # 22:30 UTC is 00:30 next day in Brussels (CEST, +2).
        (datetime(2026, 7, 1, 22, 30, tzinfo=UTC), "Europe/Brussels", date(2026, 7, 2)),
        # Same instant in winter is +1: still 23:30 the same day.
        (datetime(2026, 1, 5, 22, 30, tzinfo=UTC), "Europe/Brussels", date(2026, 1, 5)),
        # Singapore is +8 all year.
        (datetime(2026, 1, 5, 17, 0, tzinfo=UTC), "Asia/Singapore", date(2026, 1, 6)),
        # Unknown zone falls back to UTC rather than crashing.
        (datetime(2026, 1, 5, 23, 59, tzinfo=UTC), "Mars/Olympus", date(2026, 1, 5)),
    ],
)
def test_local_date_for(utc: datetime, tz: str, expected: date) -> None:
    assert local_date_for(utc, tz) == expected


def test_record_method_display() -> None:
    assert RecordMethod.STOPWATCH.display == "Start-Stop"
    assert RecordMethod.QUICKADD.display == "Add Time"


def test_new_entry_validation() -> None:
    t0 = datetime(2026, 9, 11, 9, 0, tzinfo=UTC)
    ok = NewEntry(t0, t0, "UTC", 0, RecordMethod.QUICKADD)
    ok.validate()
    with pytest.raises(ValidationError):
        NewEntry(t0, t0, "UTC", -1, RecordMethod.QUICKADD).validate()
    with pytest.raises(ValidationError):
        NewEntry(t0, t0.replace(hour=8), "UTC", 0, RecordMethod.QUICKADD).validate()
    with pytest.raises(ValidationError):
        NewEntry(t0, t0, "UTC", 0, RecordMethod.QUICKADD, note="x" * 501).validate()
