"""Settings dialog (FR-701, FR-703; FR-108; FR-404/405; FR-802/804; PRD-02 §10).

Every control writes through ``SettingsService`` immediately (no OK/Apply
dance) so a change is visible in the running app at once. Tabs:

- **General** — start at login, theme, first day of week, time format
- **Timer** — idle threshold (with the provider or the reason it is unavailable,
  P7), long-running prompt, mandatory client/type, reminders (FR-702)
- **Export** — rounding increment and scope, CSV delimiter, export folder
- **Labels** — rename, archive/unarchive, delete when unused, with usage counts
- **Data** — data folder, log file, back up now, restore, export all data
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTime, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from timetracker.core.errors import DuplicateLabelError, LabelInUseError, ValidationError
from timetracker.core.models import Dimension
from timetracker.core.rounding import INCREMENTS, RoundingScope
from timetracker.crashlog import LOG_NAME
from timetracker.platform.base import AutostartProvider, Unavailable
from timetracker.platform.factory import launch_command
from timetracker.services.backup_service import BackupService, RestoreError
from timetracker.services.idle_monitor import IdleMonitor
from timetracker.services.label_service import LabelService
from timetracker.services.settings_service import (
    KEY_CSV_DELIMITER,
    KEY_EXPORT_FOLDER,
    KEY_FIRST_WEEKDAY,
    KEY_IDLE_THRESHOLD_MIN,
    KEY_LONG_RUNNING_HOURS,
    KEY_MANDATORY_CLIENT,
    KEY_MANDATORY_TYPE,
    KEY_REMINDER_DAYS,
    KEY_REMINDER_ENABLED,
    KEY_REMINDER_END,
    KEY_REMINDER_MINUTES,
    KEY_REMINDER_START,
    KEY_ROUNDING_MINUTES,
    KEY_ROUNDING_SCOPE,
    KEY_THEME,
    KEY_TIME_FORMAT,
    SettingsService,
)

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class LabelManager(QWidget):
    """One dimension's list with rename / archive / delete (FR-404, FR-405)."""

    def __init__(self, dimension: Dimension, labels: LabelService, parent: QWidget | None = None):
        super().__init__(parent)
        self._dim = dimension
        self._labels = labels
        self.list = QListWidget()
        self.list.setAccessibleName(f"{dimension.name.title()} labels")
        self.rename_button = QPushButton("Rename…")
        self.archive_button = QPushButton("Archive")
        self.delete_button = QPushButton("Delete")
        self.rename_button.clicked.connect(self.rename_selected)
        self.archive_button.clicked.connect(self.toggle_archived)
        self.delete_button.clicked.connect(self.delete_selected)
        self.list.currentItemChanged.connect(lambda *_: self._update_buttons())
        buttons = QHBoxLayout()
        buttons.addWidget(self.rename_button)
        buttons.addWidget(self.archive_button)
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(self.list)
        layout.addLayout(buttons)
        labels.labels_changed.connect(lambda d: self.reload() if d is dimension else None)
        self.reload()

    def reload(self) -> None:
        current = self.selected_id()
        self.list.clear()
        for label in self._labels.list_all(self._dim):
            n = self._labels.entry_count(self._dim, label.id)
            text = f"{label.name}   ·   {n} entr{'y' if n == 1 else 'ies'}"
            if label.is_archived:
                text += "   (archived)"
            item = QListWidgetItem(text)
            item.setData(0x0100, label.id)  # Qt.UserRole
            item.setData(0x0101, label.is_archived)
            item.setData(0x0102, n)
            self.list.addItem(item)
            if label.id == current:
                self.list.setCurrentItem(item)
        self._update_buttons()

    def selected_id(self) -> int | None:
        item = self.list.currentItem()
        return None if item is None else int(item.data(0x0100))

    def _update_buttons(self) -> None:
        item = self.list.currentItem()
        has = item is not None
        self.rename_button.setEnabled(has)
        self.archive_button.setEnabled(has)
        self.archive_button.setText("Unarchive" if has and item.data(0x0101) else "Archive")
        self.delete_button.setEnabled(has and int(item.data(0x0102)) == 0)
        self.delete_button.setToolTip(
            "" if self.delete_button.isEnabled() else "In use by entries — archive it instead"
        )

    def rename_selected(self) -> None:
        label_id = self.selected_id()
        if label_id is None:
            return
        current = self._labels.get(self._dim, label_id)
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=current.name)
        if not ok or not new_name.strip():
            return
        try:
            self._labels.rename(self._dim, label_id, new_name)
        except (DuplicateLabelError, ValidationError) as exc:
            QMessageBox.warning(self, "Cannot rename", str(exc))

    def toggle_archived(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        self._labels.set_archived(self._dim, int(item.data(0x0100)), not bool(item.data(0x0101)))

    def delete_selected(self) -> None:
        label_id = self.selected_id()
        if label_id is None:
            return
        try:
            self._labels.delete(self._dim, label_id)
        except LabelInUseError as exc:
            QMessageBox.warning(self, "Cannot delete", str(exc))


class SettingsDialog(QDialog):
    theme_changed = Signal(str)
    relaunch_requested = Signal()

    def __init__(
        self,
        settings: SettingsService,
        labels: LabelService,
        backups: BackupService,
        idle_monitor: IdleMonitor | None,
        autostart: AutostartProvider | Unavailable,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Time Tracker — Settings")
        self.setModal(False)
        self.resize(640, 520)
        self._settings = settings
        self._labels = labels
        self._backups = backups
        self._idle = idle_monitor
        self._autostart = autostart

        self.tabs = QTabWidget()
        self.tabs.addTab(self._general_tab(), "General")
        self.tabs.addTab(self._timer_tab(), "Timer")
        self.tabs.addTab(self._export_tab(), "Export")
        self.tabs.addTab(self._labels_tab(), "Labels")
        self.tabs.addTab(self._data_tab(), "Data")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(buttons)

    # -- General -----------------------------------------------------------------

    def _general_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.autostart = QCheckBox("Start Time Tracker when I log in")
        self.autostart.setAccessibleName("Start at login")
        if isinstance(self._autostart, Unavailable):
            self.autostart.setEnabled(False)
            self.autostart.setToolTip(self._autostart.reason)
            form.addRow(self.autostart)
            form.addRow(QLabel(self._autostart.reason))
        else:
            self.autostart.setChecked(self._autostart.is_enabled())
            self.autostart.toggled.connect(self._on_autostart_toggled)
            form.addRow(self.autostart)

        self.theme = QComboBox()
        self.theme.setAccessibleName("Theme")
        for value, text in (("system", "Follow the system"), ("light", "Light"), ("dark", "Dark")):
            self.theme.addItem(text, value)
        self.theme.setCurrentIndex(max(0, self.theme.findData(self._settings.theme)))
        self.theme.currentIndexChanged.connect(
            lambda _i: (
                self._settings.set(KEY_THEME, self.theme.currentData()),
                self.theme_changed.emit(str(self.theme.currentData())),
            )
        )
        form.addRow("Theme", self.theme)

        self.first_weekday = QComboBox()
        self.first_weekday.setAccessibleName("First day of week")
        for i, name in enumerate(WEEKDAYS):
            self.first_weekday.addItem(name, i)
        self.first_weekday.setCurrentIndex(self._settings.first_weekday)
        self.first_weekday.currentIndexChanged.connect(
            lambda i: self._settings.set(KEY_FIRST_WEEKDAY, int(i))
        )
        form.addRow("First day of week", self.first_weekday)

        self.time_format = QComboBox()
        self.time_format.setAccessibleName("Time format")
        self.time_format.addItem("24-hour (14:05)", "24h")
        self.time_format.addItem("12-hour (2:05 PM)", "12h")
        self.time_format.setCurrentIndex(1 if self._settings.time_format_12h else 0)
        self.time_format.currentIndexChanged.connect(
            lambda _i: self._settings.set(KEY_TIME_FORMAT, self.time_format.currentData())
        )
        form.addRow("Time format", self.time_format)
        return page

    def _on_autostart_toggled(self, checked: bool) -> None:
        if isinstance(self._autostart, Unavailable):
            return
        try:
            self._autostart.set_enabled(checked, launch_command())
        except OSError as exc:
            QMessageBox.warning(self, "Start at login", f"Could not update the login item:\n{exc}")
            self.autostart.blockSignals(True)
            self.autostart.setChecked(self._autostart.is_enabled())
            self.autostart.blockSignals(False)

    # -- Timer -------------------------------------------------------------------

    def _timer_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.idle_minutes = QSpinBox()
        self.idle_minutes.setAccessibleName("Idle threshold in minutes")
        self.idle_minutes.setRange(0, 180)
        self.idle_minutes.setSpecialValueText("Off")
        self.idle_minutes.setSuffix(" min")
        self.idle_minutes.setValue(self._settings.idle_threshold_seconds // 60)
        self.idle_minutes.valueChanged.connect(
            lambda v: self._settings.set(KEY_IDLE_THRESHOLD_MIN, int(v))
        )
        form.addRow("Ask after no input for", self.idle_minutes)
        if self._idle is None or not self._idle.available:
            reason = self._idle.unavailable_reason if self._idle else "not running"
            self.idle_minutes.setEnabled(False)
            note = QLabel(f"Idle detection is not available on this desktop session:\n{reason}")
            note.setWordWrap(True)
            form.addRow(note)
        form.addRow(QLabel("Sleep and hibernation are always detected."))

        self.long_running_hours = QSpinBox()
        self.long_running_hours.setAccessibleName("Long-running prompt in hours")
        self.long_running_hours.setRange(0, 48)
        self.long_running_hours.setSpecialValueText("Never")
        self.long_running_hours.setSuffix(" h")
        self.long_running_hours.setValue(self._settings.long_running_seconds // 3600)
        self.long_running_hours.valueChanged.connect(
            lambda v: self._settings.set(KEY_LONG_RUNNING_HOURS, int(v))
        )
        form.addRow("Ask “still running?” after", self.long_running_hours)

        box = QGroupBox("Add Time requires")
        box_layout = QVBoxLayout(box)
        self.mandatory_client = QCheckBox("a client")
        self.mandatory_client.setChecked(self._settings.mandatory_client)
        self.mandatory_client.toggled.connect(
            lambda on: self._settings.set(KEY_MANDATORY_CLIENT, bool(on))
        )
        self.mandatory_type = QCheckBox("a category")
        self.mandatory_type.setChecked(self._settings.mandatory_type)
        self.mandatory_type.toggled.connect(
            lambda on: self._settings.set(KEY_MANDATORY_TYPE, bool(on))
        )
        box_layout.addWidget(self.mandatory_client)
        box_layout.addWidget(self.mandatory_type)
        box_layout.addWidget(QLabel("The stopwatch never blocks on labels."))
        form.addRow(box)

        # FR-702: opt-in reminders, off by default.
        rem = QGroupBox("Remind me when nothing is being tracked")
        rem.setCheckable(True)
        rem.setChecked(self._settings.reminders_enabled)
        rem.toggled.connect(lambda on: self._settings.set(KEY_REMINDER_ENABLED, bool(on)))
        self.reminders = rem
        rem_form = QFormLayout(rem)
        self.reminder_minutes = QSpinBox()
        self.reminder_minutes.setAccessibleName("Reminder after minutes")
        self.reminder_minutes.setRange(5, 480)
        self.reminder_minutes.setSingleStep(5)
        self.reminder_minutes.setSuffix(" min")
        self.reminder_minutes.setValue(self._settings.reminder_minutes)
        self.reminder_minutes.valueChanged.connect(
            lambda v: self._settings.set(KEY_REMINDER_MINUTES, int(v))
        )
        rem_form.addRow("After", self.reminder_minutes)
        hours = QHBoxLayout()
        self.reminder_start = QTimeEdit(
            QTime.fromString(self._settings.reminder_start.strftime("%H:%M"), "HH:mm")
        )
        self.reminder_start.setAccessibleName("Working hours start")
        self.reminder_end = QTimeEdit(
            QTime.fromString(self._settings.reminder_end.strftime("%H:%M"), "HH:mm")
        )
        self.reminder_end.setAccessibleName("Working hours end")
        for edit, key in (
            (self.reminder_start, KEY_REMINDER_START),
            (self.reminder_end, KEY_REMINDER_END),
        ):
            edit.setDisplayFormat("HH:mm")
            edit.timeChanged.connect(lambda t, k=key: self._settings.set(k, t.toString("HH:mm")))
        hours.addWidget(self.reminder_start)
        hours.addWidget(QLabel("to"))
        hours.addWidget(self.reminder_end)
        hours.addStretch(1)
        rem_form.addRow("Between", hours)
        days = QHBoxLayout()
        self.reminder_days: list[QCheckBox] = []
        selected = self._settings.reminder_days
        for i, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
            cb = QCheckBox(name)
            cb.setChecked(i in selected)
            cb.toggled.connect(self._on_reminder_days_changed)
            self.reminder_days.append(cb)
            days.addWidget(cb)
        days.addStretch(1)
        rem_form.addRow("On", days)
        form.addRow(rem)
        return page

    def _on_reminder_days_changed(self, _on: bool) -> None:
        self._settings.set(
            KEY_REMINDER_DAYS, [i for i, cb in enumerate(self.reminder_days) if cb.isChecked()]
        )

    # -- Export ------------------------------------------------------------------

    def _export_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.rounding = QComboBox()
        self.rounding.setAccessibleName("Default rounding")
        for minutes in INCREMENTS:
            self.rounding.addItem("none" if minutes == 0 else f"{minutes} minutes", minutes)
        self.rounding.setCurrentIndex(
            max(0, self.rounding.findData(self._settings.rounding_minutes))
        )
        self.rounding.currentIndexChanged.connect(
            lambda _i: self._settings.set(KEY_ROUNDING_MINUTES, int(self.rounding.currentData()))
        )
        form.addRow("Default rounding", self.rounding)

        self.scope = QComboBox()
        self.scope.setAccessibleName("Default rounding scope")
        for s in (RoundingScope.PER_GROUP, RoundingScope.PER_ENTRY):
            self.scope.addItem(s.display, s.value)
        self.scope.setCurrentIndex(max(0, self.scope.findData(self._settings.rounding_scope.value)))
        self.scope.currentIndexChanged.connect(
            lambda _i: self._settings.set(KEY_ROUNDING_SCOPE, self.scope.currentData())
        )
        form.addRow("Rounding scope", self.scope)

        self.delimiter = QComboBox()
        self.delimiter.setAccessibleName("CSV delimiter")
        self.delimiter.addItem("Locale default", None)
        self.delimiter.addItem("Semicolon  ;", ";")
        self.delimiter.addItem("Comma  ,", ",")
        self.delimiter.addItem("Tab", "\t")
        raw = self._settings.get(KEY_CSV_DELIMITER)
        self.delimiter.setCurrentIndex(max(0, self.delimiter.findData(raw)) if raw else 0)
        self.delimiter.currentIndexChanged.connect(
            lambda _i: self._settings.set(KEY_CSV_DELIMITER, self.delimiter.currentData())
        )
        form.addRow("CSV delimiter", self.delimiter)

        self.export_folder = QLineEdit(str(self._settings.export_folder))
        self.export_folder.setAccessibleName("Export folder")
        self.export_folder.setReadOnly(True)
        browse = QPushButton("Choose…")
        browse.clicked.connect(self._choose_export_folder)
        row = QHBoxLayout()
        row.addWidget(self.export_folder, 1)
        row.addWidget(browse)
        form.addRow("Export folder", row)
        form.addRow(
            QLabel("Rounding is applied to exported files only; stored records never change.")
        )
        return page

    def _choose_export_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Export folder", str(self._settings.export_folder)
        )
        if chosen:
            self._settings.set(KEY_EXPORT_FOLDER, chosen)
            self.export_folder.setText(chosen)

    # -- Labels ------------------------------------------------------------------

    def _labels_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        clients = QGroupBox("Clients")
        clients_layout = QVBoxLayout(clients)
        self.clients = LabelManager(Dimension.CLIENT, self._labels)
        clients_layout.addWidget(self.clients)
        types = QGroupBox("Categories")
        types_layout = QVBoxLayout(types)
        self.types = LabelManager(Dimension.TYPE, self._labels)
        types_layout.addWidget(self.types)
        layout.addWidget(clients)
        layout.addWidget(types)
        return page

    # -- Data --------------------------------------------------------------------

    def _data_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        folder = self._backups.data_dir
        path_label = QLabel(str(folder))
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        reveal = QPushButton("Reveal data folder")
        reveal.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))))
        log_button = QPushButton("Open log file")
        log_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder / LOG_NAME)))
        )
        form.addRow("Data folder", path_label)
        row = QHBoxLayout()
        row.addWidget(reveal)
        row.addWidget(log_button)
        row.addStretch(1)
        form.addRow(row)

        self.backup_button = QPushButton("Back up now")
        self.backup_button.clicked.connect(self.backup_now)
        self.restore_button = QPushButton("Restore from backup…")
        self.restore_button.clicked.connect(self.restore)
        self.export_all_button = QPushButton("Export all data…")
        self.export_all_button.clicked.connect(self.export_all)
        self.backup_status = QLabel("")
        self.backup_status.setWordWrap(True)
        actions = QHBoxLayout()
        actions.addWidget(self.backup_button)
        actions.addWidget(self.restore_button)
        actions.addWidget(self.export_all_button)
        actions.addStretch(1)
        form.addRow(actions)
        form.addRow(self.backup_status)
        form.addRow(
            QLabel(
                "A backup is a complete copy of the database. Restoring replaces the current\n"
                "data (a copy of it is kept first) and restarts the application."
            )
        )
        return page

    def backup_now(self) -> None:
        path = self._backups.backup_now()
        self.backup_status.setText(f"Backed up to {path}")

    def restore(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Restore from backup", str(self._backups.data_dir), "SQLite databases (*.sqlite3)"
        )
        if not chosen:
            return
        try:
            info = self._backups.inspect(Path(chosen))
        except RestoreError as exc:
            QMessageBox.warning(self, "Cannot restore", str(exc))
            return
        answer = QMessageBox.question(
            self,
            "Restore from backup",
            f"Replace the current data with {info.path.name} ({info.entries} entries)?\n"
            "A copy of the current data is kept, and Time Tracker restarts.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._backups.restore(info.path)
        self.relaunch_requested.emit()

    def export_all(self) -> None:
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            "Export all data",
            str(self._settings.export_folder / "timetracker-all.json"),
            "JSON (*.json);;CSV (*.csv)",
        )
        if not chosen:
            return
        path = Path(chosen)
        if path.suffix.lower() not in (".json", ".csv"):
            path = path.with_suffix(".json")
        self._backups.full_export(path)
        self.backup_status.setText(f"Exported everything to {path}")
