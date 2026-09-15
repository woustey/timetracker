"""Entries: Add Time commits with undo (FR-311, FR-314), manual adds, edits and
deletes with a session undo stack (FR-505, FR-506).

The stopwatch path lives in ``TimerService`` (the only creator of ``STOPWATCH``
entries); this service is the only creator of ``QUICKADD`` (matrix) and
``MANUAL`` (log form) entries. Split and
merge (FR-507) are *should* and not implemented.

Edit policy (decided with the owner for M5):

- editing **duration** keeps the start and moves ``end = start + duration``;
- editing **start** (or the date) shifts *both* timestamps by the same delta;
- editing **end** moves only the end;
- ``duration_seconds`` is never derived from the timestamps; a large gap is
  flagged in the log (§4.2), never corrected.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from PySide6.QtCore import QObject, Signal

from timetracker.core.anchoring import anchor
from timetracker.core.clock import Clock
from timetracker.core.errors import NotFoundError
from timetracker.core.models import Entry, NewEntry, RecordMethod
from timetracker.core.timeutil import local_date_for, zone
from timetracker.data.entry_repo import EntryRepo
from timetracker.data.label_repo import LabelRepo
from timetracker.services.settings_service import SettingsService


class EntryService(QObject):
    entries_changed = Signal(object)  # list[str] of uuids

    def __init__(
        self,
        clock: Clock,
        entries: EntryRepo,
        clients: LabelRepo,
        types: LabelRepo,
        settings: SettingsService,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._clock = clock
        self._entries = entries
        self._clients = clients
        self._types = types
        self._settings = settings
        self._last_added: Entry | None = None
        self._deleted: list[list[Entry]] = []  # session undo stack, newest last (FR-506)

    # -- queries -------------------------------------------------------------

    def today(self) -> date:
        return local_date_for(self._clock.now_utc(), self._clock.tz_name())

    def today_total_seconds(self) -> int:
        return self._entries.total_seconds_for_date(self.today())

    def default_labels(self) -> tuple[int | None, int | None]:
        recent = self._entries.recent(1)
        return (recent[0].client_id, recent[0].type_id) if recent else (None, None)

    @property
    def last_added(self) -> Entry | None:
        return self._last_added

    # -- commands ------------------------------------------------------------

    def add_quick(
        self,
        duration_seconds: int,
        client_id: int | None,
        type_id: int | None,
        note: str | None,
        target_date: date | None = None,
    ) -> Entry:
        """Commit a composed entry (FR-310), anchored per §9.3.4. Never blocks on labels (P5)."""
        target = target_date or self.today()
        placed = anchor(
            duration_seconds,
            target,
            self._entries.list_for_date(target),
            self._settings.workday_start,
            self._clock,
        )
        entry = self._entries.insert(
            NewEntry(
                started_at_utc=placed.started_at_utc,
                ended_at_utc=placed.ended_at_utc,
                tz_name=placed.tz_name,
                duration_seconds=duration_seconds,
                record_method=RecordMethod.QUICKADD,
                client_id=client_id,
                type_id=type_id,
                note=(note or "").strip() or None,
            )
        )
        if client_id is not None:
            self._clients.touch_last_used(client_id)
        if type_id is not None:
            self._types.touch_last_used(type_id)
        self._last_added = entry
        self.entries_changed.emit([entry.uuid])
        return entry

    def add_manual(
        self,
        local_date: date,
        start: time,
        duration_seconds: int,
        client_id: int | None,
        type_id: int | None,
        note: str | None,
    ) -> Entry:
        """The log window's *Add entry…* form: explicit date and start, ``MANUAL`` method."""
        tz_name = self._clock.tz_name()
        started = datetime.combine(local_date, start, tzinfo=zone(tz_name)).astimezone(UTC)
        entry = self._entries.insert(
            NewEntry(
                started_at_utc=started,
                ended_at_utc=started + timedelta(seconds=duration_seconds),
                tz_name=tz_name,
                duration_seconds=duration_seconds,
                record_method=RecordMethod.MANUAL,
                client_id=client_id,
                type_id=type_id,
                note=(note or "").strip() or None,
            )
        )
        if client_id is not None:
            self._clients.touch_last_used(client_id)
        if type_id is not None:
            self._types.touch_last_used(type_id)
        self._last_added = entry
        self.entries_changed.emit([entry.uuid])
        return entry

    def update(self, entry_id: int, **changes: object) -> Entry:
        """Edit an entry per the module's edit policy; marks it ``is_edited`` (FR-505)."""
        current = self._entries.get(entry_id)
        resolved = dict(changes)
        if "duration_seconds" in resolved and "ended_at_utc" not in resolved:
            seconds = int(resolved["duration_seconds"])  # type: ignore[call-overload]
            start = resolved.get("started_at_utc", current.started_at_utc)
            assert isinstance(start, datetime)
            resolved["ended_at_utc"] = start + timedelta(seconds=seconds)
        elif "started_at_utc" in resolved and "ended_at_utc" not in resolved:
            new_start = resolved["started_at_utc"]
            assert isinstance(new_start, datetime)
            resolved["ended_at_utc"] = current.ended_at_utc + (new_start - current.started_at_utc)
        updated = self._entries.update(entry_id, **resolved)
        self.entries_changed.emit([updated.uuid])
        return updated

    def move_to_date(self, entry_id: int, new_date: date) -> Entry:
        """Shift an entry to another local day, keeping its time of day (the log's Date column)."""
        current = self._entries.get(entry_id)
        tz = zone(current.tz_name)
        local_start = current.started_at_utc.astimezone(tz)
        new_start = datetime.combine(new_date, local_start.timetz()).astimezone(UTC)
        return self.update(entry_id, started_at_utc=new_start)

    def delete(self, entry_ids: list[int]) -> list[Entry]:
        """Delete entries; the batch goes on the session undo stack (FR-506)."""
        removed = [self._entries.delete(i) for i in entry_ids]
        if removed:
            self._deleted.append(removed)
            if self._last_added is not None and any(e.id == self._last_added.id for e in removed):
                self._last_added = None
            self.entries_changed.emit([e.uuid for e in removed])
        return removed

    def undo_delete(self) -> list[Entry]:
        """Restore the most recently deleted batch. Empty list if nothing to undo."""
        if not self._deleted:
            return []
        batch = self._deleted.pop()
        restored = [self._entries.restore(e) for e in batch]
        self.entries_changed.emit([e.uuid for e in restored])
        return restored

    @property
    def can_undo_delete(self) -> bool:
        return bool(self._deleted)

    def undo_last(self) -> Entry | None:
        """Remove the most recent Add Time commit (FR-311); ``None`` if nothing to undo."""
        entry = self._last_added
        if entry is None:
            return None
        self._last_added = None
        try:
            removed = self._entries.delete(entry.id)
        except NotFoundError:
            return None
        self.entries_changed.emit([removed.uuid])
        return removed
