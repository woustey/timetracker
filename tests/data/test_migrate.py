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


def test_empty_to_current(clock: FakeClock) -> None:
    conn = connect(":memory:")
    assert user_version(conn) == 0
    result = migrate(conn, clock=clock)
    assert result.from_version == 0
    assert result.to_version == TARGET_VERSION
    assert result.applied == list(range(1, TARGET_VERSION + 1))
    assert result.backup_path is None
    assert user_version(conn) == TARGET_VERSION
    rows = conn.execute("SELECT version, applied_at FROM schema_migration").fetchall()
    assert [(r["version"], r["applied_at"]) for r in rows] == [
        (v, "2026-09-11T10:00:00Z") for v in range(1, TARGET_VERSION + 1)
    ]
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
    assert conn.execute("SELECT COUNT(*) FROM schema_migration").fetchone()[0] == TARGET_VERSION


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
    assert result.applied == list(range(1, TARGET_VERSION + 1))
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

    nxt = TARGET_VERSION + 1

    def fake_all() -> list[Migration]:
        return [
            *all_migrations(),
            Migration(nxt, f"m{nxt:04d}_fake", lambda c: c.execute("CREATE TABLE t2 (x)")),
        ]

    monkeypatch.setattr(mod, "all_migrations", fake_all)
    monkeypatch.setattr(mod, "TARGET_VERSION", nxt)

    conn = connect(db)
    result = migrate(conn, db, clock=clock)
    assert result.applied == [nxt]
    assert result.backup_path == tmp_path / f"timetracker-pre-v{TARGET_VERSION}.sqlite3"
    assert result.backup_path.exists()
    assert user_version(conn) == nxt
    conn.close()

    # The backup is the pre-upgrade state: has the setting row, lacks table t2.
    backup = connect(result.backup_path, read_only=True)
    assert user_version(backup) == TARGET_VERSION
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

    nxt = TARGET_VERSION + 1
    monkeypatch.setattr(
        mod,
        "all_migrations",
        lambda: [*all_migrations(), Migration(nxt, f"m{nxt:04d}_broken", broken)],
    )
    monkeypatch.setattr(mod, "TARGET_VERSION", nxt)

    with pytest.raises(sqlite3.OperationalError):
        migrate(conn, clock=clock)
    assert user_version(conn) == TARGET_VERSION
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='half_done'").fetchone() is None
    assert conn.execute("SELECT COUNT(*) FROM schema_migration").fetchone()[0] == TARGET_VERSION


def test_file_database_uses_wal(tmp_path: Path, clock: FakeClock) -> None:
    conn = connect(tmp_path / "t.sqlite3")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()


def test_v1_to_v2_keeps_data_and_adds_the_totals_index(tmp_path: Path, clock: FakeClock) -> None:
    """PRD-02 §4.3: build v1, insert rows, upgrade, assert the data survived."""
    from timetracker.data.schema import DDL_V1

    db = tmp_path / "v1.sqlite3"
    conn = connect(db)
    execute_script(conn, DDL_V1)
    conn.execute("INSERT INTO client (name, name_norm, created_at) VALUES ('Nike', 'nike', 'x')")
    conn.execute(
        "INSERT INTO entry (uuid, started_at_utc, ended_at_utc, tz_name, local_date, "
        "duration_seconds, client_id, record_method, created_at, modified_at) "
        "VALUES ('u1', '2026-09-08T07:00:00Z', '2026-09-08T07:30:00Z', 'Europe/Brussels', "
        "'2026-09-08', 1800, 1, 'STOPWATCH', 'x', 'x')"
    )
    conn.execute("INSERT INTO schema_migration (version, applied_at) VALUES (1, 'x')")
    set_user_version(conn, 1)
    conn.close()

    conn = connect(db)
    result = migrate(conn, db, clock=clock)
    assert result.applied == [2, 3, 4]
    assert result.backup_path == tmp_path / "v1-pre-v1.sqlite3"
    assert user_version(conn) == TARGET_VERSION
    assert conn.execute("SELECT duration_seconds FROM entry WHERE uuid='u1'").fetchone()[0] == 1800
    assert conn.execute("SELECT name FROM client").fetchone()[0] == "Nike"
    indexes = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_entry_totals" in indexes
    plan = " ".join(
        r[3]
        for r in conn.execute(
            "EXPLAIN QUERY PLAN SELECT client_id, SUM(duration_seconds) "
            "FROM entry GROUP BY client_id"
        ).fetchall()
    )
    assert "COVERING INDEX idx_entry_totals" in plan
    conn.close()


def test_v2_to_v3_rebuilds_entry_and_keeps_data(tmp_path: Path, clock: FakeClock) -> None:
    """v3 adds the MANUAL record method (a CHECK change → table rebuild)."""
    from timetracker.data.schema import DDL_V1, DDL_V2_ADDITIONS

    db = tmp_path / "v2.sqlite3"
    conn = connect(db)
    execute_script(conn, DDL_V1)
    execute_script(conn, DDL_V2_ADDITIONS)
    conn.execute("INSERT INTO client (name, name_norm, created_at) VALUES ('Nike', 'nike', 'x')")
    conn.execute(
        "INSERT INTO entry (uuid, started_at_utc, ended_at_utc, tz_name, local_date, "
        "duration_seconds, client_id, note, record_method, is_edited, created_at, modified_at) "
        "VALUES ('u1', '2026-09-08T07:00:00Z', '2026-09-08T07:30:00Z', 'Europe/Brussels', "
        "'2026-09-08', 1800, 1, 'keep me', 'QUICKADD', 1, 'c', 'm')"
    )
    conn.execute(
        "INSERT INTO running_timer (id, started_at_utc, tz_name, heartbeat_at_utc, "
        "heartbeat_accrued_sec) VALUES (1, 'x', 'UTC', 'x', 7)"
    )
    for v in (1, 2):
        conn.execute("INSERT INTO schema_migration (version, applied_at) VALUES (?, 'x')", (v,))
    set_user_version(conn, 2)
    conn.close()

    conn = connect(db)
    result = migrate(conn, db, clock=clock)
    assert result.applied == [3, 4]
    assert user_version(conn) == 4
    row = conn.execute("SELECT * FROM entry WHERE uuid='u1'").fetchone()
    assert (
        row["id"],
        row["duration_seconds"],
        row["note"],
        row["record_method"],
        row["is_edited"],
    ) == (1, 1800, "keep me", "QUICKADD", 1)
    assert conn.execute("SELECT heartbeat_accrued_sec FROM running_timer").fetchone()[0] == 7
    # The new method is accepted, the old CHECK is gone, the RESTRICT FK still holds.
    conn.execute(
        "INSERT INTO entry (uuid, started_at_utc, ended_at_utc, tz_name, local_date, "
        "duration_seconds, client_id, record_method, created_at, modified_at) "
        "VALUES ('u2', 'x', 'x', 'UTC', '2026-09-09', 60, 1, 'MANUAL', 'x', 'x')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM client WHERE id = 1")
    assert (
        conn.execute("SELECT record_method FROM v_session_log WHERE uuid='u2'").fetchone()[0]
        == "Manual"
    )
    indexes = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {
        "idx_entry_local_date",
        "idx_entry_started",
        "idx_entry_client",
        "idx_entry_type",
        "idx_entry_totals",
    } <= indexes
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='entry_v2'").fetchone() is None
    # And it equals a fresh build (the drift guard, applied to an upgraded file).
    fresh = connect(":memory:")
    execute_script(fresh, CURRENT_DDL)
    assert _schema(conn) == _schema(fresh)
    conn.close()


def test_v3_to_v4_rebuilds_running_timer_and_keeps_the_leftover_row(
    tmp_path: Path, clock: FakeClock
) -> None:
    """v4 adds ``running_timer.paused_seconds`` (FR-212); a crash-recovery row survives."""
    from timetracker.data.schema import DDL_V3

    db = tmp_path / "v3.sqlite3"
    conn = connect(db)
    execute_script(conn, DDL_V3)
    conn.execute(
        "INSERT INTO running_timer (id, started_at_utc, tz_name, accrued_seconds, "
        "paused_since_utc, note, heartbeat_at_utc, heartbeat_accrued_sec) "
        "VALUES (1, '2026-09-16T07:00:00Z', 'UTC', 500, '2026-09-16T07:09:00Z', 'n', "
        "'2026-09-16T07:09:00Z', 500)"
    )
    for v in (1, 2, 3):
        conn.execute("INSERT INTO schema_migration (version, applied_at) VALUES (?, 'x')", (v,))
    set_user_version(conn, 3)
    conn.close()

    conn = connect(db)
    result = migrate(conn, db, clock=clock)
    assert result.applied == [4]
    assert user_version(conn) == 4
    row = conn.execute("SELECT * FROM running_timer").fetchone()
    assert (
        row["accrued_seconds"],
        row["paused_since_utc"],
        row["note"],
        row["paused_seconds"],
    ) == (
        500,
        "2026-09-16T07:09:00Z",
        "n",
        0,
    )
    assert (
        conn.execute("SELECT name FROM sqlite_master WHERE name='running_timer_v3'").fetchone()
        is None
    )
    fresh = connect(":memory:")
    execute_script(fresh, CURRENT_DDL)
    assert _schema(conn) == _schema(fresh)
    conn.close()
