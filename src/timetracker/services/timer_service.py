"""The running-timer state machine (PRD-02 §6; FR-201–FR-204, FR-206–FR-208).

Only this class writes the ``running_timer`` row and only this class creates
``STOPWATCH`` entries. Elapsed time is ``base_accrued + (monotonic - mono_start)``;
wall-clock instants are recorded at start and stop for chronology only, so a DST
change, an NTP step or a manual clock edit mid-timer never alters the duration.

Pause/resume (FR-212) is *should* and not implemented; the ``paused_since_utc``
column stays NULL.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from PySide6.QtCore import QObject, QTimer, Signal

from timetracker.core.clock import Clock
from timetracker.core.models import Entry, NewEntry, RecordMethod, RunningTimer
from timetracker.core.timeutil import local_date_for, zone
from timetracker.data.entry_repo import EntryRepo
from timetracker.data.label_repo import LabelRepo
from timetracker.data.timer_repo import TimerRepo

TICK_MS = 1_000
HEARTBEAT_MS = 30_000


class TimerState(Enum):
    IDLE = "idle"
    RUNNING = "running"


@dataclass(frozen=True, slots=True)
class RecoveryOffer:
    """What crash recovery can restore: the durable heartbeat copy (FR-207)."""

    timer: RunningTimer

    @property
    def duration_seconds(self) -> int:
        return self.timer.heartbeat_accrued_sec


class TimerService(QObject):
    started = Signal(object)  # RunningTimer
    ticked = Signal(int)  # elapsed seconds
    stopped = Signal(object)  # Entry
    labels_changed = Signal()
    state_changed = Signal(object)  # TimerState

    def __init__(
        self,
        clock: Clock,
        timer_repo: TimerRepo,
        entry_repo: EntryRepo,
        clients: LabelRepo,
        types: LabelRepo,
        parent: QObject | None = None,
        *,
        tick_ms: int = TICK_MS,
        heartbeat_ms: int = HEARTBEAT_MS,
    ) -> None:
        super().__init__(parent)
        self._clock = clock
        self._timers = timer_repo
        self._entries = entry_repo
        self._clients = clients
        self._types = types

        self._running: RunningTimer | None = None
        self._mono_start = 0.0
        self._base_accrued = 0
        self._last_emitted = -1

        self._tick = QTimer(self)
        self._tick.setInterval(tick_ms)
        self._tick.timeout.connect(self.on_tick)
        self._heartbeat = QTimer(self)
        self._heartbeat.setInterval(heartbeat_ms)
        self._heartbeat.timeout.connect(self.on_heartbeat)

        # A leftover row at construction means the last process did not stop
        # cleanly. It is offered, never auto-applied (FR-207).
        leftover = self._timers.get()
        self._recovery = RecoveryOffer(leftover) if leftover is not None else None

    # -- queries -------------------------------------------------------------

    @property
    def state(self) -> TimerState:
        return TimerState.RUNNING if self._running is not None else TimerState.IDLE

    @property
    def is_running(self) -> bool:
        return self._running is not None

    @property
    def running(self) -> RunningTimer | None:
        return self._running

    def elapsed_seconds(self) -> int:
        if self._running is None:
            return 0
        return self._base_accrued + int(self._clock.monotonic() - self._mono_start)

    def default_labels(self) -> tuple[int | None, int | None]:
        """Most recently used (client, type) pair (FR-202), from the newest entry."""
        recent = self._entries.recent(1)
        if not recent:
            return None, None
        return recent[0].client_id, recent[0].type_id

    # -- recovery (FR-207) ---------------------------------------------------

    @property
    def pending_recovery(self) -> RecoveryOffer | None:
        return self._recovery

    def recover(self) -> Entry:
        """Write the entry the heartbeat vouches for and clear the row."""
        if self._recovery is None:
            raise RuntimeError("nothing to recover")
        t = self._recovery.timer
        entry = self._entries.insert(
            NewEntry(
                started_at_utc=t.started_at_utc,
                ended_at_utc=t.heartbeat_at_utc,
                tz_name=t.tz_name,
                duration_seconds=t.heartbeat_accrued_sec,
                record_method=RecordMethod.STOPWATCH,
                client_id=t.client_id,
                type_id=t.type_id,
                note=t.note,
            )
        )
        self._timers.clear()
        self._recovery = None
        self._touch_labels(t.client_id, t.type_id)
        return entry

    def discard_recovery(self) -> None:
        if self._recovery is None:
            return
        self._timers.clear()
        self._recovery = None

    # -- transitions ---------------------------------------------------------

    def start(
        self,
        client_id: int | None = None,
        type_id: int | None = None,
        note: str | None = None,
    ) -> RunningTimer:
        """Start a timer. Never blocked on labels (FR-202). Stops a running one first (FR-203)."""
        if self._recovery is not None:
            raise RuntimeError("resolve the pending recovery before starting a timer")
        if self._running is not None:
            self.stop()
        now = self._clock.now_utc()
        timer = RunningTimer(
            started_at_utc=now,
            tz_name=self._clock.tz_name(),
            accrued_seconds=0,
            paused_since_utc=None,
            client_id=client_id,
            type_id=type_id,
            note=note,
            heartbeat_at_utc=now,
            heartbeat_accrued_sec=0,
        )
        self._timers.save(timer)
        self._running = timer
        self._mono_start = self._clock.monotonic()
        self._base_accrued = 0
        self._last_emitted = 0
        self._tick.start()
        self._heartbeat.start()
        self.started.emit(timer)
        self.state_changed.emit(TimerState.RUNNING)
        self.ticked.emit(0)
        return timer

    def stop(self) -> Entry:
        """Create the ``STOPWATCH`` entry (FR-204) and return to idle."""
        timer = self._running
        if timer is None:
            raise RuntimeError("no timer is running")
        elapsed = self.elapsed_seconds()
        now = self._clock.now_utc()
        self._tick.stop()
        self._heartbeat.stop()
        entry = self._entries.insert(
            NewEntry(
                started_at_utc=timer.started_at_utc,
                ended_at_utc=max(now, timer.started_at_utc),
                tz_name=timer.tz_name,
                duration_seconds=elapsed,
                record_method=RecordMethod.STOPWATCH,
                client_id=timer.client_id,
                type_id=timer.type_id,
                note=timer.note,
            )
        )
        self._timers.clear()
        self._running = None
        self._touch_labels(timer.client_id, timer.type_id)
        self.stopped.emit(entry)
        self.state_changed.emit(TimerState.IDLE)
        return entry

    def discard(self) -> None:
        """Drop the running timer without writing an entry (FR-111 "discard")."""
        if self._running is None:
            return
        self._tick.stop()
        self._heartbeat.stop()
        self._timers.clear()
        self._running = None
        self.state_changed.emit(TimerState.IDLE)

    def set_labels(self, client_id: int | None, type_id: int | None) -> None:
        """Change labels on the running timer (FR-202: editable while running)."""
        if self._running is None:
            return
        if (client_id, type_id) == (self._running.client_id, self._running.type_id):
            return
        self._replace_running(client_id=client_id, type_id=type_id)
        self.labels_changed.emit()

    def set_note(self, note: str | None) -> None:
        if self._running is None:
            return
        note = note or None
        if note == self._running.note:
            return
        self._replace_running(note=note)

    # -- timers (public so tests can drive them without an event loop) -------

    def on_tick(self) -> None:
        if self._running is None:
            return
        elapsed = self.elapsed_seconds()
        if elapsed != self._last_emitted:
            self._last_emitted = elapsed
            self.ticked.emit(elapsed)

    def on_heartbeat(self) -> None:
        """Persist the durable copy every 30 s (FR-207, NFR-07)."""
        if self._running is None:
            return
        elapsed = self.elapsed_seconds()
        now = self._clock.now_utc()
        self._timers.heartbeat(elapsed, now)
        self._running = _replace(
            self._running,
            accrued_seconds=elapsed,
            heartbeat_accrued_sec=elapsed,
            heartbeat_at_utc=now,
        )

    # -- internals -----------------------------------------------------------

    def _replace_running(self, **changes: object) -> None:
        assert self._running is not None
        updated = _replace(self._running, **changes)
        # Keep the row's accrued/heartbeat fields honest while we are at it.
        elapsed = self.elapsed_seconds()
        updated = _replace(updated, accrued_seconds=elapsed)
        self._timers.save(updated)
        self._running = updated

    def _touch_labels(self, client_id: int | None, type_id: int | None) -> None:
        if client_id is not None:
            self._clients.touch_last_used(client_id)
        if type_id is not None:
            self._types.touch_last_used(type_id)

    def started_local_time(self) -> str:
        """``HH:MM`` in the timer's own zone, for the running popover."""
        if self._running is None:
            return ""
        return self._running.started_at_utc.astimezone(zone(self._running.tz_name)).strftime(
            "%H:%M"
        )

    def today_total_seconds(self) -> int:
        """Stored entries on today's local date; the live timer is not included."""
        today = local_date_for(self._clock.now_utc(), self._clock.tz_name())
        return self._entries.total_seconds_for_date(today)


def _replace(timer: RunningTimer, **changes: object) -> RunningTimer:
    return replace(timer, **changes)  # type: ignore[arg-type]
