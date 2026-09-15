"""Settings dialog: every control round-trips to settings; label ops; data actions."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from timetracker.core.clock import FakeClock
from timetracker.core.models import Dimension
from timetracker.platform.base import Unavailable
from timetracker.services.backup_service import BackupService
from timetracker.services.entry_service import EntryService
from timetracker.services.label_service import LabelService
from timetracker.services.settings_service import (
    KEY_CSV_DELIMITER,
    KEY_EXPORT_FOLDER,
    KEY_ROUNDING_MINUTES,
    SettingsService,
)
from timetracker.ui.settings_dialog import SettingsDialog


class FakeAutostart:
    name = "fake"

    def __init__(self) -> None:
        self.enabled = False
        self.command: list[str] = []

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool, command: list[str]) -> None:
        self.enabled = enabled
        self.command = command


@pytest.fixture
def dialog(  # type: ignore[no-untyped-def]
    qtbot,
    tmp_path: Path,
    clock: FakeClock,
    conn: sqlite3.Connection,
    settings_service: SettingsService,
    labels: LabelService,
    entry_service: EntryService,
) -> tuple[SettingsDialog, FakeAutostart, BackupService]:
    labels.ensure_seed_types()
    nike = labels.get_or_create(Dimension.CLIENT, "Nike")
    labels.get_or_create(Dimension.CLIENT, "Unused Co")
    entry_service.add_quick(600, nike.id, None, None)
    backups = BackupService(clock, tmp_path / "timetracker.sqlite3", conn)
    autostart = FakeAutostart()
    d = SettingsDialog(settings_service, labels, backups, None, autostart)
    qtbot.addWidget(d)
    d.show()
    return d, autostart, backups


def test_general_tab_round_trips(dialog, settings_service: SettingsService, qtbot) -> None:  # type: ignore[no-untyped-def]
    d, autostart, _ = dialog
    d.autostart.setChecked(True)
    assert autostart.enabled and autostart.command  # written through launch_command()
    d.autostart.setChecked(False)
    assert not autostart.enabled

    with qtbot.waitSignal(d.theme_changed, timeout=1000) as blocker:
        d.theme.setCurrentIndex(d.theme.findData("dark"))
    assert blocker.args == ["dark"]
    assert settings_service.theme == "dark"
    d.first_weekday.setCurrentIndex(6)
    assert settings_service.first_weekday == 6
    d.time_format.setCurrentIndex(1)
    assert settings_service.time_format_12h


def test_timer_and_export_tabs(
    dialog, settings_service: SettingsService, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    d, _, _ = dialog
    assert not d.idle_minutes.isEnabled()  # no idle monitor passed: shown as unavailable
    d.long_running_hours.setValue(8)
    assert settings_service.long_running_seconds == 8 * 3600
    d.mandatory_client.setChecked(False)
    assert settings_service.mandatory_client is False
    d.rounding.setCurrentIndex(d.rounding.findData(15))
    assert settings_service.get(KEY_ROUNDING_MINUTES) == 15
    d.scope.setCurrentIndex(d.scope.findData("per_entry"))
    assert settings_service.rounding_scope.value == "per_entry"
    d.delimiter.setCurrentIndex(d.delimiter.findData(","))
    assert settings_service.get(KEY_CSV_DELIMITER) == ","
    assert settings_service.csv_delimiter == ","
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(tmp_path))
    )
    d._choose_export_folder()  # noqa: SLF001
    assert settings_service.get(KEY_EXPORT_FOLDER) == str(tmp_path)
    assert settings_service.export_folder == tmp_path


def test_labels_tab(dialog, labels: LabelService, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    d, _, _ = dialog
    clients = d.clients
    names = [clients.list.item(i).text() for i in range(clients.list.count())]
    assert any(t.startswith("Nike   ·   1 entry") for t in names)
    assert any(t.startswith("Unused Co   ·   0 entries") for t in names)

    # Nike (in use): delete disabled, archive works.
    nike_row = next(
        i for i in range(clients.list.count()) if clients.list.item(i).text().startswith("Nike")
    )
    clients.list.setCurrentRow(nike_row)
    assert not clients.delete_button.isEnabled()
    assert clients.archive_button.text() == "Archive"
    clients.toggle_archived()
    assert clients.archive_button.text() == "Unarchive"
    assert labels.list(Dimension.CLIENT) == [
        x for x in labels.list(Dimension.CLIENT) if x.name != "Nike"
    ]

    # Rename via the input dialog.
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("Nike Europe", True))
    )
    clients.rename_selected()
    assert any(x.name == "Nike Europe" for x in labels.list_all(Dimension.CLIENT))

    # Unused Co: delete allowed.
    row = next(
        i for i in range(clients.list.count()) if clients.list.item(i).text().startswith("Unused")
    )
    clients.list.setCurrentRow(row)
    assert clients.delete_button.isEnabled()
    clients.delete_selected()
    assert not any(x.name == "Unused Co" for x in labels.list_all(Dimension.CLIENT))


def test_data_tab_backup_restore_export(
    dialog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qtbot
) -> None:  # type: ignore[no-untyped-def]
    d, _, backups = dialog
    d.backup_now()
    assert "Backed up to" in d.backup_status.text()
    backup = backups.list_backups()[0]
    assert backup.exists()

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a, **k: (str(tmp_path / "all.json"), "")),
    )
    d.export_all()
    assert (tmp_path / "all.json").exists()

    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(backup), ""))
    )
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    with qtbot.waitSignal(d.relaunch_requested, timeout=1000):
        d.restore()
    assert any(p.name.startswith("timetracker-pre-restore-") for p in tmp_path.iterdir())


def test_unavailable_autostart_is_explained(
    qtbot, tmp_path, clock, conn, settings_service, labels
) -> None:  # type: ignore[no-untyped-def]
    backups = BackupService(clock, tmp_path / "t.sqlite3", conn)
    d = SettingsDialog(settings_service, labels, backups, None, Unavailable("no login items here"))
    qtbot.addWidget(d)
    assert not d.autostart.isEnabled()
    assert d.autostart.toolTip() == "no login items here"
