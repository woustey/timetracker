"""Autostart providers (FR-108) and the launch command."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from timetracker.platform.base import Unavailable
from timetracker.platform.factory import autostart_provider, launch_command


def test_launch_command_points_at_something_runnable() -> None:
    cmd = launch_command()
    assert cmd
    assert Path(cmd[0]).exists()
    if len(cmd) > 1:
        assert cmd[1:] == ["-m", "timetracker"]


def test_factory_returns_provider_or_reason() -> None:
    provider = autostart_provider()
    if isinstance(provider, Unavailable):
        assert provider.reason
    else:
        assert provider.name
        assert isinstance(provider.is_enabled(), bool)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Run key")
def test_win32_run_key_round_trip() -> None:
    import winreg

    from timetracker.platform.win32 import Win32Autostart

    name = f"TimeTrackerTest{os.getpid()}"
    provider = Win32Autostart(value_name=name)
    try:
        assert provider.is_enabled() is False
        provider.set_enabled(True, ["C:\\Program Files\\Time Tracker\\timetracker.exe"])
        assert provider.is_enabled() is True
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, Win32Autostart._KEY) as key:  # noqa: SLF001
            value, kind = winreg.QueryValueEx(key, name)
        assert kind == winreg.REG_SZ
        assert (
            value == '"C:\\Program Files\\Time Tracker\\timetracker.exe"'
        )  # quoted: the path has spaces
        provider.set_enabled(False, [])
        assert provider.is_enabled() is False
        provider.set_enabled(False, [])  # idempotent
    finally:
        provider.set_enabled(False, [])


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="XDG autostart")
def test_linux_desktop_entry_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from timetracker.platform.linux import DesktopAutostart

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    provider = DesktopAutostart()
    assert not provider.is_enabled()
    provider.set_enabled(True, ["/opt/tt/timetracker", "-m", "timetracker"])
    entry = tmp_path / "autostart" / "timetracker.desktop"
    assert entry.exists()
    assert "Exec=/opt/tt/timetracker -m timetracker" in entry.read_text()
    provider.set_enabled(False, [])
    assert not entry.exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="LaunchAgents")
def test_macos_launch_agent_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import plistlib

    from timetracker.platform.macos import LaunchAgentAutostart

    monkeypatch.setenv("HOME", str(tmp_path))
    provider = LaunchAgentAutostart(label="be.dawasal.timetracker.test")
    assert not provider.is_enabled()
    provider.set_enabled(True, ["/Applications/TT.app/Contents/MacOS/tt"])
    plist = tmp_path / "Library" / "LaunchAgents" / "be.dawasal.timetracker.test.plist"
    assert plist.exists()
    with open(plist, "rb") as fh:
        assert plistlib.load(fh)["RunAtLoad"] is True
    provider.set_enabled(False, [])
    assert not plist.exists()
