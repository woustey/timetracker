"""Date-range presets for the log filter (FR-503). Pure; the first weekday is a setting."""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum


class DatePreset(Enum):
    TODAY = "Today"
    THIS_WEEK = "This week"
    LAST_WEEK = "Last week"
    THIS_MONTH = "This month"
    LAST_MONTH = "Last month"
    ALL = "All time"
    CUSTOM = "Custom range"


def preset_range(
    preset: DatePreset, today: date, first_weekday: int = 0
) -> tuple[date | None, date | None]:
    """*first_weekday*: 0 = Monday … 6 = Sunday (FR-701 "first day of week")."""
    offset = (today.weekday() - first_weekday) % 7
    if preset is DatePreset.TODAY:
        return today, today
    if preset is DatePreset.THIS_WEEK:
        start = today - timedelta(days=offset)
        return start, start + timedelta(days=6)
    if preset is DatePreset.LAST_WEEK:
        start = today - timedelta(days=offset + 7)
        return start, start + timedelta(days=6)
    if preset is DatePreset.THIS_MONTH:
        start = today.replace(day=1)
        return start, _month_end(start)
    if preset is DatePreset.LAST_MONTH:
        start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        return start, _month_end(start)
    return None, None


def _month_end(first: date) -> date:
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return nxt - timedelta(days=1)
