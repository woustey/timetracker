"""v4: ``running_timer.paused_seconds`` — the completed pauses of the running timer (FR-212).

Rebuilt rather than ``ALTER TABLE … ADD COLUMN`` so ``sqlite_master`` stays
byte-identical to a fresh build (the drift guard in ``tests/data/test_migrate.py``).
A leftover row — a crash to recover from — is carried over with ``0`` paused.
"""

from __future__ import annotations

import sqlite3

from timetracker.data.db import execute_script
from timetracker.data.schema import RUNNING_TIMER_V4

version = 4

_COLUMNS = (
    "id, started_at_utc, tz_name, accrued_seconds, paused_since_utc, client_id, type_id, note, "
    "heartbeat_at_utc, heartbeat_accrued_sec"
)


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE running_timer RENAME TO running_timer_v3")
    execute_script(conn, RUNNING_TIMER_V4)
    conn.execute(f"INSERT INTO running_timer ({_COLUMNS}) SELECT {_COLUMNS} FROM running_timer_v3")
    conn.execute("DROP TABLE running_timer_v3")
