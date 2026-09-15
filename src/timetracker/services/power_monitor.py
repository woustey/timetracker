"""Suspend/resume detection by tick drift (PRD-02 §6, FR-211).

A 1 s ``QTimer`` records wall and monotonic time on every tick. A wall-clock
gap much larger than the interval means the machine slept, hibernated, or the
process was frozen. Both deltas are reported because the monotonic clock
counts through sleep on Windows but not on Linux (``CLOCK_MONOTONIC``): the
consumer needs to know how much of the away span the timer already accrued.

A wall-clock step *backwards* cannot be a suspend; it is a clock change and
is only logged (PRD-01 §10). A large forward step with no monotonic gap is
indistinguishable from a Linux suspend and is reported as one — the idle
prompt is the right place for the user to decide either way.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from timetracker.core.clock import Clock
from timetracker.crashlog import log

TICK_MS = 1_000
SUSPEND_THRESHOLD_S = 5.0


class PowerMonitor(QObject):
    resumed_from_suspend = Signal(int, int)  # away_wall_seconds, away_mono_seconds
    clock_set_back = Signal(int)  # seconds the wall clock moved backwards

    def __init__(
        self, clock: Clock, parent: QObject | None = None, *, tick_ms: int = TICK_MS
    ) -> None:
        super().__init__(parent)
        self._clock = clock
        self._interval = tick_ms / 1000.0
        self._last_wall = clock.now_utc()
        self._last_mono = clock.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(tick_ms)
        self._timer.timeout.connect(self.on_tick)

    def start(self) -> None:
        self._last_wall = self._clock.now_utc()
        self._last_mono = self._clock.monotonic()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def on_tick(self) -> None:
        wall = self._clock.now_utc()
        mono = self._clock.monotonic()
        wall_delta = (wall - self._last_wall).total_seconds()
        mono_delta = mono - self._last_mono
        self._last_wall, self._last_mono = wall, mono

        if wall_delta < -1.0:
            back = int(round(-wall_delta))
            log().warning("System clock moved back %d s during operation", back)
            self.clock_set_back.emit(back)
            return
        if wall_delta - self._interval > SUSPEND_THRESHOLD_S:
            away_wall = int(round(wall_delta - self._interval))
            away_mono = int(round(max(0.0, mono_delta - self._interval)))
            log().info("Resumed after %d s away (monotonic advanced %d s)", away_wall, away_mono)
            self.resumed_from_suspend.emit(away_wall, away_mono)
