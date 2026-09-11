"""Key/value settings with JSON-encoded values (PRD-02 §4.1 ``setting``, FR-703).

Typed accessors and defaults live in ``SettingsService``; this is raw storage.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from timetracker.data.db import transaction


class SettingsRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute("SELECT value FROM setting WHERE key = ?", (key,)).fetchone()
        return default if row is None else json.loads(row["value"])

    def set(self, key: str, value: Any) -> None:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
        with transaction(self._conn):
            self._conn.execute(
                "INSERT INTO setting (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, encoded),
            )

    def delete(self, key: str) -> None:
        with transaction(self._conn):
            self._conn.execute("DELETE FROM setting WHERE key = ?", (key,))

    def all(self) -> dict[str, Any]:
        rows = self._conn.execute("SELECT key, value FROM setting ORDER BY key").fetchall()
        return {str(r["key"]): json.loads(r["value"]) for r in rows}
