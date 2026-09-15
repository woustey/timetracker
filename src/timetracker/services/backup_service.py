"""Backup, restore and full data export (FR-802, FR-804; PRD-02 §10 "reveal data folder").

- **backup_now()**: a WAL checkpoint, then a timestamped copy next to the
  database (or into a chosen folder). The copy is a complete, standalone
  SQLite file.
- **restore(path)**: validate the candidate (a SQLite file that passes
  ``integrity_check`` and is not newer than this build's schema), take a
  pre-restore backup of the current file, copy the candidate over, and ask the
  application to relaunch — SQLite cannot have its file swapped under an open
  connection.
- **full_export(path)**: every entry and every label to ``.json`` (with
  settings) or ``.csv`` (entries with label names), for portability. Nothing
  is rounded; nothing leaves the machine.
"""

from __future__ import annotations

import csv
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from timetracker import __version__
from timetracker.core.clock import Clock
from timetracker.core.errors import TimeTrackerError
from timetracker.core.models import Dimension
from timetracker.core.timeutil import to_iso_utc, zone
from timetracker.data.db import connect
from timetracker.data.entry_repo import EntryRepo
from timetracker.data.label_repo import LabelRepo
from timetracker.data.schema import TARGET_VERSION
from timetracker.data.settings_repo import SettingsRepo

BACKUP_PREFIX = "timetracker-backup-"


class RestoreError(TimeTrackerError):
    """The candidate file cannot be restored; the message says why."""


@dataclass(frozen=True, slots=True)
class BackupInfo:
    path: Path
    entries: int
    schema_version: int


class BackupService(QObject):
    backup_created = Signal(object)  # Path
    restore_ready = Signal(object)  # Path of the pre-restore copy; the app should relaunch

    def __init__(
        self,
        clock: Clock,
        db_path: Path,
        conn: sqlite3.Connection,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._clock = clock
        self._db_path = db_path
        self._conn = conn

    @property
    def data_dir(self) -> Path:
        return self._db_path.parent

    # -- backup (FR-802) -------------------------------------------------------

    def backup_now(self, folder: Path | None = None) -> Path:
        target = (folder or self.data_dir) / f"{BACKUP_PREFIX}{self._stamp()}.sqlite3"
        self._snapshot(target)
        self.backup_created.emit(target)
        return target

    def _stamp(self) -> str:
        local = self._clock.now_utc().astimezone(zone(self._clock.tz_name()))
        return local.strftime("%Y%m%d-%H%M%S")

    def _snapshot(self, target: Path) -> None:
        """Copy a consistent snapshot with SQLite's online-backup API (WAL pages included)."""
        target.parent.mkdir(parents=True, exist_ok=True)
        dest = sqlite3.connect(target)
        try:
            self._conn.backup(dest)
        finally:
            dest.close()

    def list_backups(self, folder: Path | None = None) -> list[Path]:
        base = folder or self.data_dir
        return sorted(base.glob(f"{BACKUP_PREFIX}*.sqlite3"), reverse=True)

    # -- restore (FR-802) ------------------------------------------------------

    def inspect(self, candidate: Path) -> BackupInfo:
        """Validate a file for restore; raises :class:`RestoreError` with a plain reason."""
        if not candidate.is_file():
            raise RestoreError(f"{candidate} is not a file")
        try:
            conn = connect(candidate, read_only=True)
        except sqlite3.Error as exc:
            raise RestoreError(f"{candidate.name} is not a SQLite database: {exc}") from exc
        try:
            try:
                ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
                version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            except sqlite3.DatabaseError as exc:  # "file is not a database" surfaces here
                raise RestoreError(f"{candidate.name} is not a SQLite database: {exc}") from exc
            if ok != "ok":
                raise RestoreError(f"{candidate.name} fails SQLite's integrity check: {ok}")
            if version > TARGET_VERSION:
                raise RestoreError(
                    f"{candidate.name} was written by a newer version (schema {version}; "
                    f"this build understands up to {TARGET_VERSION})."
                )
            try:
                entries = int(conn.execute("SELECT COUNT(*) FROM entry").fetchone()[0])
            except sqlite3.Error as exc:
                raise RestoreError(f"{candidate.name} is not a Time Tracker database") from exc
        finally:
            conn.close()
        return BackupInfo(candidate, entries, version)

    def restore(self, candidate: Path) -> Path:
        """Replace the live database with *candidate*. Returns the pre-restore copy's path.

        The caller must relaunch the application afterwards (the open connection
        still points at the old pages).
        """
        self.inspect(candidate)
        pre = self.data_dir / f"timetracker-pre-restore-{self._stamp()}.sqlite3"
        self._snapshot(pre)
        self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self._conn.close()
        for suffix in ("-wal", "-shm"):
            self._db_path.with_name(self._db_path.name + suffix).unlink(missing_ok=True)
        shutil.copy2(candidate, self._db_path)
        self.restore_ready.emit(pre)
        return pre

    # -- full export (FR-804) ----------------------------------------------------

    def full_export(self, path: Path) -> Path:
        clients = LabelRepo(self._conn, Dimension.CLIENT, self._clock)
        types = LabelRepo(self._conn, Dimension.TYPE, self._clock)
        entries = EntryRepo(self._conn, self._clock)
        rows = entries.export_rows(newest_first=False)
        if path.suffix.lower() == ".json":
            payload = {
                "application": f"Time Tracker {__version__}",
                "schema_version": TARGET_VERSION,
                "exported_at": to_iso_utc(self._clock.now_utc()),
                "clients": [_label_dict(x) for x in clients.list_all(include_archived=True)],
                "types": [_label_dict(x) for x in types.list_all(include_archived=True)],
                "entries": [
                    {
                        "uuid": r.entry.uuid,
                        "started_at_utc": to_iso_utc(r.entry.started_at_utc),
                        "ended_at_utc": to_iso_utc(r.entry.ended_at_utc),
                        "tz_name": r.entry.tz_name,
                        "local_date": r.entry.local_date.isoformat(),
                        "duration_seconds": r.entry.duration_seconds,
                        "paused_seconds": r.entry.paused_seconds,
                        "client": r.client_name,
                        "type": r.type_name,
                        "note": r.entry.note,
                        "record_method": r.entry.record_method.value,
                        "is_edited": r.entry.is_edited,
                        "created_at": to_iso_utc(r.entry.created_at),
                        "modified_at": to_iso_utc(r.entry.modified_at),
                    }
                    for r in rows
                ],
                "settings": SettingsRepo(self._conn).all(),
            }
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            return path
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(
                [
                    "uuid",
                    "started_at_utc",
                    "ended_at_utc",
                    "tz_name",
                    "local_date",
                    "duration_seconds",
                    "paused_seconds",
                    "client",
                    "type",
                    "note",
                    "record_method",
                    "is_edited",
                    "created_at",
                    "modified_at",
                ]
            )
            for r in rows:
                e = r.entry
                w.writerow(
                    [
                        e.uuid,
                        to_iso_utc(e.started_at_utc),
                        to_iso_utc(e.ended_at_utc),
                        e.tz_name,
                        e.local_date.isoformat(),
                        e.duration_seconds,
                        e.paused_seconds,
                        r.client_name or "",
                        r.type_name or "",
                        e.note or "",
                        e.record_method.value,
                        int(e.is_edited),
                        to_iso_utc(e.created_at),
                        to_iso_utc(e.modified_at),
                    ]
                )
        return path


def _label_dict(label: object) -> dict[str, object]:
    from timetracker.core.models import Label

    assert isinstance(label, Label)
    return {
        "name": label.name,
        "is_archived": label.is_archived,
        "is_pinned": label.is_pinned,
        "colour": label.colour,
        "created_at": to_iso_utc(label.created_at),
        "last_used_at": None if label.last_used_at is None else to_iso_utc(label.last_used_at),
    }
