"""Opt-in "nothing is being tracked" reminders (FR-702, v1.1).

Off by default. When on, and only inside the configured working days and
hours, a passive notification is raised once nothing has happened for *N*
minutes: no timer running or paused, no timer started or stopped, no entry
added or edited. The quiet period is counted from the later of the last such
activity and the start of today's working window, so 09:00 sharp never nags;
while the quiet continues, the reminder repeats every *N* minutes.

The check runs on a 60 s ``QTimer``; :meth:`check` is public so tests drive it
under a ``FakeClock``. Nothing here pops a window — the app shows the tray
balloon (NFR: passive, dismissable) and a click on it opens the popover.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from PySide6.QtCore import QObject, QTimer, Signal

from timetracker.core.clock import Clock
from timetracker.core.timeutil import zone
from timetracker.services.entry_service import EntryService
from timetracker.services.settings_service import (
    KEY_REMINDER_DAYS,
    KEY_REMINDER_ENABLED,
    KEY_REMINDER_END,
    KEY_REMINDER_MINUTES,
    KEY_REMINDER_START,
    SettingsService,
)
from timetracker.services.timer_service import TimerService

CHECK_MS = 60_000


class ReminderService(QObject):
    reminder_due = Signal(int)  # quiet minutes so far

    def __init__(
        self,
        clock: Clock,
        settings: SettingsService,
        timer: TimerService,
        entries: EntryService,
        parent: QObject | None = None,
        *,
        check_ms: int = CHECK_MS,
    ) -> None:
        super().__init__(parent)
        self._clock = clock
        self._settings = settings
        self._timer = timer
        self._last_activity = clock.now_utc()  # launching the app counts
        self._last_reminded: datetime | None = None

        timer.state_changed.connect(self._on_activity)
        entries.entries_changed.connect(self._on_activity)
        settings.setting_changed.connect(self._on_setting_changed)

        self._check = QTimer(self)
        self._check.setInterval(check_ms)
        self._check.timeout.connect(self.check)
        if settings.reminders_enabled:
            self._check.start()

    # -- queries -------------------------------------------------------------

    @property
    def last_activity_utc(self) -> datetime:
        return self._last_activity

    @property
    def polling(self) -> bool:
        return self._check.isActive()

    # -- the check -----------------------------------------------------------

    def check(self) -> bool:
        """Raise the reminder if it is due. Returns whether it was."""
        if not self._settings.reminders_enabled or self._timer.is_active:
            return False
        now = self._clock.now_utc()
        local = now.astimezone(zone(self._clock.tz_name()))
        window_start = self._window_start(local)
        if window_start is None:
            return False
        quiet_since = max(self._last_activity, window_start)
        if self._last_reminded is not None:
            quiet_since = max(quiet_since, self._last_reminded)
        threshold = timedelta(minutes=self._settings.reminder_minutes)
        if now - quiet_since < threshold:
            return False
        self._last_reminded = now
        self.reminder_due.emit(int((now - self._last_activity).total_seconds() // 60))
        return True

    def _window_start(self, local: datetime) -> datetime | None:
        """Start of today's working window (UTC) if *local* lies inside it, else ``None``."""
        if local.weekday() not in self._settings.reminder_days:
            return None
        start: time = self._settings.reminder_start
        end: time = self._settings.reminder_end
        if not start <= local.time() < end:
            return None
        window = local.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
        return window.astimezone(UTC)

    # -- signals -------------------------------------------------------------

    def _on_activity(self, *_: object) -> None:
        self._last_activity = self._clock.now_utc()
        self._last_reminded = None

    def _on_setting_changed(self, key: str) -> None:
        if key not in (
            KEY_REMINDER_ENABLED,
            KEY_REMINDER_MINUTES,
            KEY_REMINDER_DAYS,
            KEY_REMINDER_START,
            KEY_REMINDER_END,
        ):
            return
        self._last_reminded = None
        if self._settings.reminders_enabled:
            if not self._check.isActive():
                self._last_activity = self._clock.now_utc()  # switching it on is activity
                self._check.start()
        else:
            self._check.stop()
