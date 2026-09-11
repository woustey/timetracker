from __future__ import annotations

from pathlib import Path

import pytest

from timetracker.data.paths import DB_FILENAME, data_dir, db_path


def test_env_override_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TIMETRACKER_DATA_DIR", str(tmp_path))
    assert data_dir() == tmp_path
    assert db_path() == tmp_path / DB_FILENAME


def test_per_platform_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("TIMETRACKER_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert data_dir("win32") == tmp_path / "la" / "TimeTracker"
    assert data_dir("linux") == tmp_path / "xdg" / "timetracker"
    assert data_dir("darwin") == Path.home() / "Library" / "Application Support" / "TimeTracker"
