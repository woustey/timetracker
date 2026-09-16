"""Domain types (PRD-01 §7, PRD-02 §4.1).

All dataclasses are frozen; repositories return new instances rather than
mutating. ``Entry.duration_seconds`` is the measured fact; the timestamps are
chronology anchors only and nothing here derives one from the other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import Enum

from timetracker.core.errors import ValidationError

NOTE_MAX_CHARS = 500
_WS = re.compile(r"\s+")


class RecordMethod(Enum):
    STOPWATCH = "STOPWATCH"  # the timer (FR-204)
    QUICKADD = "QUICKADD"  # the Add Time matrix (FR-314)
    MANUAL = "MANUAL"  # the log window's Add entry… form (v3, owner's request)

    @property
    def display(self) -> str:
        return {
            RecordMethod.STOPWATCH: "Start-Stop",
            RecordMethod.QUICKADD: "Add Time",
            RecordMethod.MANUAL: "Manual",
        }[self]


class Dimension(Enum):
    """The two label dimensions of v1 (NG8). Value is the table name."""

    CLIENT = "client"
    TYPE = "work_type"


def normalise_label_name(name: str) -> str:
    """Casefold and collapse whitespace so ``"nike"``, ``"Nike "`` and ``"Nike"`` match (FR-402)."""
    return _WS.sub(" ", name.strip()).casefold()


def clean_label_name(name: str) -> str:
    """Display form: whitespace collapsed, original casing kept. Raises on empty."""
    cleaned = _WS.sub(" ", name.strip())
    if not cleaned:
        raise ValidationError("label name is empty")
    return cleaned


@dataclass(frozen=True, slots=True)
class Label:
    id: int
    dimension: Dimension
    name: str
    name_norm: str
    colour: str | None
    is_archived: bool
    is_pinned: bool
    created_at: datetime
    last_used_at: datetime | None


@dataclass(frozen=True, slots=True)
class Entry:
    id: int
    uuid: str
    started_at_utc: datetime
    ended_at_utc: datetime
    tz_name: str
    local_date: date
    duration_seconds: int
    paused_seconds: int
    client_id: int | None
    type_id: int | None
    note: str | None
    record_method: RecordMethod
    is_edited: bool
    created_at: datetime
    modified_at: datetime

    def with_changes(self, **changes: object) -> Entry:
        return replace(self, **changes)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class NewEntry:
    """What a caller supplies to create an entry; the repo assigns the rest."""

    started_at_utc: datetime
    ended_at_utc: datetime
    tz_name: str
    duration_seconds: int
    record_method: RecordMethod
    client_id: int | None = None
    type_id: int | None = None
    note: str | None = None
    paused_seconds: int = 0
    uuid: str | None = None

    def validate(self) -> None:
        if self.duration_seconds < 0:
            raise ValidationError("duration_seconds must be >= 0")
        if self.paused_seconds < 0:
            raise ValidationError("paused_seconds must be >= 0")
        if self.ended_at_utc < self.started_at_utc:
            raise ValidationError("ended_at_utc is before started_at_utc")
        if self.note is not None and len(self.note) > NOTE_MAX_CHARS:
            raise ValidationError(f"note exceeds {NOTE_MAX_CHARS} characters")


@dataclass(frozen=True, slots=True)
class RunningTimer:
    """The singleton persisted while a stopwatch runs (PRD-02 §4.1 ``running_timer``).

    ``accrued_seconds`` is advanced from the monotonic clock in-process; the
    heartbeat pair is the last durable copy, used by crash recovery (FR-207).
    ``paused_seconds`` totals the *completed* pauses (FR-212); ``paused_since_utc``
    marks an open one.
    """

    started_at_utc: datetime
    tz_name: str
    accrued_seconds: int
    paused_since_utc: datetime | None
    paused_seconds: int
    client_id: int | None
    type_id: int | None
    note: str | None
    heartbeat_at_utc: datetime
    heartbeat_accrued_sec: int

    @property
    def is_paused(self) -> bool:
        return self.paused_since_utc is not None
