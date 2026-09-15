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
from timetracker.core.models import NOTE_MAX_CHARS, Dimension, Entry, NewEntry, RecordMethod
from timetracker.core.timeutil import from_iso_utc, local_date_for, to_iso_utc
from timetracker.data.db import transaction

_COLUMN_NAMES = (
    "id, uuid, started_at_utc, ended_at_utc, tz_name, local_date, duration_seconds, "
    "paused_seconds, client_id, type_id, note, record_method, is_edited, created_at, modified_at"
)
_COLUMNS = _COLUMN_NAMES
_E_COLUMNS = ", ".join(f"e.{c.strip()}" for c in _COLUMN_NAMES.split(","))

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


# Sortable columns for the log window, mapped to safe ORDER BY fragments.
SORT_COLUMNS: dict[str, str] = {
    "started_at_utc": "started_at_utc",
    "ended_at_utc": "ended_at_utc",
    "duration_seconds": "duration_seconds",
    "client": "client_name",
    "type": "type_name",
    "record_method": "record_method",
    "note": "note",
    "local_date": "local_date",
}


@dataclass(frozen=True, slots=True)
class EntryFilter:
    date_from: date | None = None  # inclusive, local
    date_to: date | None = None  # inclusive, local
    client_id: int | None = None
    type_id: int | None = None
    record_method: RecordMethod | None = None
    note_contains: str | None = None


@dataclass(frozen=True, slots=True)
class ExportRow:
    """One export line: the entry plus its label names, joined in one query (no N+1)."""

    entry: Entry
    client_name: str | None
    type_name: str | None


@dataclass(frozen=True, slots=True)
class LabelTotal:
    label_id: int | None
    name: str | None
    seconds: int
    count: int


@dataclass(frozen=True, slots=True)
class Summary:
    """Everything the log footer shows (FR-504), from a single grouped scan."""

    count: int
    seconds: int
    by_client: list[LabelTotal]
    by_type: list[LabelTotal]


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
        sort_by: str = "started_at_utc",
    ) -> list[Entry]:
        """Filtered, sorted, paged entries. Sorting is SQL so 50 000 rows stay fast (NFR-04)."""
        return [
            row.entry
            for row in self.export_rows(
                flt, newest_first=newest_first, limit=limit, offset=offset, sort_by=sort_by
            )
        ]

    def export_rows(
        self,
        flt: EntryFilter | None = None,
        *,
        newest_first: bool = True,
        limit: int | None = None,
        offset: int = 0,
        sort_by: str = "started_at_utc",
    ) -> list[ExportRow]:
        """Filtered, sorted, paged rows with label names.

        The entry table is filtered, sorted and limited *first*; names are joined
        onto the page only. Sorting by a label column uses a ``CASE`` over the
        (few) label ids in name order, so no join is needed before the sort —
        this is what keeps a 50 000-row sort under the NFR-04 budget.
        """
        column = SORT_COLUMNS.get(sort_by)
        if column is None:
            raise ValidationError(f"cannot sort by {sort_by!r}")
        where, params = _where(flt or EntryFilter())
        order = "DESC" if newest_first else "ASC"

        def sort_expr(p: str) -> str:
            if column in ("client_name", "type_name"):
                id_column = "client_id" if column == "client_name" else "type_id"
                table = "client" if column == "client_name" else "work_type"
                ranks = self._conn.execute(
                    f"SELECT id FROM {table} ORDER BY name_norm {order}"
                ).fetchall()
                if not ranks:
                    return f"({p}{id_column} IS NULL) ASC"
                case = " ".join(f"WHEN {int(r['id'])} THEN {i}" for i, r in enumerate(ranks))
                return f"({p}{id_column} IS NULL) ASC, CASE {p}{id_column} {case} END ASC"
            if column == "note":
                return f"({p}note IS NULL) ASC, {p}note {order}"
            return f"{p}{column} {order}"

        inner = (
            f"SELECT {_COLUMNS} FROM entry {where} "
            f"ORDER BY {sort_expr('')}, started_at_utc {order}, id {order}"
        )
        if limit is not None:
            inner += " LIMIT ? OFFSET ?"
            params = [*params, limit, offset]
        # The outer ORDER BY repeats the sort over the page only (cheap) because
        # SQLite does not promise to keep a subquery's order through a join.
        sql = (
            f"SELECT {_E_COLUMNS}, c.name AS client_name, t.name AS type_name "
            f"FROM ({inner}) e "
            "LEFT JOIN client c ON c.id = e.client_id LEFT JOIN work_type t ON t.id = e.type_id "
            f"ORDER BY {sort_expr('e.')}, e.started_at_utc {order}, e.id {order}"
        )
        return [
            ExportRow(_to_entry(r), r["client_name"], r["type_name"])
            for r in self._conn.execute(sql, params).fetchall()
        ]

    def summary(self, flt: EntryFilter | None = None) -> Summary:
        """Count, grand total and both subtotal lists from one ``GROUP BY client_id, type_id``."""
        where, params = _where(flt or EntryFilter())
        rows = self._conn.execute(
            "SELECT client_id, type_id, COALESCE(SUM(duration_seconds), 0) AS seconds, "
            f"COUNT(*) AS n FROM entry {where} GROUP BY client_id, type_id",
            params,
        ).fetchall()
        client_names = self._names("client")
        type_names = self._names("work_type")
        by_client: dict[int | None, list[int]] = {}
        by_type: dict[int | None, list[int]] = {}
        count = 0
        seconds = 0
        for r in rows:
            c = None if r["client_id"] is None else int(r["client_id"])
            t = None if r["type_id"] is None else int(r["type_id"])
            sec, n = int(r["seconds"]), int(r["n"])
            count += n
            seconds += sec
            for bucket, key in ((by_client, c), (by_type, t)):
                acc = bucket.setdefault(key, [0, 0])
                acc[0] += sec
                acc[1] += n
        return Summary(
            count,
            seconds,
            _totals(by_client, client_names),
            _totals(by_type, type_names),
        )

    def totals_by(self, dimension: Dimension, flt: EntryFilter | None = None) -> list[LabelTotal]:
        """FR-504 subtotals for one dimension (see :meth:`summary` for both at once)."""
        summary = self.summary(flt)
        return summary.by_client if dimension is Dimension.CLIENT else summary.by_type

    def _names(self, table: str) -> dict[int, str]:
        return {
            int(r["id"]): str(r["name"])
            for r in self._conn.execute(f"SELECT id, name FROM {table}").fetchall()
        }

    def overlapping_ids(self, flt: EntryFilter | None = None) -> set[int]:
        """Ids of entries overlapping another entry within the filter (FR-508).

        Ordered by start: an entry overlaps its *predecessors* when it starts
        before the running max end so far, and overlaps its *successor* when
        the next entry starts before it ends. The union flags both partners of
        every pair. Two window functions, one sort, fine at 50 000 rows.
        """
        where, params = _where(flt or EntryFilter())
        where = f"{where} AND" if where else "WHERE"
        sql = (
            "WITH f AS (SELECT id, started_at_utc, ended_at_utc FROM entry "
            f"{where} ended_at_utc > started_at_utc), "
            "w AS (SELECT id, started_at_utc, ended_at_utc, "
            "MAX(ended_at_utc) OVER (ORDER BY started_at_utc "
            "ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prev_end, "
            "LEAD(started_at_utc) OVER (ORDER BY started_at_utc) AS next_start FROM f) "
            "SELECT id FROM w WHERE (prev_end IS NOT NULL AND started_at_utc < prev_end) "
            "OR (next_start IS NOT NULL AND ended_at_utc > next_start)"
        )
        return {int(r["id"]) for r in self._conn.execute(sql, params).fetchall()}

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

    def date_bounds(self) -> tuple[date, date] | None:
        """Earliest and latest local dates in the table, or ``None`` when empty."""
        row = self._conn.execute("SELECT MIN(local_date), MAX(local_date) FROM entry").fetchone()
        if row is None or row[0] is None:
            return None
        return date.fromisoformat(row[0]), date.fromisoformat(row[1])

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


def _totals(bucket: dict[int | None, list[int]], names: dict[int, str]) -> list[LabelTotal]:
    totals = [
        LabelTotal(key, None if key is None else names.get(key), sec, n)
        for key, (sec, n) in bucket.items()
    ]
    totals.sort(key=lambda t: (-t.seconds, t.name or "￿"))
    return totals


def _where(flt: EntryFilter, prefix: str = "") -> tuple[str, list[object]]:
    p = prefix
    clauses: list[str] = []
    params: list[object] = []
    if flt.date_from is not None:
        clauses.append(f"{p}local_date >= ?")
        params.append(flt.date_from.isoformat())
    if flt.date_to is not None:
        clauses.append(f"{p}local_date <= ?")
        params.append(flt.date_to.isoformat())
    if flt.client_id is not None:
        clauses.append(f"{p}client_id = ?")
        params.append(flt.client_id)
    if flt.type_id is not None:
        clauses.append(f"{p}type_id = ?")
        params.append(flt.type_id)
    if flt.record_method is not None:
        clauses.append(f"{p}record_method = ?")
        params.append(flt.record_method.value)
    if flt.note_contains:
        clauses.append(f"{p}note LIKE ? ESCAPE '\\'")
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
