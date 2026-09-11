"""Where the data lives (FR-801), using only the stdlib.

| OS      | Directory                                             |
|---------|-------------------------------------------------------|
| Windows | ``%LOCALAPPDATA%\\TimeTracker``                        |
| macOS   | ``~/Library/Application Support/TimeTracker``         |
| Linux   | ``$XDG_DATA_HOME/timetracker`` (``~/.local/share/…``) |

``TIMETRACKER_DATA_DIR`` overrides all of them, which is how tests and portable
installs point the app elsewhere.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

DB_FILENAME = "timetracker.sqlite3"
ENV_OVERRIDE = "TIMETRACKER_DATA_DIR"


def data_dir(platform: str | None = None) -> Path:
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return Path(override).expanduser()
    system = platform or sys.platform
    if system == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "TimeTracker"
    if system == "darwin":
        return Path.home() / "Library" / "Application Support" / "TimeTracker"
    xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(xdg) / "timetracker"


def db_path() -> Path:
    return data_dir() / DB_FILENAME
