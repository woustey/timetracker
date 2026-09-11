"""Entry creation for Add Time, and undo of the last commit (FR-311, FR-314).

The stopwatch path lives in ``TimerService`` (the only creator of ``STOPWATCH``
entries); this service is the only creator of ``QUICKADD`` entries. Edit,
delete, split and merge (FR-505–FR-507) arrive with the log window in M5.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QObject, Signal

from timetracker.core.anchoring import anchor
from timetracker.core.clock import Clock
from timetracker.core.errors import NotFoundError
from timetracker.core.models import Entry, NewEntry, RecordMethod
from timetracker.core.timeutil import local_date_for
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
