"""Typed accessors over the ``setting`` table with defaults (PRD-02 §6, FR-701).

Only the keys the shipped milestones read are defined; the settings dialog
(M6) will grow this. Values are JSON in the table; here they are typed.
"""

from __future__ import annotations

from datetime import time
from typing import Any

from PySide6.QtCore import QObject, Signal

from timetracker.data.settings_repo import SettingsRepo

KEY_MANDATORY_CLIENT = "labels.mandatory_client"
KEY_MANDATORY_TYPE = "labels.mandatory_type"
KEY_WORKDAY_START = "quickadd.workday_start"  # "HH:MM"
KEY_POPOVER_MODE = "popover.last_mode"  # "stopwatch" | "matrix"

DEFAULTS: dict[str, Any] = {
    KEY_MANDATORY_CLIENT: True,  # PRD-01 Q1: mandatory by default, with a setting
    KEY_MANDATORY_TYPE: True,
    KEY_WORKDAY_START: "09:00",
    KEY_POPOVER_MODE: "stopwatch",
}


class SettingsService(QObject):
    setting_changed = Signal(str)

    def __init__(self, repo: SettingsRepo, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._repo = repo

    # -- generic -------------------------------------------------------------

    def get(self, key: str) -> Any:
        return self._repo.get(key, DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        if self.get(key) == value:
            return
        self._repo.set(key, value)
        self.setting_changed.emit(key)

    # -- typed ---------------------------------------------------------------

    @property
    def mandatory_client(self) -> bool:
        return bool(self.get(KEY_MANDATORY_CLIENT))

    @property
    def mandatory_type(self) -> bool:
        return bool(self.get(KEY_MANDATORY_TYPE))

    @property
    def workday_start(self) -> time:
        raw = str(self.get(KEY_WORKDAY_START))
        try:
            return time.fromisoformat(raw)
        except ValueError:
            return time.fromisoformat(DEFAULTS[KEY_WORKDAY_START])
