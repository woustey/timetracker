"""Idle detection and the four-way prompt (FR-209, FR-210, FR-211).

Polls the platform :class:`IdleProvider` every 15 s while a timer runs. When
the idle time crosses the threshold, one :class:`IdleSpan` is raised and stays
outstanding until the user answers or the timer is stopped by other means
(superseded). While outstanding and the user is still away, the span keeps
growing; once input resumes it freezes. Suspend/resume from
:class:`PowerMonitor` feeds the same span, so a closed lid and a corridor
conversation get the same dialogue.

The four outcomes are defined in terms of what the user sees, not of what the
monotonic clock did (PRD-02 §6 assumes the clock counts through sleep, which
is only true on Windows):

- **keep**              → accrued ends up *including* the whole away span
- **discard**           → accrued ends up *excluding* it; timer keeps running
- **discard and stop**  → as discard, then stop at the idle start
- **log separately**    → stop at the idle start; the away span becomes its
                          own entry with the same labels and the note ``Idle``
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum

from PySide6.QtCore import QObject, QTimer, Signal

from timetracker.core.clock import Clock
from timetracker.crashlog import log
from timetracker.platform.base import IdleProvider, Unavailable
from timetracker.services.timer_service import TimerService

POLL_MS = 15_000


class IdleOutcome(Enum):
    KEEP = "keep"
    DISCARD = "discard"
    DISCARD_AND_STOP = "discard_and_stop"
    LOG_SEPARATELY = "log_separately"


class IdleSource(Enum):
    INPUT = "input"  # no keyboard/mouse activity
    SUSPEND = "suspend"  # sleep, hibernate, lid, frozen process


@dataclass(frozen=True, slots=True)
class IdleSpan:
    started_at_utc: datetime
    seconds: int  # wall-clock length of the away span, as the user experienced it
    counted_seconds: int  # how much of it the running timer has already accrued
    source: IdleSource
    still_idle: bool

    @property
    def ended_at_utc(self) -> datetime:
        return self.started_at_utc + timedelta(seconds=self.seconds)


class IdleMonitor(QObject):
    prompt_needed = Signal(object)  # IdleSpan — raise the four-way prompt (FR-209)
    span_updated = Signal(object)  # IdleSpan — the outstanding span grew or froze
    resolved = Signal()  # the prompt is no longer needed (answered or superseded)

    def __init__(
        self,
        clock: Clock,
        provider: IdleProvider | Unavailable,
        timer: TimerService,
        *,
        threshold_seconds: int = 600,
        parent: QObject | None = None,
        poll_ms: int = POLL_MS,
    ) -> None:
        super().__init__(parent)
        self._clock = clock
        self._provider = provider
        self._timer_service = timer
        self._threshold = max(0, int(threshold_seconds))
        self._span: IdleSpan | None = None
        self._poll = QTimer(self)
        self._poll.setInterval(poll_ms)
        self._poll.timeout.connect(self.poll)
        timer.state_changed.connect(self._on_timer_state)
        if isinstance(provider, Unavailable):
            log().warning("Idle detection unavailable: %s", provider.reason)
        if timer.is_running:
            self._poll.start()

    # -- queries -------------------------------------------------------------

    @property
    def available(self) -> bool:
        return not isinstance(self._provider, Unavailable)

    @property
    def unavailable_reason(self) -> str | None:
        return self._provider.reason if isinstance(self._provider, Unavailable) else None

    @property
    def outstanding(self) -> IdleSpan | None:
        return self._span

    @property
    def threshold_seconds(self) -> int:
        return self._threshold

    def set_threshold_seconds(self, seconds: int) -> None:
        """0 disables input-idle detection (FR-209); suspend detection stays on."""
        self._threshold = max(0, int(seconds))

    # -- detection -----------------------------------------------------------

    def poll(self) -> None:
        """Read the provider once. Public so tests can drive it without the event loop."""
        if not self._timer_service.is_running:
            return
        now = self._clock.now_utc()
        if self._span is not None:
            self._update_outstanding(now)
            return
        if self._threshold == 0 or isinstance(self._provider, Unavailable):
            return
        try:
            idle = self._provider.seconds_idle()
        except OSError as exc:
            log().warning("Idle provider failed; disabling: %s", exc)
            self._provider = Unavailable(str(exc))
            return
        if idle >= self._threshold:
            seconds = int(idle)
            self._span = IdleSpan(
                started_at_utc=now - timedelta(seconds=seconds),
                seconds=seconds,
                counted_seconds=seconds,
                source=IdleSource.INPUT,
                still_idle=True,
            )
            self.prompt_needed.emit(self._span)

    def on_suspend_resumed(self, away_wall: int, away_mono: int) -> None:
        """FR-211: sleep, hibernation and lock are idle. Fed by :class:`PowerMonitor`."""
        if not self._timer_service.is_running:
            return
        now = self._clock.now_utc()
        if self._span is None:
            self._span = IdleSpan(
                started_at_utc=now - timedelta(seconds=away_wall),
                seconds=away_wall,
                counted_seconds=away_mono,
                source=IdleSource.SUSPEND,
                still_idle=False,
            )
            self.prompt_needed.emit(self._span)
            return
        # A sleep while a prompt is already up extends the outstanding span.
        span = self._span
        self._span = replace(
            span,
            seconds=int((now - span.started_at_utc).total_seconds()),
            counted_seconds=span.counted_seconds + away_mono,
            still_idle=False,
        )
        self.span_updated.emit(self._span)

    def _update_outstanding(self, now: datetime) -> None:
        span = self._span
        assert span is not None
        if not span.still_idle:
            return
        idle = 0.0
        if not isinstance(self._provider, Unavailable):
            try:
                idle = self._provider.seconds_idle()
            except OSError:
                idle = 0.0
        elapsed_since_start = int((now - span.started_at_utc).total_seconds())
        if idle >= self._threshold and idle >= span.seconds:
            # Still away: the span grows, and so does what the timer counted.
            grown = elapsed_since_start - span.seconds
            self._span = replace(
                span, seconds=elapsed_since_start, counted_seconds=span.counted_seconds + grown
            )
        else:
            # Input resumed since the last poll; freeze at the moment it did.
            back_for = int(idle)
            frozen = max(span.seconds, elapsed_since_start - back_for)
            grown = frozen - span.seconds
            self._span = replace(
                span,
                seconds=frozen,
                counted_seconds=span.counted_seconds + grown,
                still_idle=False,
            )
        self.span_updated.emit(self._span)

    # -- resolution (FR-209 outcomes) ----------------------------------------

    def resolve(self, outcome: IdleOutcome) -> None:
        span = self._span
        if span is None:
            return
        svc = self._timer_service
        self._span = None
        if not svc.is_active:
            self.resolved.emit()
            return
        if outcome is IdleOutcome.KEEP:
            svc.adjust_accrued(span.seconds - span.counted_seconds)
        elif outcome is IdleOutcome.DISCARD:
            svc.adjust_accrued(-span.counted_seconds)
        elif outcome is IdleOutcome.DISCARD_AND_STOP:
            svc.adjust_accrued(-span.counted_seconds)
            svc.stop(ended_at_utc=span.started_at_utc)
        elif outcome is IdleOutcome.LOG_SEPARATELY:
            svc.split_idle(span.started_at_utc, span.seconds, span.counted_seconds)
        log().info(
            "Idle span of %d s (%s) resolved: %s", span.seconds, span.source.value, outcome.value
        )
        self.resolved.emit()

    # -- lifecycle -----------------------------------------------------------

    def _on_timer_state(self, state: object) -> None:
        if self._timer_service.is_running:
            self._poll.start()
            return
        self._poll.stop()
        if self._timer_service.is_paused:
            # Nothing accrues while paused, so nothing new to ask about; an
            # outstanding question stays outstanding (FR-210).
            return
        if self._span is not None:
            # Stopped or discarded by other means: the question is moot (superseded).
            self._span = None
            self.resolved.emit()
