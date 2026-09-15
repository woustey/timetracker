"""``QApplication`` subclass: wiring and lifecycle."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QProcess, QTimer, QTimeZone
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from timetracker import __version__, resources
from timetracker.core.clock import Clock, SystemClock
from timetracker.core.duration import format_hm
from timetracker.core.errors import SchemaTooNewError
from timetracker.core.models import Dimension
from timetracker.crashlog import log
from timetracker.data import paths
from timetracker.data.db import connect
from timetracker.data.entry_repo import EntryRepo
from timetracker.data.label_repo import LabelRepo
from timetracker.data.migrate import migrate
from timetracker.data.settings_repo import SettingsRepo
from timetracker.data.timer_repo import TimerRepo
from timetracker.diagnostics import ASSUME_TRAY_ENV
from timetracker.instance_lock import InstanceLock
from timetracker.platform.factory import autostart_provider, idle_provider, launch_command
from timetracker.services.backup_service import BackupService
from timetracker.services.entry_service import EntryService
from timetracker.services.export_service import ExportService
from timetracker.services.idle_monitor import IdleMonitor, IdleOutcome, IdleSpan
from timetracker.services.label_service import LabelService
from timetracker.services.power_monitor import PowerMonitor
from timetracker.services.settings_service import (
    KEY_AUTOSTART_OFFERED,
    KEY_IDLE_THRESHOLD_MIN,
    KEY_LONG_RUNNING_HOURS,
    KEY_THEME,
    KEY_TIME_FORMAT,
    SettingsService,
)
from timetracker.services.timer_service import TimerService, TimerState
from timetracker.ui import formatting
from timetracker.ui.dialogs.first_run import FirstRunDialog
from timetracker.ui.dialogs.idle_prompt import IdlePromptDialog
from timetracker.ui.dialogs.long_running import LongRunningDialog
from timetracker.ui.dialogs.recovery import RecoveryChoice, RecoveryDialog
from timetracker.ui.icons import TrayState
from timetracker.ui.log.window import LogWindow
from timetracker.ui.popover import Popover, PopoverMode
from timetracker.ui.settings_dialog import SettingsDialog
from timetracker.ui.theme import ThemeManager
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
        icon_file = resources.icon_path()
        if icon_file is not None:
            self.setWindowIcon(QIcon(str(icon_file)))

        # Strong references: the tray must outlive every local scope.
        self.tray: TrayIcon | None = None
        self.popover: Popover | None = None
        self.timer_service: TimerService | None = None
        self.label_service: LabelService | None = None
        self.entry_service: EntryService | None = None
        self.settings_service: SettingsService | None = None
        self.idle_monitor: IdleMonitor | None = None
        self.power_monitor: PowerMonitor | None = None
        self.export_service: ExportService | None = None
        self.backup_service: BackupService | None = None
        self.log_window: LogWindow | None = None
        self.settings_dialog: SettingsDialog | None = None
        self.theme = ThemeManager(self, self)
        self._first_run_dialog: FirstRunDialog | None = None
        self._relaunching = False
        self._entry_repo: EntryRepo | None = None
        self.clock: Clock | None = None
        self._conn: sqlite3.Connection | None = None
        self._lock: InstanceLock | None = None
        self._watcher: QFileSystemWatcher | None = None
        self._recovery_dialog: RecoveryDialog | None = None
        self._idle_dialog: IdlePromptDialog | None = None
        self._long_running_dialog: LongRunningDialog | None = None
        self.aboutToQuit.connect(self.shutdown)

    # -- lifecycle -----------------------------------------------------------

    def bootstrap(self, data_dir: Path | None = None) -> bool:
        """Create everything. Returns ``False`` if the app cannot run here."""
        if not QSystemTrayIcon.isSystemTrayAvailable() and not os.environ.get(ASSUME_TRAY_ENV):
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
        self.export_service = ExportService(self.clock, db_file, self)
        self.backup_service = BackupService(self.clock, db_file, conn, self)
        self._entry_repo = entries
        self.theme.apply(self.settings_service.theme)
        formatting.set_twelve_hour(self.settings_service.time_format_12h)

        self.tray = TrayIcon(self)
        self.popover = Popover(
            self.timer_service, self.label_service, self.entry_service, self.settings_service
        )

        self.tray.popover_requested.connect(self.show_popover)
        self.tray.add_time_requested.connect(self.show_add_time)
        self.tray.open_log_requested.connect(self.show_log)
        self.popover.open_log_requested.connect(self.show_log)
        self.tray.settings_requested.connect(self.show_settings)
        self.popover.settings_requested.connect(self.show_settings)
        self.tray.toggle_requested.connect(self.toggle_timer)
        self.tray.quit_requested.connect(self.request_quit)
        self.timer_service.state_changed.connect(self._on_state_changed)
        self.timer_service.ticked.connect(self._on_tick)
        self.timer_service.labels_changed.connect(lambda: self._on_tick(self._elapsed()))
        self.timer_service.long_running.connect(self.offer_long_running)
        self.timer_service.set_long_running_threshold(self.settings_service.long_running_seconds)

        # -- trust: idle + sleep/wake (FR-209–FR-211) ------------------------
        provider = idle_provider()
        self.idle_monitor = IdleMonitor(
            self.clock,
            provider,
            self.timer_service,
            threshold_seconds=self.settings_service.idle_threshold_seconds,
            parent=self,
        )
        self.idle_monitor.prompt_needed.connect(self.offer_idle_prompt)
        self.idle_monitor.span_updated.connect(self._on_idle_span_updated)
        self.idle_monitor.resolved.connect(self._on_idle_resolved)
        self.power_monitor = PowerMonitor(self.clock, self)
        self.power_monitor.resumed_from_suspend.connect(self.idle_monitor.on_suspend_resumed)
        self.power_monitor.start()
        self.settings_service.setting_changed.connect(self._on_setting_changed)
        log().info("Idle provider: %s", getattr(provider, "name", provider))

        self._watcher = QFileSystemWatcher([str(directory)], self)
        self._watcher.directoryChanged.connect(self._on_data_dir_changed)

        self.tray.show()
        self._on_state_changed(self.timer_service.state)

        if self.timer_service.pending_recovery is not None:
            self.tray.set_state(TrayState.ATTENTION, "Unsaved session recovered — click to resolve")
            QTimer.singleShot(0, self.offer_recovery)
        elif not self.settings_service.autostart_offered:
            QTimer.singleShot(400, self.offer_first_run)  # once, after the tray is up
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
        if self.power_monitor is not None:
            self.power_monitor.stop()
            self.power_monitor = None
        self.idle_monitor = None
        for dialog in (self._idle_dialog, self._long_running_dialog):
            if dialog is not None:
                dialog.close()
        self._idle_dialog = None
        self._long_running_dialog = None
        if self.log_window is not None:
            self.log_window.close()
            self.log_window = None
        if self.settings_dialog is not None:
            self.settings_dialog.close()
            self.settings_dialog = None
        if self._first_run_dialog is not None:
            self._first_run_dialog.close()
            self._first_run_dialog = None
        self.export_service = None
        self.backup_service = None
        self._entry_repo = None
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
        if self.idle_monitor is not None and self.idle_monitor.outstanding is not None:
            self.offer_idle_prompt(self.idle_monitor.outstanding)  # FR-210: reachable from the tray
            return
        if self.popover.isVisible():
            self.popover.hide()
            return
        self.popover.show_near(self.tray.geometry())

    def show_log(self) -> None:
        """FR-103 *Open log…*: one window, re-raised if already open."""
        if self.log_window is None:
            if (
                self.clock is None
                or self._entry_repo is None
                or self.entry_service is None
                or self.label_service is None
                or self.settings_service is None
                or self.export_service is None
            ):
                return
            self.log_window = LogWindow(
                self.clock,
                self._entry_repo,
                self.entry_service,
                self.label_service,
                self.settings_service,
                self.export_service,
            )
            self.log_window.closed.connect(self._on_log_closed)
        self.log_window.show()
        self.log_window.raise_()
        self.log_window.activateWindow()

    def show_settings(self) -> None:
        """FR-103 *Settings…*: one dialog, re-raised if already open."""
        if self.settings_dialog is None:
            if (
                self.settings_service is None
                or self.label_service is None
                or self.backup_service is None
            ):
                return
            dialog = SettingsDialog(
                self.settings_service,
                self.label_service,
                self.backup_service,
                self.idle_monitor,
                autostart_provider(),
            )
            dialog.theme_changed.connect(self.theme.apply)
            dialog.relaunch_requested.connect(self.relaunch)
            dialog.finished.connect(lambda _code: setattr(self, "settings_dialog", None))
            self.settings_dialog = dialog
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def offer_first_run(self) -> None:
        """NFR-09 / FR-409 / FR-108: one welcome screen, once; then the popover opens itself."""
        if self.settings_service is None or self._first_run_dialog is not None:
            return
        provider = autostart_provider()
        self.settings_service.set(KEY_AUTOSTART_OFFERED, True)
        dialog = FirstRunDialog(autostart_available=hasattr(provider, "set_enabled"))

        def finished(names: list[str], start_at_login: bool) -> None:
            if self.label_service is not None:
                for name in names:
                    self.label_service.get_or_create(Dimension.CLIENT, name)
            if start_at_login and hasattr(provider, "set_enabled"):
                try:
                    provider.set_enabled(True, launch_command())
                except OSError as exc:
                    log().warning("Could not enable start at login: %s", exc)
            QTimer.singleShot(150, self.show_popover)

        dialog.finished_setup.connect(finished)
        dialog.finished.connect(lambda _code: setattr(self, "_first_run_dialog", None))
        self._first_run_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def relaunch(self) -> None:
        """After a restore: release everything, start a fresh process, quit this one."""
        if self._relaunching:
            return
        self._relaunching = True
        self.shutdown()
        command = launch_command()
        QProcess.startDetached(command[0], command[1:])
        self.quit()

    def _on_log_closed(self) -> None:
        if self.log_window is not None:
            self.log_window.deleteLater()
            self.log_window = None

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

    # -- idle prompt (FR-209/FR-210) -----------------------------------------

    def offer_idle_prompt(self, span: IdleSpan) -> None:
        if self.clock is None or self.idle_monitor is None:
            return
        if self._idle_dialog is not None:
            self._idle_dialog.update_span(span)
            self._idle_dialog.show()
            self._idle_dialog.raise_()
            self._idle_dialog.activateWindow()
            return
        dialog = IdlePromptDialog(span, self.clock.tz_name())
        dialog.answered.connect(self._on_idle_answered)
        dialog.finished.connect(lambda _code: self._on_idle_dialog_closed(dialog))
        self._idle_dialog = dialog
        self._refresh_attention()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _on_idle_span_updated(self, span: IdleSpan) -> None:
        if self._idle_dialog is not None:
            self._idle_dialog.update_span(span)
        self._refresh_attention()

    def _on_idle_answered(self, outcome: IdleOutcome) -> None:
        if self.idle_monitor is not None:
            self.idle_monitor.resolve(outcome)

    def _on_idle_dialog_closed(self, dialog: IdlePromptDialog) -> None:
        if self._idle_dialog is dialog:
            self._idle_dialog = None
        # Closed without answering: the span stays outstanding (FR-210); the tray
        # keeps the attention state until it is answered or superseded.
        self._refresh_attention()

    def _on_idle_resolved(self) -> None:
        if self._idle_dialog is not None:
            dialog, self._idle_dialog = self._idle_dialog, None
            dialog.close()
        self._refresh_attention()

    def _refresh_attention(self) -> None:
        if self.tray is None or self.timer_service is None:
            return
        if self.timer_service.pending_recovery is not None:
            return
        span = self.idle_monitor.outstanding if self.idle_monitor is not None else None
        if span is not None and self.timer_service.is_running:
            self.tray.set_state(
                TrayState.ATTENTION, f"Away for {format_hm(span.seconds)} — click to resolve"
            )
        else:
            self._on_state_changed(self.timer_service.state)

    # -- long-running prompt (PRD-01 §10) --------------------------------------

    def offer_long_running(self, elapsed: int) -> None:
        svc = self.timer_service
        if svc is None or not svc.is_running:
            return
        if self._long_running_dialog is not None:
            self._long_running_dialog.raise_()
            return
        dialog = LongRunningDialog(elapsed, svc.started_local_time())
        dialog.stop_requested.connect(lambda: svc.stop() if svc.is_running else None)
        dialog.finished.connect(lambda _code: setattr(self, "_long_running_dialog", None))
        self._long_running_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _on_setting_changed(self, key: str) -> None:
        if self.settings_service is None:
            return
        if key == KEY_IDLE_THRESHOLD_MIN and self.idle_monitor is not None:
            self.idle_monitor.set_threshold_seconds(self.settings_service.idle_threshold_seconds)
        elif key == KEY_LONG_RUNNING_HOURS and self.timer_service is not None:
            self.timer_service.set_long_running_threshold(
                self.settings_service.long_running_seconds
            )
        elif key == KEY_THEME:
            self.theme.apply(self.settings_service.theme)
        elif key == KEY_TIME_FORMAT:
            formatting.set_twelve_hour(self.settings_service.time_format_12h)
            if self.popover is not None:
                self.popover.refresh()

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
            and self.tray.state is not TrayState.ATTENTION
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
