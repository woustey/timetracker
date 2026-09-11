"""Migration runner (PRD-02 §4.3, FR-806)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from timetracker.core.clock import FakeClock
from timetracker.core.errors import SchemaTooNewError
from timetracker.data.db import connect, execute_script, set_user_version, user_version
from timetracker.data.migrate import migrate
from timetracker.data.migrations import all_migrations
from timetracker.data.schema import CURRENT_DDL, TARGET_VERSION


def _schema(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    rows = conn.execute(
        "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"
    ).fetchall()
    return [(r["type"], r["name"], " ".join(r["sql"].split())) for r in rows]


def test_migrations_are_contiguous_and_end_at_target() -> None:
    versions = [m.version for m in all_migrations()]
    assert versions == list(range(1, TARGET_VERSION + 1))


def test_empty_to_v1(clock: FakeClock) -> None:
    conn = connect(":memory:")
    assert user_version(conn) == 0
    result = migrate(conn, clock=clock)
    assert result.from_version == 0
    assert result.to_version == TARGET_VERSION
    assert result.applied == [1]
    assert result.backup_path is None
    assert user_version(conn) == TARGET_VERSION
    rows = conn.execute("SELECT version, applied_at FROM schema_migration").fetchall()
    assert [(r["version"], r["applied_at"]) for r in rows] == [(1, "2026-09-11T10:00:00Z")]
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "client",
        "work_type",
        "entry",
        "running_timer",
        "setting",
        "schema_migration",
    } <= tables
    views = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'")}
    assert views == {"v_session_log"}


def test_migrate_is_idempotent(clock: FakeClock) -> None:
    conn = connect(":memory:")
    migrate(conn, clock=clock)
    before = _schema(conn)
    second = migrate(conn, clock=clock)
    assert not second.changed
    assert second.applied == []
    assert _schema(conn) == before
    assert conn.execute("SELECT COUNT(*) FROM schema_migration").fetchone()[0] == 1


def test_migrated_schema_matches_current_ddl(clock: FakeClock) -> None:
    """Drift guard: applying every migration must equal schema.CURRENT_DDL."""
    migrated = connect(":memory:")
    migrate(migrated, clock=clock)
    direct = connect(":memory:")
    execute_script(direct, CURRENT_DDL)
    assert _schema(migrated) == _schema(direct)


def test_refuses_database_from_the_future(clock: FakeClock) -> None:
    conn = connect(":memory:")
    set_user_version(conn, TARGET_VERSION + 1)
    with pytest.raises(SchemaTooNewError) as exc:
        migrate(conn, clock=clock)
    assert exc.value.db_version == TARGET_VERSION + 1
    assert exc.value.code_version == TARGET_VERSION


def test_fresh_file_gets_no_backup(tmp_path: Path, clock: FakeClock) -> None:
    """A brand-new database has nothing to back up."""
    db = tmp_path / "timetracker.sqlite3"
    conn = connect(db)
    result = migrate(conn, db, clock=clock)
    conn.close()
    assert result.applied == [1]
    assert result.backup_path is None
    assert sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".sqlite3") == [
        "timetracker.sqlite3"
    ]


def test_backup_taken_when_file_version_is_behind(
    tmp_path: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "timetracker.sqlite3"
    conn = connect(db)
    migrate(conn, db, clock=clock)
    conn.execute("INSERT INTO setting (key, value) VALUES ('k', '1')")
    conn.close()

    # Pretend the code moved on to v2 with a trivial migration.
    import timetracker.data.migrate as mod
    from timetracker.data.migrations import Migration

    def fake_all() -> list[Migration]:
        return [
            *all_migrations(),
            Migration(2, "m0002_fake", lambda c: c.execute("CREATE TABLE t2 (x)")),
        ]

    monkeypatch.setattr(mod, "all_migrations", fake_all)
    monkeypatch.setattr(mod, "TARGET_VERSION", 2)

    conn = connect(db)
    result = migrate(conn, db, clock=clock)
    assert result.applied == [2]
    assert result.backup_path == tmp_path / "timetracker-pre-v1.sqlite3"
    assert result.backup_path.exists()
    assert user_version(conn) == 2
    conn.close()

    # The backup is the pre-v2 state: has the setting row, lacks table t2.
    backup = connect(result.backup_path, read_only=True)
    assert user_version(backup) == 1
    assert backup.execute("SELECT value FROM setting WHERE key='k'").fetchone()[0] == "1"
    assert backup.execute("SELECT name FROM sqlite_master WHERE name='t2'").fetchone() is None
    backup.close()


def test_failed_migration_rolls_back_entirely(
    tmp_path: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = connect(":memory:")
    migrate(conn, clock=clock)

    import timetracker.data.migrate as mod
    from timetracker.data.migrations import Migration

    def broken(c: sqlite3.Connection) -> None:
        c.execute("CREATE TABLE half_done (x)")
        raise sqlite3.OperationalError("boom")

    monkeypatch.setattr(
        mod, "all_migrations", lambda: [*all_migrations(), Migration(2, "m0002_broken", broken)]
    )
    monkeypatch.setattr(mod, "TARGET_VERSION", 2)

    with pytest.raises(sqlite3.OperationalError):
        migrate(conn, clock=clock)
    assert user_version(conn) == 1
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='half_done'").fetchone() is None
    assert conn.execute("SELECT COUNT(*) FROM schema_migration").fetchone()[0] == 1


def test_file_database_uses_wal(tmp_path: Path, clock: FakeClock) -> None:
    conn = connect(tmp_path / "t.sqlite3")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()
