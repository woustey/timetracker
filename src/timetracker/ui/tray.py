"""System tray icon and its native context menu (FR-101, FR-103, FR-104, FR-105).

The owner **must** keep a strong reference to :class:`TrayIcon`; a tray icon held
only by a local variable is garbage-collected and vanishes (PRD-02 §8.1).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from timetracker.ui.icons import TrayState, make_icon

_TOOLTIP_IDLE = "Not tracking"


class TrayIcon(QObject):
    """Wraps ``QSystemTrayIcon`` with state handling and the context menu."""

    quit_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = TrayState.IDLE
        self._icons = {state: make_icon(state) for state in TrayState}

        # Menu is a real QMenu set via setContextMenu(): native on every platform.
        self._menu = QMenu()
        self._quit_action = QAction("Quit", self._menu)
        self._quit_action.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(self._quit_action)

        self._tray = QSystemTrayIcon(self._icons[self._state], self)
        self._tray.setContextMenu(self._menu)
        self._tray.setToolTip(_TOOLTIP_IDLE)

    # -- state ---------------------------------------------------------------

    @property
    def state(self) -> TrayState:
        return self._state

    def set_state(self, state: TrayState, tooltip: str | None = None) -> None:
        self._state = state
        self._tray.setIcon(self._icons[state])
        self._tray.setToolTip(tooltip if tooltip is not None else _TOOLTIP_IDLE)

    # -- lifecycle -----------------------------------------------------------

    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    # -- test / introspection hooks -----------------------------------------

    @property
    def system_tray_icon(self) -> QSystemTrayIcon:
        return self._tray

    @property
    def menu(self) -> QMenu:
        return self._menu

    @property
    def quit_action(self) -> QAction:
        return self._quit_action
