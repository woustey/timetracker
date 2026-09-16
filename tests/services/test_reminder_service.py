"""ReminderService (FR-702) under a fake clock: working window, quiet period, repeat, activity."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from timetracker.core.clock import FakeClock
from timetracker.services.entry_service import EntryService
from timetracker.services.reminder_service import ReminderService
from timetracker.services.settings_service import (
    KEY_REMINDER_DAYS,
    KEY_REMINDER_ENABLED,
    KEY_REMINDER_END,
    KEY_REMINDER_MINUTES,
    KEY_REMINDER_START,
    SettingsService,
)
from timetracker.services.timer_service import TimerService

# The shared clock is Fri 11 Sep 2026 10:00 UTC = 12:00 Brussels (CEST).


@pytest.fixture
def reminders(
    qapp,
    clock: FakeClock,
    settings_service: SettingsService,
    service: TimerService,
    entry_service: EntryService,
) -> ReminderService:  # type: ignore[no-untyped-def]
    settings_service.set(KEY_REMINDER_ENABLED, True)
    settings_service.set(KEY_REMINDER_MINUTES, 30)
    return ReminderService(clock, settings_service, service, entry_service)


def test_off_by_default(
    qapp,
    clock: FakeClock,
    settings_service: SettingsService,
    service: TimerService,
    entry_service: EntryService,
) -> None:  # type: ignore[no-untyped-def]
    svc = ReminderService(clock, settings_service, service, entry_service)
    assert not settings_service.reminders_enabled
    assert not svc.polling
    clock.advance(3 * 3600)
    assert svc.check() is False


def test_quiet_period_counts_from_launch_then_repeats(
    reminders: ReminderService, clock: FakeClock, qtbot
) -> None:  # type: ignore[no-untyped-def]
    assert reminders.polling
    clock.advance(29 * 60)
    assert reminders.check() is False
    clock.advance(60)
    with qtbot.waitSignal(reminders.reminder_due, timeout=1000) as blocker:
        assert reminders.check() is True
    assert blocker.args == [30]
    assert reminders.check() is False  # not again in the same minute
    clock.advance(30 * 60)
    with qtbot.waitSignal(reminders.reminder_due, timeout=1000) as blocker:
        assert reminders.check() is True
    assert blocker.args == [60]  # quiet since launch, not since the last reminder


def test_timer_and_entries_are_activity_and_a_live_timer_silences(
    reminders: ReminderService, service: TimerService, entry_service: EntryService, clock: FakeClock
) -> None:
    clock.advance(25 * 60)
    service.start()
    clock.advance(60 * 60)
    assert reminders.check() is False  # running
    service.pause()
    clock.advance(60 * 60)
    assert reminders.check() is False  # paused is still a live timer
    service.resume()
    service.stop()  # activity
    clock.advance(29 * 60)
    assert reminders.check() is False
    entry_service.add_quick(900, None, None, None)  # activity
    clock.advance(29 * 60)
    assert reminders.check() is False
    clock.advance(60)
    assert reminders.check() is True


def test_outside_working_hours_and_days_is_silent(
    reminders: ReminderService, settings_service: SettingsService, clock: FakeClock
) -> None:
    clock.advance(6 * 3600)  # 18:00 Brussels — after the 17:00 default end
    assert reminders.check() is False
    settings_service.set(KEY_REMINDER_END, "20:00")
    assert reminders.check() is True
    settings_service.set(KEY_REMINDER_DAYS, [0, 1, 2, 3])  # not Friday
    clock.advance(60 * 60)
    assert reminders.check() is False


def test_window_start_resets_the_quiet_period(
    reminders: ReminderService, settings_service: SettingsService, clock: FakeClock
) -> None:
    """Quiet time before 09:00 does not count: the first reminder of the day comes at 09:30."""
    settings_service.set(KEY_REMINDER_START, "09:00")
    # Jump to Monday 14 Sep 2026 08:59 Brussels (06:59 UTC) — nothing since Friday.
    target = datetime(2026, 9, 14, 6, 59, tzinfo=UTC)
    clock.advance((target - clock.now_utc()).total_seconds())
    assert reminders.check() is False
    clock.advance(60)  # 09:00
    assert reminders.check() is False
    clock.advance(29 * 60)  # 09:29
    assert reminders.check() is False
    clock.advance(60)  # 09:30
    assert reminders.check() is True


def test_toggling_the_setting_starts_and_stops_polling(
    reminders: ReminderService, settings_service: SettingsService, clock: FakeClock
) -> None:
    settings_service.set(KEY_REMINDER_ENABLED, False)
    assert not reminders.polling
    clock.advance(2 * 3600)
    assert reminders.check() is False
    settings_service.set(KEY_REMINDER_ENABLED, True)
    assert reminders.polling
    assert reminders.check() is False  # switching it on counts as activity
    clock.advance(30 * 60)
    assert reminders.check() is True
