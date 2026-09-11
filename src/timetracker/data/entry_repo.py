"""Entries — the rows of the session log (PRD-01 §7.1, PRD-02 §4.1).

``duration_seconds`` is stored exactly as supplied and is never computed from
the timestamps here or anywhere else. ``local_date`` is denormalised from
``started_at_utc`` + ``tz_name`` on every write that touches either.
"""

from __future__ import annotations

import sqlite3
import uuid as uuidlib
from dataclasses import dataclass
from datetime import date, datetime

from timetracker.core.clock import Clock
from timetracker.core.errors import NotFoundError, ValidationError
from timetracker.core.models import NOTE_MAX_CHARS, Entry, NewEntry, RecordMethod
from timetracker.core.timeutil import from_iso_utc, local_date_for, to_iso_utc
from timetracker.data.db import transaction

_COLUMNS = (
    "id, uuid, started_at_utc, ended_at_utc, tz_name, local_date, duration_seconds, "
    "paused_seconds, client_id, type_id, note, record_method, is_edited, created_at, modified_at"
)

# Fields a caller may change through update(). record_method is deliberately absent (FR-505).
_EDITABLE = frozenset(
    {
        "started_at_utc",
        "ended_at_utc",
        "tz_name",
        "duration_seconds",
        "paused_seconds",
        "client_id",
        "type_id",
        "note",
    }
)


@dataclass(frozen=True, slots=True)
class EntryFilter:
    date_from: date | None = None  # inclusive, local
    date_to: date | None = None  # inclusive, local
    client_id: int | None = None
    type_id: int | None = None
    record_method: RecordMethod | None = None
    note_contains: str | None = None


class EntryRepo:
    def __init__(self, conn: sqlite3.Connection, clock: Clock) -> None:
        self._conn = conn
        self._clock = clock

    # -- create --------------------------------------------------------------

    def insert(self, new: NewEntry) -> Entry:
        new.validate()
        now = to_iso_utc(self._clock.now_utc())
        entry_uuid = new.uuid or str(uuidlib.uuid4())
        local = local_date_for(new.started_at_utc, new.tz_name).isoformat()
        with transaction(self._conn):
            cur = self._conn.execute(
                "INSERT INTO entry (uuid, started_at_utc, ended_at_utc, tz_name, local_date, "
                "duration_seconds, paused_seconds, client_id, type_id, note, record_method, "
                "is_edited, created_at, modified_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
                (
                    entry_uuid,
                    to_iso_utc(new.started_at_utc),
                    to_iso_utc(new.ended_at_utc),
                    new.tz_name,
                    local,
                    new.duration_seconds,
                    new.paused_seconds,
                    new.client_id,
                    new.type_id,
                    new.note,
                    new.record_method.value,
                    now,
                    now,
                ),
            )
        return self.get(int(cur.lastrowid or 0))

    # -- read ----------------------------------------------------------------

    def get(self, entry_id: int) -> Entry:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM entry WHERE id = ?", (entry_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"entry id {entry_id}")
        return _to_entry(row)

    def get_by_uuid(self, entry_uuid: str) -> Entry:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM entry WHERE uuid = ?", (entry_uuid,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"entry uuid {entry_uuid}")
        return _to_entry(row)

    def query(
        self,
        flt: EntryFilter | None = None,
        *,
        newest_first: bool = True,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Entry]:
        where, params = _where(flt or EntryFilter())
        order = "DESC" if newest_first else "ASC"
        sql = f"SELECT {_COLUMNS} FROM entry {where} ORDER BY started_at_utc {order}, id {order}"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params = [*params, limit, offset]
        return [_to_entry(r) for r in self._conn.execute(sql, params).fetchall()]

    def list_for_date(self, local_date: date) -> list[Entry]:
        """Entries on a local calendar day, oldest first — the shape anchoring needs (§5.4)."""
        return self.query(EntryFilter(date_from=local_date, date_to=local_date), newest_first=False)

    def recent(self, n: int) -> list[Entry]:
        return self.query(limit=n)

    def count(self, flt: EntryFilter | None = None) -> int:
        where, params = _where(flt or EntryFilter())
        row = self._conn.execute(f"SELECT COUNT(*) FROM entry {where}", params).fetchone()
        return int(row[0])

    def total_seconds(self, flt: EntryFilter | None = None) -> int:
        """SQL aggregate over the filter predicate, never a sum of loaded rows (§8.3)."""
        where, params = _where(flt or EntryFilter())
        row = self._conn.execute(
            f"SELECT COALESCE(SUM(duration_seconds), 0) FROM entry {where}", params
        ).fetchone()
        return int(row[0])

    def total_seconds_for_date(self, local_date: date) -> int:
        return self.total_seconds(EntryFilter(date_from=local_date, date_to=local_date))

    # -- update --------------------------------------------------------------

    def update(self, entry_id: int, **changes: object) -> Entry:
        """Apply field changes; marks ``is_edited`` and recomputes ``local_date`` (FR-505)."""
        unknown = set(changes) - _EDITABLE
        if unknown:
            raise ValidationError(f"not editable: {sorted(unknown)}")
        if not changes:
            return self.get(entry_id)
        current = self.get(entry_id)
        merged = current.with_changes(**changes)
        _validate_entry(merged)
        now = to_iso_utc(self._clock.now_utc())
        with transaction(self._conn):
            self._conn.execute(
                "UPDATE entry SET started_at_utc = ?, ended_at_utc = ?, tz_name = ?, "
                "local_date = ?, duration_seconds = ?, paused_seconds = ?, client_id = ?, "
                "type_id = ?, note = ?, is_edited = 1, modified_at = ? WHERE id = ?",
                (
                    to_iso_utc(merged.started_at_utc),
                    to_iso_utc(merged.ended_at_utc),
                    merged.tz_name,
                    local_date_for(merged.started_at_utc, merged.tz_name).isoformat(),
                    merged.duration_seconds,
                    merged.paused_seconds,
                    merged.client_id,
                    merged.type_id,
                    merged.note,
                    now,
                    entry_id,
                ),
            )
        return self.get(entry_id)

    # -- delete --------------------------------------------------------------

    def delete(self, entry_id: int) -> Entry:
        """Delete and return the removed entry so the caller can offer undo (FR-506)."""
        entry = self.get(entry_id)
        with transaction(self._conn):
            self._conn.execute("DELETE FROM entry WHERE id = ?", (entry_id,))
        return entry

    def restore(self, entry: Entry) -> Entry:
        """Re-insert a deleted entry with its original uuid and audit fields (undo)."""
        with transaction(self._conn):
            cur = self._conn.execute(
                "INSERT INTO entry (uuid, started_at_utc, ended_at_utc, tz_name, local_date, "
                "duration_seconds, paused_seconds, client_id, type_id, note, record_method, "
                "is_edited, created_at, modified_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.uuid,
                    to_iso_utc(entry.started_at_utc),
                    to_iso_utc(entry.ended_at_utc),
                    entry.tz_name,
                    entry.local_date.isoformat(),
                    entry.duration_seconds,
                    entry.paused_seconds,
                    entry.client_id,
                    entry.type_id,
                    entry.note,
                    entry.record_method.value,
                    int(entry.is_edited),
                    to_iso_utc(entry.created_at),
                    to_iso_utc(entry.modified_at),
                ),
            )
        return self.get(int(cur.lastrowid or 0))


# -- helpers -----------------------------------------------------------------


def _where(flt: EntryFilter) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if flt.date_from is not None:
        clauses.append("local_date >= ?")
        params.append(flt.date_from.isoformat())
    if flt.date_to is not None:
        clauses.append("local_date <= ?")
        params.append(flt.date_to.isoformat())
    if flt.client_id is not None:
        clauses.append("client_id = ?")
        params.append(flt.client_id)
    if flt.type_id is not None:
        clauses.append("type_id = ?")
        params.append(flt.type_id)
    if flt.record_method is not None:
        clauses.append("record_method = ?")
        params.append(flt.record_method.value)
    if flt.note_contains:
        clauses.append("note LIKE ? ESCAPE '\\'")
        needle = flt.note_contains.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.append(f"%{needle}%")
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def _validate_entry(entry: Entry) -> None:
    if entry.duration_seconds < 0:
        raise ValidationError("duration_seconds must be >= 0")
    if entry.paused_seconds < 0:
        raise ValidationError("paused_seconds must be >= 0")
    if entry.ended_at_utc < entry.started_at_utc:
        raise ValidationError("ended_at_utc is before started_at_utc")
    if entry.note is not None and len(entry.note) > NOTE_MAX_CHARS:
        raise ValidationError(f"note exceeds {NOTE_MAX_CHARS} characters")
    if not isinstance(entry.started_at_utc, datetime) or not isinstance(
        entry.ended_at_utc, datetime
    ):
        raise ValidationError("timestamps must be datetimes")


def _to_entry(row: sqlite3.Row) -> Entry:
    return Entry(
        id=int(row["id"]),
        uuid=str(row["uuid"]),
        started_at_utc=from_iso_utc(row["started_at_utc"]),
        ended_at_utc=from_iso_utc(row["ended_at_utc"]),
        tz_name=str(row["tz_name"]),
        local_date=date.fromisoformat(row["local_date"]),
        duration_seconds=int(row["duration_seconds"]),
        paused_seconds=int(row["paused_seconds"]),
        client_id=row["client_id"],
        type_id=row["type_id"],
        note=row["note"],
        record_method=RecordMethod(row["record_method"]),
        is_edited=bool(row["is_edited"]),
        created_at=from_iso_utc(row["created_at"]),
        modified_at=from_iso_utc(row["modified_at"]),
    )
