"""core/csv_import (FR-805): sniffing, header guessing, mapping, date/time/duration parsing."""

from __future__ import annotations

from datetime import UTC, datetime, time
from pathlib import Path

from timetracker.core.csv_import import (
    ColumnMapping,
    DateOrder,
    guess_mapping,
    parse_rows,
    parse_sample,
    read_sample,
)

TZ = "Europe/Brussels"


def test_sniff_delimiter_header_and_row_count(tmp_path: Path) -> None:
    text = (
        "Date;Start;End;Client;Note\n2026-09-14;09:00;10:30;Nike;call\n2026-09-14;11:00;11:15;;\n"
    )
    sample = parse_sample(text)
    assert sample.delimiter == ";"
    assert sample.has_header
    assert sample.header == ["Date", "Start", "End", "Client", "Note"]
    assert sample.total_rows == 2 and len(sample.rows) == 2
    path = tmp_path / "x.csv"
    path.write_bytes(b"\xef\xbb\xbf" + text.replace(";", ",").encode())  # BOM + comma
    again = read_sample(path)
    assert again.delimiter == "," and again.header[0] == "Date"
    # No header: generic names, every row is data.
    no_header = parse_sample("2026-09-14,09:00,10:30\n2026-09-15,09:00,09:30\n")
    assert not no_header.has_header
    assert no_header.header == ["Column 1", "Column 2", "Column 3"]
    assert no_header.total_rows == 2
    forced = parse_sample(text, has_header=False)
    assert forced.total_rows == 3


def test_guess_mapping_from_header_words() -> None:
    m = guess_mapping(["Datum", "Begin", "Einde", "Duration (h:mm)", "Klant", "Categorie", "Notes"])
    assert (m.date, m.start, m.duration, m.client, m.type, m.note) == (0, 1, 3, 4, 5, 6)
    m = guess_mapping(["Start date", "Project", "Description", "Hours"])
    assert (m.date, m.client, m.note, m.duration) == (0, 1, 2, 3)
    assert m.start is None
    assert ColumnMapping().problems() == [
        "a Date column is required",
        "map a Duration column, or both Start and End",
    ]
    assert ColumnMapping(date=0, duration=0).problems() == ["one column is mapped to two fields"]


def test_parse_rows_duration_from_column_or_span_and_placement() -> None:
    rows = [
        ["16/09/2026", "09:00", "10:30", "", "Nike", "Work", "a"],  # span → 1:30
        ["16/09/2026", "", "", "1:15", "Nike", "", ""],  # placed at 10:30 (after the first)
        ["16/09/2026", "", "", "1.5", "", "", ""],  # decimal hours, placed at 11:45
        ["17/09/2026", "", "", "90", "", "", ""],  # minutes, placed at workday start
        ["16.09.2026", "2:30 PM", "3:00 pm", "", "", "", ""],  # 12 h clock, dotted date
        ["31/12/26", "23:30", "00:15", "", "", "", ""],  # crosses midnight → 45 min
    ]
    m = ColumnMapping(date=0, start=1, end=2, duration=3, client=4, type=5, note=6)
    result = parse_rows(rows, m, tz_name=TZ, workday_start=time(8, 0))
    assert result.errors == []
    got = [
        (r.started_at_utc.astimezone(UTC).strftime("%d %H:%M"), r.duration_seconds, r.placed)
        for r in result.rows
    ]
    assert got == [
        ("16 07:00", 5400, False),  # 09:00 CEST = 07:00 UTC
        ("16 08:30", 4500, True),
        ("16 09:45", 5400, True),
        ("17 06:00", 5400, True),
        ("16 12:30", 1800, False),
        ("31 22:30", 2700, False),
    ]
    assert (
        result.rows[0].client == "Nike"
        and result.rows[0].type == "Work"
        and result.rows[0].note == "a"
    )
    assert result.rows[1].type is None
    assert result.rows[0].line == 2  # header counted


def test_parse_rows_reports_errors_per_line_and_keeps_the_rest() -> None:
    rows = [
        ["2026-09-16", "09:00", "10:00", ""],
        ["yesterday", "09:00", "10:00", ""],
        ["2026-09-16", "9am", "", ""],
        ["2026-09-16", "", "", "one hour"],
        ["2026-02-30", "", "", "1:00"],
    ]
    m = ColumnMapping(date=0, start=1, end=2, duration=3)
    result = parse_rows(rows, m, tz_name=TZ, first_line=1)
    assert [r.line for r in result.rows] == [1]
    assert [(e.line, e.message) for e in result.errors] == [
        (2, "cannot read the date 'yesterday'"),
        (3, "no duration, and no start and end to derive it from"),
        (4, "cannot read the duration 'one hour'"),
        (5, "cannot read the date '2026-02-30'"),
    ]
    assert parse_rows(rows, ColumnMapping(), tz_name=TZ).errors[0].line == 0


def test_date_order_auto_dmy_and_mdy() -> None:
    rows = [["03/04/2026", "1:00"], ["13/04/2026", "1:00"]]
    m = ColumnMapping(date=0, duration=1)
    auto = parse_rows(rows, m, tz_name=TZ)
    assert [r.started_at_utc.date().isoformat() for r in auto.rows] == ["2026-04-03", "2026-04-13"]
    mdy_rows = [["03/04/2026", "1:00"], ["04/13/2026", "1:00"]]
    auto = parse_rows(mdy_rows, m, tz_name=TZ)
    assert [r.started_at_utc.date().isoformat() for r in auto.rows] == ["2026-03-04", "2026-04-13"]
    forced = parse_rows([["03/04/2026", "1:00"]], m, tz_name=TZ, date_order=DateOrder.MDY)
    assert forced.rows[0].started_at_utc.date().isoformat() == "2026-03-04"
    iso_with_time = parse_rows([["2026-09-16 09:00:00", "0:30"]], m, tz_name=TZ)
    assert iso_with_time.rows[0].started_at_utc == datetime(2026, 9, 16, 7, 0, tzinfo=UTC)
