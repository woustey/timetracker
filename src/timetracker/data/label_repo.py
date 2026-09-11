"""Client and work-type labels (FR-401–FR-405, FR-409).

One class serves both dimensions; ``Dimension.value`` is the table name. The
two tables are identical by design (PRD-02 §4.1).
"""

from __future__ import annotations

import sqlite3

from timetracker.core.clock import Clock
from timetracker.core.errors import DuplicateLabelError, LabelInUseError, NotFoundError
from timetracker.core.models import Dimension, Label, clean_label_name, normalise_label_name
from timetracker.core.timeutil import from_iso_utc, to_iso_utc
from timetracker.data.db import transaction

SEED_TYPES = ("Email/Chat", "Phone", "Meeting/Call", "Work")

_COLUMNS = "id, name, name_norm, colour, is_archived, is_pinned, created_at, last_used_at"


class LabelRepo:
    def __init__(self, conn: sqlite3.Connection, dimension: Dimension, clock: Clock) -> None:
        self._conn = conn
        self._dim = dimension
        self._table = dimension.value
        self._clock = clock

    @property
    def dimension(self) -> Dimension:
        return self._dim

    # -- create --------------------------------------------------------------

    def create(self, name: str, *, colour: str | None = None) -> Label:
        """Insert a new label. Raises :class:`DuplicateLabelError` on a normalised match."""
        display = clean_label_name(name)
        norm = normalise_label_name(display)
        existing = self.find_by_name(name)
        if existing is not None:
            raise DuplicateLabelError(f"{self._dim.name.lower()} '{existing.name}' already exists")
        now = to_iso_utc(self._clock.now_utc())
        with transaction(self._conn):
            cur = self._conn.execute(
                f"INSERT INTO {self._table} (name, name_norm, colour, created_at) "
                "VALUES (?, ?, ?, ?)",
                (display, norm, colour, now),
            )
        return self.get(int(cur.lastrowid or 0))

    def get_or_create(self, name: str) -> Label:
        """The FR-401 path: a typed value becomes a chip, or resolves to the existing one."""
        found = self.find_by_name(name)
        return found if found is not None else self.create(name)

    def ensure_seed(self, names: tuple[str, ...] = SEED_TYPES) -> list[Label]:
        """First-run seed (FR-409): only when the table is empty, so archiving sticks."""
        if self.count(include_archived=True) > 0:
            return []
        return [self.create(n) for n in names]

    # -- read ----------------------------------------------------------------

    def get(self, label_id: int) -> Label:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM {self._table} WHERE id = ?", (label_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"{self._dim.name.lower()} id {label_id}")
        return self._to_label(row)

    def find_by_name(self, name: str) -> Label | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM {self._table} WHERE name_norm = ?",
            (normalise_label_name(name),),
        ).fetchone()
        return None if row is None else self._to_label(row)

    def list_all(self, *, include_archived: bool = False) -> list[Label]:
        """Pinned first, then most recently used, then creation order (FR-407 default).

        Creation order rather than alphabetical keeps the seed types in the
        mockup's order and puts a freshly typed label at the end of its column.
        """
        where = "" if include_archived else "WHERE is_archived = 0"
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM {self._table} {where} "
            "ORDER BY is_pinned DESC, last_used_at IS NULL, last_used_at DESC, id ASC"
        ).fetchall()
        return [self._to_label(r) for r in rows]

    def count(self, *, include_archived: bool = False) -> int:
        where = "" if include_archived else "WHERE is_archived = 0"
        row = self._conn.execute(f"SELECT COUNT(*) FROM {self._table} {where}").fetchone()
        return int(row[0])

    def entry_count(self, label_id: int) -> int:
        column = "client_id" if self._dim is Dimension.CLIENT else "type_id"
        row = self._conn.execute(
            f"SELECT COUNT(*) FROM entry WHERE {column} = ?", (label_id,)
        ).fetchone()
        return int(row[0])

    # -- update --------------------------------------------------------------

    def rename(self, label_id: int, new_name: str) -> Label:
        """Rename in place; entries reference the id so they follow (FR-404)."""
        display = clean_label_name(new_name)
        norm = normalise_label_name(display)
        clash = self.find_by_name(display)
        if clash is not None and clash.id != label_id:
            raise DuplicateLabelError(f"'{clash.name}' already exists")
        with transaction(self._conn):
            self._require(label_id)
            self._conn.execute(
                f"UPDATE {self._table} SET name = ?, name_norm = ? WHERE id = ?",
                (display, norm, label_id),
            )
        return self.get(label_id)

    def set_archived(self, label_id: int, archived: bool) -> Label:
        with transaction(self._conn):
            self._require(label_id)
            self._conn.execute(
                f"UPDATE {self._table} SET is_archived = ? WHERE id = ?",
                (int(archived), label_id),
            )
        return self.get(label_id)

    def set_pinned(self, label_id: int, pinned: bool) -> Label:
        with transaction(self._conn):
            self._require(label_id)
            self._conn.execute(
                f"UPDATE {self._table} SET is_pinned = ? WHERE id = ?",
                (int(pinned), label_id),
            )
        return self.get(label_id)

    def set_colour(self, label_id: int, colour: str | None) -> Label:
        with transaction(self._conn):
            self._require(label_id)
            self._conn.execute(
                f"UPDATE {self._table} SET colour = ? WHERE id = ?", (colour, label_id)
            )
        return self.get(label_id)

    def touch_last_used(self, label_id: int) -> None:
        now = to_iso_utc(self._clock.now_utc())
        with transaction(self._conn):
            self._conn.execute(
                f"UPDATE {self._table} SET last_used_at = ? WHERE id = ?", (now, label_id)
            )

    # -- delete --------------------------------------------------------------

    def delete(self, label_id: int) -> None:
        """Hard delete. Refused when any entry references the label (FR-405)."""
        with transaction(self._conn):
            self._require(label_id)
            try:
                self._conn.execute(f"DELETE FROM {self._table} WHERE id = ?", (label_id,))
            except sqlite3.IntegrityError as exc:
                raise LabelInUseError(
                    f"{self._dim.name.lower()} id {label_id} is referenced by entries; "
                    "archive it instead"
                ) from exc

    # -- internals -----------------------------------------------------------

    def _require(self, label_id: int) -> None:
        row = self._conn.execute(
            f"SELECT 1 FROM {self._table} WHERE id = ?", (label_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"{self._dim.name.lower()} id {label_id}")

    def _to_label(self, row: sqlite3.Row) -> Label:
        return Label(
            id=int(row["id"]),
            dimension=self._dim,
            name=str(row["name"]),
            name_norm=str(row["name_norm"]),
            colour=row["colour"],
            is_archived=bool(row["is_archived"]),
            is_pinned=bool(row["is_pinned"]),
            created_at=from_iso_utc(row["created_at"]),
            last_used_at=(
                None if row["last_used_at"] is None else from_iso_utc(row["last_used_at"])
            ),
        )
