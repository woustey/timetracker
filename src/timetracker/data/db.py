"""Connection factory, pragmas and the transaction helper (PRD-02 §4.4).

One connection per thread; ``check_same_thread`` is left at its default so
misuse fails loudly. Rows come back as ``sqlite3.Row``; repositories convert to
dataclasses at the boundary so no ``Row`` escapes ``data/``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

MEMORY = ":memory:"


def connect(path: Path | str, *, read_only: bool = False) -> sqlite3.Connection:
    """Open *path* with the §4.1 pragmas applied. ``":memory:"`` is accepted for tests."""
    target = str(path)
    if read_only and target != MEMORY:
        uri = Path(target).resolve().as_uri().replace("file://", "file:", 1) + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, isolation_level=None)
    else:
        conn = sqlite3.connect(target, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    if target != MEMORY and not read_only:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """``BEGIN IMMEDIATE`` … ``COMMIT``, rolling back on any exception.

    The connection runs in autocommit mode (``isolation_level=None``) so that
    transaction boundaries are explicit and nested helpers cannot silently
    widen them.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0])


def set_user_version(conn: sqlite3.Connection, version: int) -> None:
    # PRAGMA does not accept bound parameters; version is an int we control.
    conn.execute(f"PRAGMA user_version = {int(version)}")


def execute_script(conn: sqlite3.Connection, sql: str) -> None:
    """Run a multi-statement script *without* the implicit COMMIT of ``executescript``.

    Statements are split on ``;`` using ``sqlite3.complete_statement`` so that a
    script can run inside an open transaction.
    """
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                conn.execute(statement)
            buffer = ""
    if buffer.strip():
        conn.execute(buffer.strip())
