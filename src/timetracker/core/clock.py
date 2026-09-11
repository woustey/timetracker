"""Clock injection (PRD-02 §5.1).

Every service takes a :class:`Clock` in its constructor. ``SystemClock`` is the
only place in the code base that calls ``datetime.now()`` or ``time.monotonic()``.
``FakeClock`` lives here rather than under ``tests/`` because services, data and
UI tests all need the same one.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Protocol

from timetracker.core.timeutil import local_tz_name


class Clock(Protocol):
    def now_utc(self) -> datetime:
        """Timezone-aware instant in UTC."""
        ...

    def monotonic(self) -> float:
        """Seconds from an arbitrary origin; never decreases within a process."""
        ...

    def tz_name(self) -> str:
        """IANA name of the current local zone, e.g. ``Europe/Brussels``."""
        ...


class SystemClock:
    """Production clock.

    ``tz_name`` may be supplied by the caller: the stdlib cannot name the local
    zone on Windows, but Qt can (``QTimeZone.systemTimeZoneId()``), and ``core/``
    must not import Qt — so the app passes it in. Without it we fall back to
    :func:`local_tz_name`.
    """

    def __init__(self, tz_name: str | None = None) -> None:
        self._tz = tz_name or local_tz_name()

    def now_utc(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()

    def tz_name(self) -> str:
        return self._tz


class FakeClock:
    """Deterministic clock for tests.

    ``advance()`` moves wall and monotonic time together — the normal case.
    ``step_wall()`` moves only the wall clock, which is how a DST change, an NTP
    correction or a manual clock edit looks to the process (FR-208).
    ``jump_monotonic()`` moves only the monotonic clock, which is what a suspend
    looks like on platforms where the monotonic clock keeps counting.
    """

    def __init__(
        self,
        now: datetime | None = None,
        tz: str = "Europe/Brussels",
        monotonic: float = 1000.0,
    ) -> None:
        if now is None:
            now = datetime(2026, 9, 11, 10, 0, tzinfo=UTC)
        if now.tzinfo is None:
            raise ValueError("FakeClock needs an aware datetime")
        self._now = now.astimezone(UTC)
        self._mono = monotonic
        self._tz = tz

    def now_utc(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._mono

    def tz_name(self) -> str:
        return self._tz

    # -- test controls -------------------------------------------------------

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("cannot advance backwards")
        self._now += timedelta(seconds=seconds)
        self._mono += seconds

    def step_wall(self, seconds: float) -> None:
        """Move the wall clock only (may be negative). Monotonic is untouched."""
        self._now += timedelta(seconds=seconds)

    def jump_monotonic(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("monotonic never decreases")
        self._mono += seconds

    def set_now(self, now: datetime) -> None:
        if now.tzinfo is None:
            raise ValueError("FakeClock needs an aware datetime")
        self._now = now.astimezone(UTC)

    def set_tz(self, tz: str) -> None:
        self._tz = tz
