"""v3: a third record method, ``MANUAL`` — entries added through the log window's form.

``record_method`` is guarded by a CHECK constraint and SQLite cannot alter one,
so the table is rebuilt: rename the old table away, create ``entry`` with the
exact current DDL (so ``sqlite_master`` matches a fresh build), copy every row,
drop the old table, and recreate the indexes and the view. All inside the
migration's transaction.
"""

from __future__ import annotations

import sqlite3

from timetracker.data.db import execute_script
from timetracker.data.schema import ENTRY_INDEXES_V1, ENTRY_INDEXES_V2, ENTRY_TABLE_V3, VIEW_V3

version = 3

_COLUMNS = (
    "id, uuid, started_at_utc, ended_at_utc, tz_name, local_date, duration_seconds, "
    "paused_seconds, client_id, type_id, note, record_method, is_edited, created_at, modified_at"
)


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute("DROP VIEW IF EXISTS v_session_log")
    conn.execute("ALTER TABLE entry RENAME TO entry_v2")
    execute_script(conn, ENTRY_TABLE_V3)
    conn.execute(f"INSERT INTO entry ({_COLUMNS}) SELECT {_COLUMNS} FROM entry_v2")
    conn.execute("DROP TABLE entry_v2")
    execute_script(conn, ENTRY_INDEXES_V1)
    execute_script(conn, ENTRY_INDEXES_V2)
    execute_script(conn, VIEW_V3)
