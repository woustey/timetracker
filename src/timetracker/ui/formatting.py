"""Time-of-day formatting honouring the 12 h / 24 h setting (FR-701).

A UI-layer module-level switch: the setting is read once at boot and on change,
and every widget that prints a clock time goes through :func:`fmt_time`.
"""

from __future__ import annotations

from datetime import datetime, time

_twelve_hour = False


def set_twelve_hour(enabled: bool) -> None:
    global _twelve_hour
    _twelve_hour = enabled


def twelve_hour() -> bool:
    return _twelve_hour


def fmt_time(value: datetime | time, *, seconds: bool = False) -> str:
    if _twelve_hour:
        text = value.strftime("%I:%M:%S %p" if seconds else "%I:%M %p")
        return text.lstrip("0")
    return value.strftime("%H:%M:%S" if seconds else "%H:%M")
