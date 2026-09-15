"""BackupService: backup, validated restore, full export (FR-802, FR-804)."""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from timetracker.core.clock import FakeClock
from timetracker.core.models import Dimension, NewEntry, RecordMethod
from timetracker.data.db import connect, set_user_version, user_version
from timetracker.data.entry_repo import EntryRepo
from timetracker.data.label_repo import LabelRepo
from timetracker.data.migrate import migrate
from timetracker.data.schema import TARGET_VERSION
from timetracker.services.backup_service import BackupService, RestoreError


@pytest.fixture
def live(tmp_path: Path, clock: FakeClock) -> tuple[Path, sqlite3.Connection, BackupService]:
    db = tmp_path / "timetracker.sqlite3"
    conn = connect(db)
    migrate(conn, db, clock=clock)
    clients = LabelRepo(conn, Dimension.CLIENT, clock)
    types = LabelRepo(conn, Dimension.TYPE, clock)
    nike = clients.create("Nike")
    work = types.create("Work")
    types.set_archived(work.id, True)
    entries = EntryRepo(conn, clock)
    t0 = datetime(2026, 9, 8, 7, 0, tzinfo=UTC)
    for i in range(3):
        start = t0 + timedelta(hours=i)
        entries.insert(
            NewEntry(
                start,
                start + timedelta(minutes=30),
                "Europe/Brussels",
                1800,
                RecordMethod.QUICKADD,
                nike.id,
                work.id,
                f"note {i}",
            )
        )
    return db, conn, BackupService(clock, db, conn)


def test_backup_is_a_complete_standalone_copy(
    live: tuple[Path, sqlite3.Connection, BackupService], qtbot
) -> None:  # type: ignore[no-untyped-def]
    db, conn, svc = live
    with qtbot.waitSignal(svc.backup_created, timeout=1000) as blocker:
        path = svc.backup_now()
    assert blocker.args == [path]
    assert path.name == "timetracker-backup-20260911-120000.sqlite3"  # local time of the FakeClock
    assert svc.list_backups() == [path]
    copy = connect(path, read_only=True)
    assert copy.execute("SELECT COUNT(*) FROM entry").fetchone()[0] == 3
    assert user_version(copy) == TARGET_VERSION
    assert copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    copy.close()
    # The live file keeps working afterwards.
    conn.execute("INSERT INTO setting (key, value) VALUES ('k', '1')")


def test_inspect_rejects_garbage_and_newer_schemas(
    live: tuple[Path, sqlite3.Connection, BackupService], tmp_path: Path, clock: FakeClock
) -> None:
    _db, _conn, svc = live
    with pytest.raises(RestoreError, match="not a file"):
        svc.inspect(tmp_path / "missing.sqlite3")
    junk = tmp_path / "junk.sqlite3"
    junk.write_bytes(b"not a database at all" * 10)
    with pytest.raises(RestoreError):
        svc.inspect(junk)
    other = tmp_path / "other.sqlite3"
    c = connect(other)
    c.execute("CREATE TABLE unrelated (x)")
    c.close()
    with pytest.raises(RestoreError, match="not a Time Tracker database"):
        svc.inspect(other)
    future = tmp_path / "future.sqlite3"
    c = connect(future)
    migrate(c, future, clock=clock)
    set_user_version(c, TARGET_VERSION + 5)
    c.close()
    with pytest.raises(RestoreError, match="newer version"):
        svc.inspect(future)


def test_restore_keeps_a_pre_restore_copy_and_swaps_the_file(
    live: tuple[Path, sqlite3.Connection, BackupService], tmp_path: Path, clock: FakeClock, qtbot
) -> None:  # type: ignore[no-untyped-def]
    db, _conn, svc = live
    candidate = tmp_path / "older.sqlite3"
    c = connect(candidate)
    migrate(c, candidate, clock=clock)
    c.execute("INSERT INTO client (name, name_norm, created_at) VALUES ('Puma', 'puma', 'x')")
    c.close()
    info = svc.inspect(candidate)
    assert (info.entries, info.schema_version) == (0, TARGET_VERSION)

    with qtbot.waitSignal(svc.restore_ready, timeout=1000) as blocker:
        pre = svc.restore(candidate)
    assert blocker.args == [pre]
    assert pre.name.startswith("timetracker-pre-restore-")
    kept = connect(pre, read_only=True)
    assert kept.execute("SELECT COUNT(*) FROM entry").fetchone()[0] == 3  # what we had
    kept.close()
    fresh = connect(db)
    assert fresh.execute("SELECT COUNT(*) FROM entry").fetchone()[0] == 0
    assert fresh.execute("SELECT name FROM client").fetchone()[0] == "Puma"
    fresh.close()


def test_full_export_json_and_csv(
    live: tuple[Path, sqlite3.Connection, BackupService], tmp_path: Path
) -> None:
    _db, _conn, svc = live
    out = svc.full_export(tmp_path / "all.json")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema_version"] == TARGET_VERSION
    assert [c["name"] for c in data["clients"]] == ["Nike"]
    assert data["types"] == [
        {
            "name": "Work",
            "is_archived": True,
            "is_pinned": False,
            "colour": None,
            "created_at": "2026-09-11T10:00:00Z",
            "last_used_at": None,
        }
    ]
    assert len(data["entries"]) == 3
    assert data["entries"][0]["client"] == "Nike" and data["entries"][0]["type"] == "Work"
    assert data["entries"][0]["record_method"] == "QUICKADD"
    assert "settings" in data

    out = svc.full_export(tmp_path / "all.csv")
    with open(out, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0][:3] == ["uuid", "started_at_utc", "ended_at_utc"]
    assert len(rows) == 4
    assert rows[1][7:9] == ["Nike", "Work"]
    assert rows[1][10] == "QUICKADD"
