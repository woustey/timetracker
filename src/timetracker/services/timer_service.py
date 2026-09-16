"""The running-timer state machine (PRD-02 §6; FR-201–FR-204, FR-206–FR-208).

Only this class writes the ``running_timer`` row and only this class creates
``STOPWATCH`` entries. Elapsed time is ``base_accrued + (monotonic - mono_start)``;
wall-clock instants are recorded at start and stop for chronology only, so a DST
change, an NTP step or a manual clock edit mid-timer never alters the duration.

Pause/resume (FR-212): while paused the elapsed value is frozen at
``base_accrued`` and the 1 s tick is off; resuming re-anchors ``mono_start`` and
continues the *same* timer. A pause is a chronology gap, not a measured
duration, so its length is the wall-clock span ``resume − paused_since`` and is
totalled into ``paused_seconds`` on the entry. Stopping while paused ends the
entry at the pause start; the trailing pause is not part of the entry.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
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
    PAUSED = "paused"


@dataclass(frozen=True, slots=True)
class RecoveryOffer:
    """What crash recovery can restore: the durable heartbeat copy (FR-207)."""

    timer: RunningTimer

    @property
    def duration_seconds(self) -> int:
        return self.timer.heartbeat_accrued_sec

    @property
    def ended_at_utc(self) -> datetime:
        """A timer that died paused ends at the pause start, like a stop while paused."""
        t = self.timer
        return t.paused_since_utc if t.paused_since_utc is not None else t.heartbeat_at_utc

    @property
    def paused_seconds(self) -> int:
        return self.timer.paused_seconds


class TimerService(QObject):
    started = Signal(object)  # RunningTimer
    ticked = Signal(int)  # elapsed seconds
    stopped = Signal(object)  # Entry
    paused = Signal()
    resumed = Signal()
    labels_changed = Signal()
    state_changed = Signal(object)  # TimerState
    long_running = Signal(int)  # elapsed seconds; once per timer at the threshold (PRD-01 §10)

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
        self._long_running_threshold = 12 * 3600
        self._long_running_prompted = False

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
        if self._running is None:
            return TimerState.IDLE
        return TimerState.PAUSED if self._running.is_paused else TimerState.RUNNING

    @property
    def is_running(self) -> bool:
        """Accruing right now (not idle, not paused)."""
        return self._running is not None and not self._running.is_paused

    @property
    def is_paused(self) -> bool:
        return self._running is not None and self._running.is_paused

    @property
    def is_active(self) -> bool:
        """There is a timer to stop: running or paused."""
        return self._running is not None

    @property
    def running(self) -> RunningTimer | None:
        return self._running

    def elapsed_seconds(self) -> int:
        if self._running is None:
            return 0
        if self._running.is_paused:
            return self._base_accrued
        return max(0, self._base_accrued + int(self._clock.monotonic() - self._mono_start))

    def paused_seconds(self) -> int:
        """Completed pauses so far; an open pause is not counted until it ends."""
        return 0 if self._running is None else self._running.paused_seconds

    @property
    def long_running_threshold(self) -> int:
        return self._long_running_threshold

    def set_long_running_threshold(self, seconds: int) -> None:
        """0 disables the "still running?" prompt."""
        self._long_running_threshold = max(0, int(seconds))

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
                ended_at_utc=max(self._recovery.ended_at_utc, t.started_at_utc),
                tz_name=t.tz_name,
                duration_seconds=t.heartbeat_accrued_sec,
                record_method=RecordMethod.STOPWATCH,
                client_id=t.client_id,
                type_id=t.type_id,
                note=t.note,
                paused_seconds=t.paused_seconds,
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
            paused_seconds=0,
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
        self._long_running_prompted = False
        self._tick.start()
        self._heartbeat.start()
        self.started.emit(timer)
        self.state_changed.emit(TimerState.RUNNING)
        self.ticked.emit(0)
        return timer

    def stop(
        self, *, ended_at_utc: datetime | None = None, elapsed_override: int | None = None
    ) -> Entry:
        """Create the ``STOPWATCH`` entry (FR-204) and return to idle.

        ``ended_at_utc`` moves the chronology anchor (e.g. to an idle start);
        ``elapsed_override`` replaces the measured duration. Both exist for the
        idle outcomes; ordinary stops pass neither. A stop while paused ends
        at the pause start (FR-212).
        """
        timer = self._running
        if timer is None:
            raise RuntimeError("no timer is running")
        elapsed = self.elapsed_seconds() if elapsed_override is None else max(0, elapsed_override)
        if ended_at_utc is not None:
            end = ended_at_utc
        elif timer.paused_since_utc is not None:
            end = timer.paused_since_utc
        else:
            end = self._clock.now_utc()
        self._tick.stop()
        self._heartbeat.stop()
        entry = self._entries.insert(
            NewEntry(
                started_at_utc=timer.started_at_utc,
                ended_at_utc=max(end, timer.started_at_utc),
                tz_name=timer.tz_name,
                duration_seconds=elapsed,
                record_method=RecordMethod.STOPWATCH,
                client_id=timer.client_id,
                type_id=timer.type_id,
                note=timer.note,
                paused_seconds=timer.paused_seconds,
            )
        )
        self._timers.clear()
        self._running = None
        self._touch_labels(timer.client_id, timer.type_id)
        self.stopped.emit(entry)
        self.state_changed.emit(TimerState.IDLE)
        return entry

    def pause(self) -> None:
        """Freeze the elapsed value (FR-212). No-op unless running."""
        timer = self._running
        if timer is None or timer.is_paused:
            return
        elapsed = self.elapsed_seconds()
        now = self._clock.now_utc()
        self._base_accrued = elapsed
        self._tick.stop()
        # A pause is a durable point: the heartbeat copy vouches for it too.
        self._running = _replace(
            timer,
            accrued_seconds=elapsed,
            paused_since_utc=now,
            heartbeat_at_utc=now,
            heartbeat_accrued_sec=elapsed,
        )
        self._timers.save(self._running)
        self.paused.emit()
        self.state_changed.emit(TimerState.PAUSED)

    def resume(self) -> None:
        """Continue the same timer; the pause's wall-clock length is booked. No-op unless paused."""
        timer = self._running
        if timer is None or timer.paused_since_utc is None:
            return
        now = self._clock.now_utc()
        gap = max(0, int((now - timer.paused_since_utc).total_seconds()))
        self._mono_start = self._clock.monotonic()
        self._running = _replace(
            timer,
            paused_since_utc=None,
            paused_seconds=timer.paused_seconds + gap,
            heartbeat_at_utc=now,
        )
        self._timers.save(self._running)
        self._last_emitted = -1
        self._tick.start()
        self.resumed.emit()
        self.state_changed.emit(TimerState.RUNNING)
        self.on_tick()

    def adjust_accrued(self, delta_seconds: int) -> int:
        """Add (or remove) seconds on the running timer; floors at zero. Returns new elapsed.

        Used by the idle outcomes (FR-209/FR-211). Persists immediately so an
        answered prompt survives a crash.
        """
        if self._running is None or delta_seconds == 0:
            return self.elapsed_seconds()
        current = self.elapsed_seconds()
        target = max(0, current + int(delta_seconds))
        self._base_accrued += target - current
        self.on_heartbeat()
        self._last_emitted = -1
        self.on_tick()
        return target

    def split_idle(
        self, idle_start_utc: datetime, idle_seconds: int, counted_seconds: int
    ) -> tuple[Entry, Entry]:
        """ "Log separately": stop at the idle start and write the idle span as its own entry.

        The first entry keeps the work before the idle period; the second has
        the same labels, the note ``Idle``, and the wall-clock length of the
        away span. Both are ``STOPWATCH`` entries created here (§6 rule).
        """
        timer = self._running
        if timer is None:
            raise RuntimeError("no timer is running")
        before = max(0, self.elapsed_seconds() - counted_seconds)
        work = self.stop(ended_at_utc=idle_start_utc, elapsed_override=before)
        idle = self._entries.insert(
            NewEntry(
                started_at_utc=idle_start_utc,
                ended_at_utc=idle_start_utc + timedelta(seconds=idle_seconds),
                tz_name=timer.tz_name,
                duration_seconds=idle_seconds,
                record_method=RecordMethod.STOPWATCH,
                client_id=timer.client_id,
                type_id=timer.type_id,
                note="Idle",
            )
        )
        return work, idle

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
        if self._running is None or self._running.is_paused:
            return
        elapsed = self.elapsed_seconds()
        if elapsed != self._last_emitted:
            self._last_emitted = elapsed
            self.ticked.emit(elapsed)
        if (
            self._long_running_threshold
            and not self._long_running_prompted
            and elapsed >= self._long_running_threshold
        ):
            self._long_running_prompted = True
            self.long_running.emit(elapsed)

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
        local = self._running.started_at_utc.astimezone(zone(self._running.tz_name))
        return self._format_time(local)

    @staticmethod
    def _format_time(local: object) -> str:
        from datetime import datetime

        assert isinstance(local, datetime)
        return local.strftime("%H:%M")

    def today_total_seconds(self) -> int:
        """Stored entries on today's local date; the live timer is not included."""
        today = local_date_for(self._clock.now_utc(), self._clock.tz_name())
        return self._entries.total_seconds_for_date(today)


def _replace(timer: RunningTimer, **changes: object) -> RunningTimer:
    return replace(timer, **changes)  # type: ignore[arg-type]
