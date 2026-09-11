"""``QApplication`` subclass: wiring and lifecycle."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QTimer, QTimeZone
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from timetracker import __version__
from timetracker.core.clock import Clock, SystemClock
from timetracker.core.duration import format_hm
from timetracker.core.errors import SchemaTooNewError
from timetracker.core.models import Dimension
from timetracker.data import paths
from timetracker.data.db import connect
from timetracker.data.entry_repo import EntryRepo
from timetracker.data.label_repo import LabelRepo
from timetracker.data.migrate import migrate
from timetracker.data.settings_repo import SettingsRepo
from timetracker.data.timer_repo import TimerRepo
from timetracker.instance_lock import InstanceLock
from timetracker.services.entry_service import EntryService
from timetracker.services.label_service import LabelService
from timetracker.services.settings_service import SettingsService
from timetracker.services.timer_service import TimerService, TimerState
from timetracker.ui.dialogs.recovery import RecoveryChoice, RecoveryDialog
from timetracker.ui.icons import TrayState
from timetracker.ui.popover import Popover, PopoverMode
from timetracker.ui.tray import TrayIcon

_NO_TRAY_TEXT = (
    "Time Tracker lives in the system tray, and this desktop session does not "
    "provide one.\n\nA windowed fallback mode is planned; for now the application "
    "cannot start here."
)


def system_tz_name() -> str:
    """IANA zone via Qt, which maps Windows zone names correctly (stdlib cannot)."""
    ident = bytes(QTimeZone.systemTimeZoneId().data()).decode("ascii", "replace")
    return ident or "UTC"


class App(QApplication):
    def __init__(self, argv: list[str]) -> None:
        super().__init__(argv)
        self.setApplicationName("Time Tracker")
        self.setApplicationVersion(__version__)
        self.setOrganizationName("timetracker")
        # Otherwise closing any window kills a tray app (PRD-02 §8.1).
        self.setQuitOnLastWindowClosed(False)

        # Strong references: the tray must outlive every local scope.
        self.tray: TrayIcon | None = None
        self.popover: Popover | None = None
        self.timer_service: TimerService | None = None
        self.label_service: LabelService | None = None
        self.entry_service: EntryService | None = None
        self.settings_service: SettingsService | None = None
        self.clock: Clock | None = None
        self._conn: sqlite3.Connection | None = None
        self._lock: InstanceLock | None = None
        self._watcher: QFileSystemWatcher | None = None
        self._recovery_dialog: RecoveryDialog | None = None
        self.aboutToQuit.connect(self.shutdown)

    # -- lifecycle -----------------------------------------------------------

    def bootstrap(self, data_dir: Path | None = None) -> bool:
        """Create everything. Returns ``False`` if the app cannot run here."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(None, "No system tray available", _NO_TRAY_TEXT)
            return False

        directory = data_dir or paths.data_dir()
        directory.mkdir(parents=True, exist_ok=True)

        lock = InstanceLock(directory)
        if not lock.acquire():
            # FR-107: surface the running instance and leave.
            lock.request_show()
            return False
        self._lock = lock

        db_file = directory / paths.DB_FILENAME
        self.clock = SystemClock(tz_name=system_tz_name())
        conn = connect(db_file)
        try:
            migrate(conn, db_file, clock=self.clock)
        except SchemaTooNewError as exc:
            conn.close()
            lock.release()
            QMessageBox.critical(None, "Database is newer than this version", str(exc))
            return False
        self._conn = conn

        clients = LabelRepo(conn, Dimension.CLIENT, self.clock)
        types = LabelRepo(conn, Dimension.TYPE, self.clock)
        entries = EntryRepo(conn, self.clock)
        timers = TimerRepo(conn)

        self.label_service = LabelService(clients, types, self)
        self.label_service.ensure_seed_types()  # FR-409
        self.settings_service = SettingsService(SettingsRepo(conn), self)
        self.timer_service = TimerService(self.clock, timers, entries, clients, types, self)
        self.entry_service = EntryService(
            self.clock, entries, clients, types, self.settings_service, self
        )

        self.tray = TrayIcon(self)
        self.popover = Popover(
            self.timer_service, self.label_service, self.entry_service, self.settings_service
        )

        self.tray.popover_requested.connect(self.show_popover)
        self.tray.add_time_requested.connect(self.show_add_time)
        self.tray.toggle_requested.connect(self.toggle_timer)
        self.tray.quit_requested.connect(self.request_quit)
        self.timer_service.state_changed.connect(self._on_state_changed)
        self.timer_service.ticked.connect(self._on_tick)
        self.timer_service.labels_changed.connect(lambda: self._on_tick(self._elapsed()))

        self._watcher = QFileSystemWatcher([str(directory)], self)
        self._watcher.directoryChanged.connect(self._on_data_dir_changed)

        self.tray.show()
        self._on_state_changed(self.timer_service.state)

        if self.timer_service.pending_recovery is not None:
            self.tray.set_state(TrayState.ATTENTION, "Unsaved session recovered — click to resolve")
            QTimer.singleShot(0, self.offer_recovery)
        return True

    def shutdown(self) -> None:
        """Release the lock and the connection. Safe to call more than once."""
        if self.popover is not None:
            self.popover.hide()
        if self.tray is not None:
            self.tray.hide()
        if self._watcher is not None:
            self._watcher.deleteLater()
            self._watcher = None
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        if self._lock is not None:
            self._lock.release()
            self._lock = None
        self.tray = None
        self.popover = None
        self.timer_service = None
        self.label_service = None
        self.entry_service = None
        self.settings_service = None

    # -- actions -------------------------------------------------------------

    def show_popover(self) -> None:
        if self.popover is None or self.tray is None:
            return
        if self.timer_service is not None and self.timer_service.pending_recovery is not None:
            self.offer_recovery()
            return
        if self.popover.isVisible():
            self.popover.hide()
            return
        self.popover.show_near(self.tray.geometry())

    def show_add_time(self) -> None:
        """FR-103 *Add Time…*: open the popover straight onto the matrix."""
        if self.popover is None or self.tray is None:
            return
        if self.timer_service is not None and self.timer_service.pending_recovery is not None:
            self.offer_recovery()
            return
        self.popover.set_mode(PopoverMode.MATRIX)
        if not self.popover.isVisible():
            self.popover.show_near(self.tray.geometry())

    def toggle_timer(self) -> None:
        svc = self.timer_service
        if svc is None or svc.pending_recovery is not None:
            return
        if svc.is_running:
            svc.stop()
        else:
            client_id, type_id = svc.default_labels()
            svc.start(client_id, type_id)

    def offer_recovery(self) -> None:
        svc = self.timer_service
        if svc is None or svc.pending_recovery is None or self.label_service is None:
            return
        if self._recovery_dialog is not None:
            self._recovery_dialog.raise_()
            self._recovery_dialog.activateWindow()
            return
        offer = svc.pending_recovery
        client = self._label_name(Dimension.CLIENT, offer.timer.client_id)
        type_ = self._label_name(Dimension.TYPE, offer.timer.type_id)
        dialog = RecoveryDialog(offer, client, type_)
        self._recovery_dialog = dialog
        dialog.finished.connect(lambda _code: self._resolve_recovery(dialog))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _resolve_recovery(self, dialog: RecoveryDialog) -> None:
        self._recovery_dialog = None
        svc = self.timer_service
        if svc is None or svc.pending_recovery is None:
            return
        if dialog.result() == RecoveryDialog.DialogCode.Accepted and (
            dialog.choice is RecoveryChoice.RECOVER
        ):
            svc.recover()
        elif dialog.result() == RecoveryDialog.DialogCode.Accepted:
            svc.discard_recovery()
        else:
            # Closed without choosing: keep offering (FR-210 spirit — never lose it silently).
            return
        self._on_state_changed(svc.state)

    def request_quit(self) -> None:
        """FR-111: with a timer running, ask before quitting."""
        svc = self.timer_service
        if svc is None or not svc.is_running:
            self.quit()
            return
        box = QMessageBox()
        box.setWindowTitle("A timer is running")
        box.setText(
            f"The timer has been running for {format_hm(svc.elapsed_seconds())}. "
            "What should happen to it?"
        )
        stop_save = box.addButton("Stop and save", QMessageBox.ButtonRole.AcceptRole)
        keep = box.addButton("Keep running", QMessageBox.ButtonRole.RejectRole)
        discard = box.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(stop_save)
        box.setEscapeButton(keep)
        box.exec()
        clicked = box.clickedButton()
        if clicked is stop_save:
            svc.stop()
            self.quit()
        elif clicked is discard:
            svc.discard()
            self.quit()
        # "Keep running" — the app stays in the tray with the timer untouched.

    # -- signal handlers -----------------------------------------------------

    def _on_state_changed(self, state: TimerState) -> None:
        if self.tray is None or self.timer_service is None:
            return
        running = state is TimerState.RUNNING
        self.tray.set_running(running)
        if self.timer_service.pending_recovery is not None:
            return
        if running:
            self.tray.set_state(TrayState.RUNNING, self._tooltip())
        else:
            self.tray.set_state(TrayState.IDLE)

    def _on_tick(self, _seconds: int) -> None:
        if (
            self.tray is not None
            and self.timer_service is not None
            and self.timer_service.is_running
        ):
            self.tray.set_tooltip(self._tooltip())

    def _on_data_dir_changed(self, _path: str) -> None:
        if self._lock is not None and self._lock.consume_show_request():
            self.show_popover()

    # -- helpers -------------------------------------------------------------

    def _elapsed(self) -> int:
        return self.timer_service.elapsed_seconds() if self.timer_service else 0

    def _tooltip(self) -> str:
        svc = self.timer_service
        if svc is None or svc.running is None:
            return "Not tracking"
        parts = [format_hm(svc.elapsed_seconds())]
        type_name = self._label_name(Dimension.TYPE, svc.running.type_id)
        client_name = self._label_name(Dimension.CLIENT, svc.running.client_id)
        parts.extend(p for p in (type_name, client_name) if p)
        return " · ".join(parts)

    def _label_name(self, dimension: Dimension, label_id: int | None) -> str | None:
        if label_id is None or self.label_service is None:
            return None
        return self.label_service.get(dimension, label_id).name
