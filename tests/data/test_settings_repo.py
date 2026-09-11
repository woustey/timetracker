from __future__ import annotations

import sqlite3

from timetracker.data.settings_repo import SettingsRepo


def test_default_when_missing(settings: SettingsRepo) -> None:
    assert settings.get("idle_threshold_minutes") is None
    assert settings.get("idle_threshold_minutes", 10) == 10


def test_json_round_trip_and_overwrite(settings: SettingsRepo, conn: sqlite3.Connection) -> None:
    settings.set("rounding", {"increment": 6, "scope": "PER_GROUP"})
    settings.set("theme", "système")
    settings.set("flag", True)
    settings.set("n", 3)
    assert settings.get("rounding") == {"increment": 6, "scope": "PER_GROUP"}
    assert settings.get("theme") == "système"
    assert settings.get("flag") is True
    assert settings.get("n") == 3
    settings.set("n", 4)
    assert settings.get("n") == 4
    assert conn.execute("SELECT COUNT(*) FROM setting WHERE key='n'").fetchone()[0] == 1
    assert conn.execute("SELECT value FROM setting WHERE key='theme'").fetchone()[0] == '"système"'


def test_delete_and_all(settings: SettingsRepo) -> None:
    settings.set("b", 2)
    settings.set("a", 1)
    assert settings.all() == {"a": 1, "b": 2}
    settings.delete("a")
    settings.delete("a")  # idempotent
    assert settings.all() == {"b": 2}
