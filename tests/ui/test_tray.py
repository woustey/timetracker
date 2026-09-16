"""Tray behaviour: icon per state, menu, clean quit, no GC bug, state follows the timer."""

from __future__ import annotations

import gc
from pathlib import Path

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox, QSystemTrayIcon

from timetracker.ui.icons import TrayState, make_icon
from timetracker.ui.tray import TrayIcon


@pytest.mark.parametrize("state", list(TrayState))
def test_icons_render_for_every_state(qapp, state: TrayState) -> None:  # type: ignore[no-untyped-def]
    icon = make_icon(state)
    assert not icon.isNull()
    for size in (16, 22, 32):
        pm = icon.pixmap(size, size)
        assert not pm.isNull()
        assert pm.width() == size


def test_menu_has_start_stop_and_quit(qapp, qtbot) -> None:  # type: ignore[no-untyped-def]
    tray = TrayIcon()
    actions = [a.text() for a in tray.menu.actions() if not a.isSeparator()]
    assert actions == ["Start", "Pause", "Add Time…", "Open log…", "Settings…", "Quit"]
    assert not tray.pause_action.isVisible()  # FR-212: only while a timer is active
    with qtbot.waitSignal(tray.settings_requested, timeout=1000):
        tray.settings_action.trigger()
    with qtbot.waitSignal(tray.open_log_requested, timeout=1000):
        tray.open_log_action.trigger()
    with qtbot.waitSignal(tray.add_time_requested, timeout=1000):
        tray.add_time_action.trigger()
    with qtbot.waitSignal(tray.quit_requested, timeout=1000):
        tray.quit_action.trigger()
    with qtbot.waitSignal(tray.toggle_requested, timeout=1000):
        tray.toggle_action.trigger()
    tray.set_running(True)
    assert tray.toggle_action.text() == "Stop"
    assert tray.pause_action.isVisible() and tray.pause_action.text() == "Pause"
    tray.set_running(True, paused=True)
    assert tray.pause_action.text() == "Resume"
    with qtbot.waitSignal(tray.pause_toggle_requested, timeout=1000):
        tray.pause_action.trigger()
    tray.set_running(False)
    assert not tray.pause_action.isVisible()


def test_activation_reasons(qapp, qtbot) -> None:  # type: ignore[no-untyped-def]
    tray = TrayIcon()
    with qtbot.waitSignal(tray.popover_requested, timeout=1000):
        tray.system_tray_icon.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
    with qtbot.waitSignal(tray.toggle_requested, timeout=1000):
        tray.system_tray_icon.activated.emit(QSystemTrayIcon.ActivationReason.MiddleClick)


def test_set_state_changes_tooltip(qapp) -> None:  # type: ignore[no-untyped-def]
    tray = TrayIcon()
    assert tray.system_tray_icon.toolTip() == "Not tracking"
    tray.set_state(TrayState.RUNNING, "1:23 · Meeting/Call · ASICS")
    assert tray.state is TrayState.RUNNING
    assert tray.system_tray_icon.toolTip() == "1:23 · Meeting/Call · ASICS"
    tray.set_state(TrayState.IDLE)
    assert tray.system_tray_icon.toolTip() == "Not tracking"


def test_bootstrap_refuses_without_tray(
    qapp, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    shown: list[str] = []
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: False))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: shown.append(a[1])))
    assert qapp.bootstrap(tmp_path) is False
    assert shown == ["No system tray available"]
    assert qapp.tray is None


def test_bootstrap_keeps_strong_reference_and_quits_cleanly(booted_app) -> None:  # type: ignore[no-untyped-def]
    qapp = booted_app
    tray = qapp.tray
    assert tray is not None

    # The classic bug: tray held only by a local in bootstrap(), collected on return.
    gc.collect()
    assert qapp.tray is tray
    assert tray.system_tray_icon.parent() is tray

    # Quit from the menu must end the event loop.
    timed_out: list[bool] = []
    guard = QTimer()
    guard.setSingleShot(True)
    guard.timeout.connect(lambda: (timed_out.append(True), qapp.quit()))
    guard.start(3000)
    QTimer.singleShot(0, tray.quit_action.trigger)
    qapp.exec()
    guard.stop()
    assert not timed_out, "Quit action did not stop the event loop"


def test_tray_follows_timer_state(booted_app) -> None:  # type: ignore[no-untyped-def]
    app = booted_app
    tray, svc, labels = app.tray, app.timer_service, app.label_service
    from timetracker.core.models import Dimension

    nike = labels.get_or_create(Dimension.CLIENT, "Nike")
    work = labels.get_or_create(Dimension.TYPE, "Work")
    assert tray.state is TrayState.IDLE
    svc.start(nike.id, work.id)
    assert tray.state is TrayState.RUNNING
    assert tray.system_tray_icon.toolTip() == "0:00 · Work · Nike"
    assert tray.toggle_action.text() == "Stop"
    app.toggle_timer()  # middle-click / menu path
    assert tray.state is TrayState.IDLE
    assert tray.system_tray_icon.toolTip() == "Not tracking"
    assert tray.toggle_action.text() == "Start"


def test_idle_prompt_sets_attention_and_tray_click_raises_it(booted_app, qtbot) -> None:  # type: ignore[no-untyped-def]

    app = booted_app
    svc, monitor, tray = app.timer_service, app.idle_monitor, app.tray
    assert monitor is not None
    svc.start()
    monitor.on_suspend_resumed(1800, 1800)  # what PowerMonitor reports after a 30-min sleep
    qtbot.waitUntil(lambda: app._idle_dialog is not None, timeout=1000)  # noqa: SLF001
    assert tray.state is TrayState.ATTENTION
    assert tray.system_tray_icon.toolTip() == "Away for 0:30 — click to resolve"
    dialog = app._idle_dialog  # noqa: SLF001
    assert "asleep for 0:30:00" in dialog.summary.text()

    # Closing without answering keeps it outstanding; a tray click brings it back.
    dialog.reject()
    assert app._idle_dialog is None  # noqa: SLF001
    assert monitor.outstanding is not None
    assert tray.state is TrayState.ATTENTION
    app.show_popover()
    assert app._idle_dialog is not None  # noqa: SLF001
    assert app.popover is not None and not app.popover.isVisible()

    app._idle_dialog.discard.click()  # noqa: SLF001
    assert monitor.outstanding is None
    assert tray.state is TrayState.RUNNING
    assert svc.elapsed_seconds() == 0
    svc.stop()


def test_fr212_tray_pause_and_resume(booted_app) -> None:  # type: ignore[no-untyped-def]
    app = booted_app
    tray, svc = app.tray, app.timer_service
    svc.start()
    app.toggle_pause()
    assert svc.is_paused
    assert tray.state is TrayState.PAUSED
    assert tray.system_tray_icon.toolTip() == "Paused · 0:00"
    assert tray.pause_action.text() == "Resume"
    assert tray.toggle_action.text() == "Stop"
    app.toggle_pause()
    assert svc.is_running
    assert tray.state is TrayState.RUNNING
    assert tray.pause_action.text() == "Pause"
    app.toggle_pause()
    app.toggle_timer()  # Stop from the tray while paused
    assert tray.state is TrayState.IDLE
    assert not tray.pause_action.isVisible()


def test_fr212_pause_with_an_outstanding_idle_prompt_raises_the_prompt(booted_app, qtbot) -> None:  # type: ignore[no-untyped-def]
    app = booted_app
    svc, monitor = app.timer_service, app.idle_monitor
    svc.start()
    monitor.on_suspend_resumed(1800, 1800)
    qtbot.waitUntil(lambda: app._idle_dialog is not None, timeout=1000)  # noqa: SLF001
    app._idle_dialog.reject()  # noqa: SLF001
    app.toggle_pause()
    assert app._idle_dialog is not None  # noqa: SLF001 - the question comes first (FR-210)
    assert svc.is_running and not svc.is_paused
    app._idle_dialog.discard.click()  # noqa: SLF001
    svc.stop()


def test_fr702_reminder_shows_a_balloon_and_a_click_opens_the_popover(
    booted_app,
) -> None:  # type: ignore[no-untyped-def]
    app = booted_app
    tray, reminders = app.tray, app.reminder_service
    assert reminders is not None and not reminders.polling  # off by default
    assert tray.last_message is None
    reminders.reminder_due.emit(125)  # what the service raises after 2 h 05 of quiet
    assert tray.last_message == (
        "Nothing is being tracked",
        "No timer or entry for 2:05. Click to open Time Tracker.",
    )
    tray.system_tray_icon.messageClicked.emit()
    assert app.popover is not None and app.popover.isVisible()
    app.popover.hide()
