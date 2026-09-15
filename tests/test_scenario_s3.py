"""PRD-01 scenario S3, end to end (M5 acceptance).

Friday 16:30. The user reviews the week's log, spots a Tuesday afternoon with a
2-hour gap, adds a back-dated 90-minute Work entry for ASICS, then exports the
week to XLSX rounded to 6-minute increments.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QTime

from timetracker.core.clock import FakeClock
from timetracker.core.models import NewEntry, RecordMethod
from timetracker.core.rounding import RoundingScope
from timetracker.data.entry_repo import EntryRepo
from timetracker.data.label_repo import LabelRepo
from timetracker.services.entry_service import EntryService
from timetracker.services.export_service import ExportService
from timetracker.services.label_service import LabelService
from timetracker.services.settings_service import SettingsService
from timetracker.ui.dialogs.add_entry import AddEntryDialog
from timetracker.ui.log.model import Col
from timetracker.ui.log.presets import DatePreset
from timetracker.ui.log.window import LogWindow

BRU = "Europe/Brussels"


def test_scenario_s3(  # type: ignore[no-untyped-def]
    qtbot,
    tmp_path: Path,
    clock: FakeClock,
    entries: EntryRepo,
    entry_service: EntryService,
    labels: LabelService,
    settings_service: SettingsService,
    clients: LabelRepo,
    types: LabelRepo,
    monkeypatch,
) -> None:
    clock.set_now(datetime(2026, 9, 11, 14, 30, tzinfo=UTC))  # Friday 16:30 Brussels
    asics = clients.create("ASICS")
    nike = clients.create("Nike")
    work = types.create("Work")
    meeting = types.create("Meeting/Call")
    # The week so far: Tuesday has a call 10:00–10:44 and then nothing until 14:00.
    tue = datetime(2026, 9, 8, 8, 0, tzinfo=UTC)  # 10:00 Brussels
    for start, minutes, client_id, type_id, method in (
        (tue, 44, asics.id, meeting.id, RecordMethod.STOPWATCH),
        (tue + timedelta(hours=4), 62, nike.id, work.id, RecordMethod.STOPWATCH),
        (tue + timedelta(days=1), 8, nike.id, work.id, RecordMethod.QUICKADD),
    ):
        entries.insert(
            NewEntry(
                start,
                start + timedelta(minutes=minutes),
                BRU,
                minutes * 60,
                method,
                client_id,
                type_id,
            )
        )

    # 1. Review the week's log.
    window = LogWindow(
        clock, entries, entry_service, labels, settings_service, ExportService(clock, None)
    )
    qtbot.addWidget(window)
    window.show()
    assert window.current_preset() is DatePreset.THIS_WEEK
    m = window.model
    assert m.rowCount() == 3
    tuesday_rows = [
        r for r in range(m.rowCount()) if m.index(r, Col.DATE).data() == "Tue 08 Sep 2026"
    ]
    ends = sorted(m.index(r, Col.END).data() for r in tuesday_rows)
    starts = sorted(m.index(r, Col.START).data() for r in tuesday_rows)
    assert ends[0] == "10:44" and starts[-1] == "14:00"  # the 2-hour gap is visible

    # 2. Add the back-dated 90-minute ASICS / Work entry into the gap.
    def fill_form(dialog: AddEntryDialog) -> int:
        dialog.date.setDate(QDate(2026, 9, 8))
        dialog.start.setTime(QTime(11, 0))
        dialog.duration.setText("1h30")
        dialog.client.setCurrentIndex(dialog.client.findData(asics.id))
        dialog.type.setCurrentIndex(dialog.type.findData(work.id))
        dialog._validate()  # noqa: SLF001
        return int(dialog.result())

    monkeypatch.setattr(AddEntryDialog, "exec", fill_form)
    window.add_entry()
    assert m.rowCount() == 4
    added = entry_service.last_added
    assert added is not None
    assert added.local_date == date(2026, 9, 8)
    assert added.duration_seconds == 5400
    assert added.client_id == asics.id and added.type_id == work.id
    assert added.record_method is RecordMethod.MANUAL
    assert "Total 3:24" in window.totals.text()  # 44 + 62 + 8 + 90 min

    # 3. Export the week to XLSX rounded to 6 minutes.
    from openpyxl import load_workbook

    options = window.build_export_options("xlsx", 6, RoundingScope.PER_GROUP)
    assert options.flt.date_from == date(2026, 9, 7) and options.flt.date_to == date(2026, 9, 13)
    out = tmp_path / window.default_export_name("xlsx")
    assert out.name == "timetracker_2026-09-07_2026-09-13.xlsx"
    window._exporter.export_sync(entries, options, out)  # noqa: SLF001

    wb = load_workbook(out)
    ws = wb["Time"]
    rows = [[c.value for c in row] for row in ws.iter_rows(min_row=2, max_row=5)]
    assert [r[0] for r in rows] == ["2026-09-08", "2026-09-08", "2026-09-08", "2026-09-09"]
    by_note = {(r[0], r[1]): r for r in rows}
    call = by_note[("2026-09-08", "10:00")]
    assert call[5:8] == ["ASICS", "Meeting/Call", "Start-Stop"]
    assert call[3] == 0.8  # 44 → 48 min
    gap = by_note[("2026-09-08", "11:00")]
    assert gap[2] == "12:30" and gap[3] == 1.5 and gap[5:8] == ["ASICS", "Work", "Manual"]
    nike_work = by_note[("2026-09-08", "14:00")]
    assert nike_work[3] == round(66 / 60, 4)  # 62 → 66 min
    info = {row[0].value: row[1].value for row in wb["Export info"].iter_rows()}
    assert info["Rounding"] == "6 minutes, rounded up per day × client × type"
    assert info["Billed total (h:mm)"] == "3:36"  # 48 + 90 + 66 + 12
    assert info["Raw total (h:mm)"] == "3:24"

    # 4. FR-605: nothing in the database changed because of the rounding.
    assert entries.get(added.id).duration_seconds == 5400
    assert not any(e.is_edited for e in entries.query())
    window.close()
