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
    assert actions == ["Start", "Quit"]
    with qtbot.waitSignal(tray.quit_requested, timeout=1000):
        tray.quit_action.trigger()
    with qtbot.waitSignal(tray.toggle_requested, timeout=1000):
        tray.toggle_action.trigger()
    tray.set_running(True)
    assert tray.toggle_action.text() == "Stop"


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
