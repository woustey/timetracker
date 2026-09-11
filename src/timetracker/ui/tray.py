"""System tray icon and its native context menu (FR-101, FR-103, FR-104, FR-105).

The owner **must** keep a strong reference to :class:`TrayIcon`; a tray icon held
only by a local variable is garbage-collected and vanishes (PRD-02 §8.1).

Activation: ``Trigger`` opens the popover, ``Context`` is handled natively by
the menu, ``MiddleClick`` toggles the timer. No action is reachable *only* via a
non-Trigger reason (GNOME Shell does not deliver them all).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRect, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from timetracker.ui.icons import TrayState, make_icon

_TOOLTIP_IDLE = "Not tracking"


class TrayIcon(QObject):
    """Wraps ``QSystemTrayIcon`` with state handling and the context menu."""

    popover_requested = Signal()
    toggle_requested = Signal()
    add_time_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = TrayState.IDLE
        self._icons = {state: make_icon(state) for state in TrayState}

        # Menu is a real QMenu set via setContextMenu(): native on every platform.
        self._menu = QMenu()
        self._toggle_action = QAction("Start", self._menu)
        self._toggle_action.triggered.connect(self.toggle_requested.emit)
        self._menu.addAction(self._toggle_action)
        self._add_time_action = QAction("Add Time…", self._menu)
        self._add_time_action.triggered.connect(self.add_time_requested.emit)
        self._menu.addAction(self._add_time_action)
        self._menu.addSeparator()
        self._quit_action = QAction("Quit", self._menu)
        self._quit_action.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(self._quit_action)

        self._tray = QSystemTrayIcon(self._icons[self._state], self)
        self._tray.setContextMenu(self._menu)
        self._tray.setToolTip(_TOOLTIP_IDLE)
        self._tray.activated.connect(self._on_activated)

    # -- state ---------------------------------------------------------------

    @property
    def state(self) -> TrayState:
        return self._state

    def set_state(self, state: TrayState, tooltip: str | None = None) -> None:
        self._state = state
        self._tray.setIcon(self._icons[state])
        self._tray.setToolTip(tooltip if tooltip is not None else _TOOLTIP_IDLE)

    def set_tooltip(self, tooltip: str) -> None:
        self._tray.setToolTip(tooltip)

    def set_running(self, running: bool) -> None:
        """Flip the Start/Stop menu item (FR-103)."""
        self._toggle_action.setText("Stop" if running else "Start")

    def geometry(self) -> QRect:
        return self._tray.geometry()

    # -- lifecycle -----------------------------------------------------------

    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    # -- events --------------------------------------------------------------

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.popover_requested.emit()
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            self.toggle_requested.emit()

    # -- test / introspection hooks -----------------------------------------

    @property
    def system_tray_icon(self) -> QSystemTrayIcon:
        return self._tray

    @property
    def menu(self) -> QMenu:
        return self._menu

    @property
    def toggle_action(self) -> QAction:
        return self._toggle_action

    @property
    def add_time_action(self) -> QAction:
        return self._add_time_action

    @property
    def quit_action(self) -> QAction:
        return self._quit_action
