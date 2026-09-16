"""CSV import with column mapping (FR-805, v1.1) — the pure part.

Reads a delimited text file, lets the caller map its columns onto the entry
fields, and turns every row into either a :class:`ParsedRow` (what will be
inserted) or an error message. No I/O beyond reading the file, no Qt, no
database: the service resolves label names and writes; the dialog shows the
preview this produces.

Field rules:

- **date** is required: ISO ``2026-09-16``, or ``16/09/2026`` / ``16.09.2026``
  / ``16-09-2026`` read per the chosen :class:`DateOrder` (DMY or MDY —
  ``09/16/2026`` cannot be told from ``16/09/2026`` in general, so the user
  picks; *auto* uses ISO first and otherwise DMY unless a day > 12 proves MDY).
- **duration** comes from the duration column (``1:30``, ``1h15``, ``90``
  minutes, ``1.5`` decimal hours) or, failing that, from ``end − start``. This
  is the one place a duration is derived from timestamps: it is the *source
  tool's* data, and the result is stored as the measured fact from then on.
- **start** is optional; a row without one is placed at the workday start,
  consecutive rows on the same day back to back (like Add Time anchoring).
- **client** / **type** / **note** are optional text.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from enum import Enum
from pathlib import Path

from timetracker.core.duration import parse_duration
from timetracker.core.timeutil import zone

FIELDS = ("date", "start", "end", "duration", "client", "type", "note")
MAX_FILE_BYTES = 50 * 1024 * 1024

# Header words that suggest a field (casefolded, punctuation stripped).
_HINTS: dict[str, tuple[str, ...]] = {
    "date": ("date", "day", "datum"),
    "start": ("start", "begin", "from", "starttime", "started"),
    "end": ("end", "stop", "to", "endtime", "ended", "finish"),
    "duration": ("duration", "hours", "time", "minutes", "total", "dur", "length", "h:mm"),
    "client": ("client", "customer", "project", "account", "klant"),
    "type": ("type", "category", "activity", "task", "kind", "work type", "categorie"),
    "note": ("note", "notes", "description", "comment", "memo", "remark", "opmerking"),
}

_DATE_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?$")
_DATE_SEP = re.compile(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})$")
_TIME = re.compile(r"^(\d{1,2})(?::(\d{2}))?(?::(\d{2}))?\s*([ap]\.?m\.?)?$", re.IGNORECASE)
_DECIMAL_HOURS = re.compile(r"^\d+[.,]\d+$")


class DateOrder(Enum):
    AUTO = "auto"
    DMY = "dmy"
    MDY = "mdy"


@dataclass(frozen=True, slots=True)
class CsvSample:
    delimiter: str
    header: list[str]
    rows: list[list[str]]  # every data row (the dialog previews a slice)
    total_rows: int  # data rows in the file
    has_header: bool


@dataclass(frozen=True, slots=True)
class ColumnMapping:
    """Field → column index (``None`` = not mapped)."""

    date: int | None = None
    start: int | None = None
    end: int | None = None
    duration: int | None = None
    client: int | None = None
    type: int | None = None
    note: int | None = None

    def index(self, field_name: str) -> int | None:
        return getattr(self, field_name)  # type: ignore[no-any-return]

    def problems(self) -> list[str]:
        out: list[str] = []
        if self.date is None:
            out.append("a Date column is required")
        if self.duration is None and (self.start is None or self.end is None):
            out.append("map a Duration column, or both Start and End")
        used = [
            i
            for i in (
                self.date,
                self.start,
                self.end,
                self.duration,
                self.client,
                self.type,
                self.note,
            )
            if i is not None
        ]
        if len(used) != len(set(used)):
            out.append("one column is mapped to two fields")
        return out


@dataclass(frozen=True, slots=True)
class ParsedRow:
    line: int  # 1-based line in the file (header counted)
    started_at_utc: datetime
    ended_at_utc: datetime
    duration_seconds: int
    client: str | None
    type: str | None
    note: str | None
    placed: bool = False  # start was invented (no start column)


@dataclass(frozen=True, slots=True)
class RowError:
    line: int
    message: str


@dataclass(frozen=True, slots=True)
class ParseResult:
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)


# -- reading -------------------------------------------------------------------


def read_sample(
    path: Path, delimiter: str | None = None, *, has_header: bool | None = None
) -> CsvSample:
    """Sniff delimiter and header, read everything (bounded by MAX_FILE_BYTES)."""
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(f"file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB")
    raw = path.read_bytes()
    text = _decode(raw)
    return parse_sample(text, delimiter, has_header=has_header)


def parse_sample(
    text: str, delimiter: str | None = None, *, has_header: bool | None = None
) -> CsvSample:
    head = text[:8192]
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(head, delimiters=";,\t|").delimiter
        except csv.Error:
            delimiter = ";" if head.count(";") >= head.count(",") else ","
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    all_rows = [r for r in reader if any(c.strip() for c in r)]
    if not all_rows:
        return CsvSample(delimiter, [], [], 0, False)
    if has_header is None:
        has_header = _looks_like_header(all_rows[0])
    header = (
        [c.strip() for c in all_rows[0]]
        if has_header
        else [f"Column {i + 1}" for i in range(len(all_rows[0]))]
    )
    data = all_rows[1:] if has_header else all_rows
    return CsvSample(delimiter, header, data, len(data), has_header)


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("cp1252", errors="replace")


def _looks_like_header(row: list[str]) -> bool:
    """A header has no cell that parses as a date or a duration and at least one word."""
    for cell in row:
        c = cell.strip()
        if not c:
            continue
        if _parse_date(c, DateOrder.AUTO) is not None or _DATE_ISO.match(c):
            return False
    return any(re.search(r"[A-Za-z]", c) for c in row)


def guess_mapping(header: list[str]) -> ColumnMapping:
    taken: set[int] = set()
    found: dict[str, int | None] = {f: None for f in FIELDS}
    norm = [re.sub(r"[^a-z0-9: ]", " ", h.casefold()).strip() for h in header]
    # Exact-ish matches first, then substring matches, so "Start date" is not "date".
    for exact in (True, False):
        for field_name in FIELDS:
            if found[field_name] is not None:
                continue
            for i, h in enumerate(norm):
                if i in taken or not h:
                    continue
                hints = _HINTS[field_name]
                hit = h in hints if exact else any(w in h for w in hints)
                if hit:
                    found[field_name] = i
                    taken.add(i)
                    break
    return ColumnMapping(**found)


# -- parsing -------------------------------------------------------------------


def parse_rows(
    sample_rows: list[list[str]],
    mapping: ColumnMapping,
    *,
    tz_name: str,
    date_order: DateOrder = DateOrder.AUTO,
    workday_start: time = time(9, 0),
    first_line: int = 2,
) -> ParseResult:
    """Turn data rows into inserts or errors. ``first_line`` is the file line of row 0."""
    problems = mapping.problems()
    if problems:
        return ParseResult(errors=[RowError(0, "; ".join(problems))])
    tz = zone(tz_name)
    order = date_order
    if order is DateOrder.AUTO:
        order = _infer_order(sample_rows, mapping.date)
    result_rows: list[ParsedRow] = []
    errors: list[RowError] = []
    last_end_by_day: dict[date, datetime] = {}

    for offset, row in enumerate(sample_rows):
        line = first_line + offset
        try:
            parsed = _parse_row(row, mapping, tz, order, workday_start, last_end_by_day, line)
        except ValueError as exc:
            errors.append(RowError(line, str(exc)))
            continue
        result_rows.append(parsed)
    return ParseResult(result_rows, errors)


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def _parse_row(
    row: list[str],
    m: ColumnMapping,
    tz: object,
    order: DateOrder,
    workday_start: time,
    last_end_by_day: dict[date, datetime],
    line: int,
) -> ParsedRow:
    day = _parse_date(_cell(row, m.date), order)
    if day is None:
        raise ValueError(f"cannot read the date {_cell(row, m.date)!r}")
    start_t = _parse_time(_cell(row, m.start)) if m.start is not None else None
    if m.start is not None and _cell(row, m.start) and start_t is None:
        raise ValueError(f"cannot read the start time {_cell(row, m.start)!r}")
    end_t = _parse_time(_cell(row, m.end)) if m.end is not None else None
    if m.end is not None and _cell(row, m.end) and end_t is None:
        raise ValueError(f"cannot read the end time {_cell(row, m.end)!r}")

    duration: int | None = None
    if m.duration is not None and _cell(row, m.duration):
        duration = _parse_duration_cell(_cell(row, m.duration))
        if duration is None:
            raise ValueError(f"cannot read the duration {_cell(row, m.duration)!r}")
    if duration is None:
        if start_t is None or end_t is None:
            raise ValueError("no duration, and no start and end to derive it from")
        s = datetime.combine(day, start_t, tzinfo=tz).astimezone(UTC)  # type: ignore[arg-type]
        e = datetime.combine(day, end_t, tzinfo=tz).astimezone(UTC)  # type: ignore[arg-type]
        if e < s:
            e += timedelta(days=1)  # crossed midnight
        duration = int((e - s).total_seconds())

    placed = False
    if start_t is not None:
        started = datetime.combine(day, start_t, tzinfo=tz).astimezone(UTC)  # type: ignore[arg-type]
    else:
        day_start = datetime.combine(day, workday_start, tzinfo=tz).astimezone(UTC)  # type: ignore[arg-type]
        started = max(day_start, last_end_by_day.get(day, day_start))
        placed = True
    ended = started + timedelta(seconds=duration)
    last_end_by_day[day] = max(last_end_by_day.get(day, ended), ended)

    return ParsedRow(
        line=line,
        started_at_utc=started,
        ended_at_utc=ended,
        duration_seconds=duration,
        client=_cell(row, m.client) or None,
        type=_cell(row, m.type) or None,
        note=(_cell(row, m.note) or None),
        placed=placed,
    )


def _infer_order(rows: list[list[str]], date_index: int | None) -> DateOrder:
    """DMY unless some day-first reading is impossible (a 'day' > 12) → MDY."""
    for row in rows:
        m = _DATE_SEP.match(_cell(row, date_index))
        if m and int(m.group(1)) > 12:
            return DateOrder.DMY
        if m and int(m.group(2)) > 12:
            return DateOrder.MDY
    return DateOrder.DMY


def _parse_date(text: str, order: DateOrder) -> date | None:
    m = _DATE_ISO.match(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = _DATE_SEP.match(text)
    if not m:
        return None
    a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    if order is DateOrder.MDY:
        month, day = a, b
    elif order is DateOrder.DMY:
        day, month = a, b
    else:  # AUTO, per cell: prefer DMY, fall back to MDY when DMY is impossible
        day, month = a, b
        if day > 31 or month > 12:
            day, month = b, a
    try:
        return date(y, month, day)
    except ValueError:
        return None


def _parse_time(text: str) -> time | None:
    if not text:
        return None
    m = _TIME.match(text)
    if not m:
        return None
    hour, minute, second = int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0)
    ampm = (m.group(4) or "").replace(".", "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59 or second > 59:
        return None
    return time(hour, minute, second)


def _parse_duration_cell(text: str) -> int | None:
    if _DECIMAL_HOURS.match(text):
        return int(float(text.replace(",", ".")) * 3600 + 1e-9)  # decimal hours, e.g. 1.5
    return parse_duration(text)
