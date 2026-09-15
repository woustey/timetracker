"""First-run flow (NFR-09, FR-409, FR-108) and packaging helpers (M7)."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from timetracker import resources
from timetracker.core.models import Dimension
from timetracker.ui.dialogs.first_run import FirstRunDialog

ROOT = Path(__file__).resolve().parents[1]


def test_first_run_dialog_collects_clients_and_autostart(qtbot) -> None:  # type: ignore[no-untyped-def]
    d = FirstRunDialog(autostart_available=True)
    qtbot.addWidget(d)
    d.show()
    d.clients.setPlainText("Nike\n  adidas  \n\nNIKE\nASICS Europe\n")
    assert d.autostart.isChecked()
    d.autostart.setChecked(False)
    with qtbot.waitSignal(d.finished_setup, timeout=1000) as blocker:
        qtbot.mouseClick(d.start_button, Qt.MouseButton.LeftButton)
    names, start_at_login = blocker.args
    assert names == ["Nike", "adidas", "ASICS Europe"]  # trimmed, collapsed, de-duplicated
    assert start_at_login is False
    assert not d.isModal()


def test_first_run_without_autostart_support(qtbot) -> None:  # type: ignore[no-untyped-def]
    d = FirstRunDialog(autostart_available=False)
    qtbot.addWidget(d)
    assert not d.autostart.isEnabled() and not d.autostart.isChecked()
    assert d.client_names() == []


def test_app_first_run_creates_labels_and_opens_popover(booted_app, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from timetracker.services.settings_service import KEY_AUTOSTART_OFFERED

    app = booted_app
    assert app.settings_service.get(KEY_AUTOSTART_OFFERED) is False  # fresh data dir
    qtbot.waitUntil(lambda: app._first_run_dialog is not None, timeout=2000)  # noqa: SLF001
    dialog = app._first_run_dialog  # noqa: SLF001
    dialog.clients.setPlainText("Puma\nReebok")
    dialog.autostart.setChecked(False)
    dialog.start_button.click()
    assert app.settings_service.get(KEY_AUTOSTART_OFFERED) is True
    names = [x.name for x in app.label_service.list(Dimension.CLIENT)]
    assert names == ["Puma", "Reebok"]
    qtbot.waitUntil(lambda: app.popover is not None and app.popover.isVisible(), timeout=2000)
    # A second boot never asks again (checked through the service, same DB).
    assert app.settings_service.autostart_offered


def test_icon_files_are_shipped_and_valid() -> None:
    ico = resources.icon_path()
    assert ico is not None and ico.suffix == ".ico"
    data = ico.read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data, 0)
    assert (reserved, kind) == (0, 1)
    assert count == 7
    for size in (16, 32, 256):
        png = resources.png_path(size)
        assert png is not None and png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    icon = QIcon(str(ico))
    assert not icon.isNull()
    assert 256 in [s.width() for s in icon.availableSizes()]


def test_launch_command_when_frozen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from timetracker.platform.factory import launch_command

    fake_exe = tmp_path / "timetracker.exe"
    fake_exe.write_bytes(b"MZ")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    assert launch_command() == [str(fake_exe)]


def test_installer_script_and_workflow_are_consistent() -> None:
    iss = (ROOT / "installer" / "windows.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in iss  # per-user, no elevation (§12.2)
    assert 'ValueName: "TimeTracker"' in iss  # same Run value the app manages
    assert "TimeTracker" in iss and "uninsdeletevalue" in iss
    assert "[UninstallDelete]" not in iss  # never touches the data folder
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    for needle in (
        "windows-latest",
        "macos-latest",
        "ubuntu-latest",
        "TIMETRACKER_MEASURE_BOOT",
        "ISCC.exe",
    ):
        assert needle in workflow
    build = (ROOT / "scripts" / "build_release.py").read_text(encoding="utf-8")
    assert "--include-package=openpyxl" in build  # lazy import must be forced in
    assert "--include-package-data=tzdata" in build
    assert "--windows-console-mode=disable" in build
    assert "--macos-app-mode=background" in build  # LSUIElement
