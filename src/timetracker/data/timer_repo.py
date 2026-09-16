"""The ``running_timer`` singleton row (PRD-02 §4.1, FR-207).

Only ``TimerService`` may call the writers here. ``heartbeat()`` is the durable
copy that crash recovery reads; ``save()`` writes the full state.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from timetracker.core.models import RunningTimer
from timetracker.core.timeutil import from_iso_utc, to_iso_utc
from timetracker.data.db import transaction

_COLUMNS = (
    "started_at_utc, tz_name, accrued_seconds, paused_since_utc, paused_seconds, client_id, "
    "type_id, note, heartbeat_at_utc, heartbeat_accrued_sec"
)


class TimerRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self) -> RunningTimer | None:
        row = self._conn.execute(f"SELECT {_COLUMNS} FROM running_timer WHERE id = 1").fetchone()
        return None if row is None else _to_timer(row)

    def save(self, timer: RunningTimer) -> None:
        """Insert or replace the singleton with the full state."""
        with transaction(self._conn):
            self._conn.execute(
                f"INSERT OR REPLACE INTO running_timer (id, {_COLUMNS}) "
                "VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    to_iso_utc(timer.started_at_utc),
                    timer.tz_name,
                    timer.accrued_seconds,
                    None if timer.paused_since_utc is None else to_iso_utc(timer.paused_since_utc),
                    timer.paused_seconds,
                    timer.client_id,
                    timer.type_id,
                    timer.note,
                    to_iso_utc(timer.heartbeat_at_utc),
                    timer.heartbeat_accrued_sec,
                ),
            )

    def heartbeat(self, accrued_seconds: int, at: datetime) -> bool:
        """Advance the durable copy. Returns ``False`` if no timer row exists."""
        with transaction(self._conn):
            cur = self._conn.execute(
                "UPDATE running_timer SET accrued_seconds = ?, heartbeat_accrued_sec = ?, "
                "heartbeat_at_utc = ? WHERE id = 1",
                (accrued_seconds, accrued_seconds, to_iso_utc(at)),
            )
        return cur.rowcount == 1

    def clear(self) -> None:
        with transaction(self._conn):
            self._conn.execute("DELETE FROM running_timer WHERE id = 1")


def _to_timer(row: sqlite3.Row) -> RunningTimer:
    return RunningTimer(
        started_at_utc=from_iso_utc(row["started_at_utc"]),
        tz_name=str(row["tz_name"]),
        accrued_seconds=int(row["accrued_seconds"]),
        paused_since_utc=(
            None if row["paused_since_utc"] is None else from_iso_utc(row["paused_since_utc"])
        ),
        paused_seconds=int(row["paused_seconds"]),
        client_id=row["client_id"],
        type_id=row["type_id"],
        note=row["note"],
        heartbeat_at_utc=from_iso_utc(row["heartbeat_at_utc"]),
        heartbeat_accrued_sec=int(row["heartbeat_accrued_sec"]),
    )
