"""Migration runner (PRD-02 §4.3, FR-806).

On launch:

1. Read ``PRAGMA user_version``.
2. If behind the code's target and the database is an existing file, copy it to
   ``timetracker-pre-v{n}.sqlite3`` before touching anything. A brand-new empty
   database has nothing to back up and gets none.
3. Apply each pending migration inside its own transaction, writing a
   ``schema_migration`` row and bumping ``user_version``.
4. If the database is *ahead* of the code, refuse with :class:`SchemaTooNewError`.

Running it on an up-to-date database is a no-op, so it is idempotent.
"""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from timetracker.core.clock import Clock, SystemClock
from timetracker.core.errors import SchemaTooNewError
from timetracker.core.timeutil import to_iso_utc
from timetracker.data.db import set_user_version, transaction, user_version
from timetracker.data.migrations import Migration, all_migrations
from timetracker.data.schema import TARGET_VERSION


@dataclass(frozen=True, slots=True)
class MigrationResult:
    from_version: int
    to_version: int
    applied: list[int] = field(default_factory=list)
    backup_path: Path | None = None

    @property
    def changed(self) -> bool:
        return bool(self.applied)


def migrate(
    conn: sqlite3.Connection,
    db_path: Path | None = None,
    *,
    clock: Clock | None = None,
) -> MigrationResult:
    """Bring *conn* to :data:`TARGET_VERSION`. *db_path* enables the pre-migration copy."""
    migrations = all_migrations()
    if migrations[-1].version != TARGET_VERSION:
        raise RuntimeError(
            f"schema.TARGET_VERSION is {TARGET_VERSION} but the last migration is "
            f"{migrations[-1].version}"
        )

    current = user_version(conn)
    if current > TARGET_VERSION:
        raise SchemaTooNewError(current, TARGET_VERSION)
    if current == TARGET_VERSION:
        return MigrationResult(current, current)

    backup = _backup_if_needed(conn, db_path, current)
    applied_at = to_iso_utc((clock or SystemClock()).now_utc())
    applied: list[int] = []
    for migration in migrations:
        if migration.version <= current:
            continue
        _apply(conn, migration, applied_at)
        applied.append(migration.version)
    return MigrationResult(current, TARGET_VERSION, applied, backup)


def _apply(conn: sqlite3.Connection, migration: Migration, applied_at: str) -> None:
    # SQLite DDL is transactional, so the whole step — DDL, bookkeeping row and
    # version bump — commits or rolls back as one. Migrations must therefore use
    # execute_script() rather than executescript(), which auto-commits first.
    with transaction(conn):
        migration.upgrade(conn)
        conn.execute(
            "INSERT INTO schema_migration (version, applied_at) VALUES (?, ?)",
            (migration.version, applied_at),
        )
        set_user_version(conn, migration.version)


def _backup_if_needed(conn: sqlite3.Connection, db_path: Path | None, current: int) -> Path | None:
    if db_path is None or current == 0 or not db_path.exists():
        return None
    backup = db_path.with_name(f"{db_path.stem}-pre-v{current}{db_path.suffix}")
    conn.execute("PRAGMA wal_checkpoint(FULL)")
    shutil.copy2(db_path, backup)
    return backup
