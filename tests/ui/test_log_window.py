"""Log window under pytest-qt (FR-501–FR-506, FR-508)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest
from PySide6.QtCore import QDate, Qt

from timetracker.core.clock import FakeClock
from timetracker.core.models import NewEntry, RecordMethod
from timetracker.data.entry_repo import EntryRepo
from timetracker.data.label_repo import LabelRepo
from timetracker.services.entry_service import EntryService
from timetracker.services.export_service import ExportService
from timetracker.services.label_service import LabelService
from timetracker.services.settings_service import SettingsService
from timetracker.ui.log.model import GLYPH_DISCREPANCY, GLYPH_EDITED, GLYPH_OVERLAP, Col
from timetracker.ui.log.presets import DatePreset, preset_range
from timetracker.ui.log.window import LogWindow

BRU = "Europe/Brussels"


def _add(entries: EntryRepo, start: datetime, minutes: int, **kw: object) -> None:
    entries.insert(
        NewEntry(
            started_at_utc=start,
            ended_at_utc=start + timedelta(minutes=minutes),
            tz_name=BRU,
            duration_seconds=minutes * 60,
            record_method=RecordMethod.STOPWATCH,
            **kw,  # type: ignore[arg-type]
        )
    )


@pytest.fixture
def window(  # type: ignore[no-untyped-def]
    qtbot,
    clock: FakeClock,
    entries: EntryRepo,
    entry_service: EntryService,
    labels: LabelService,
    settings_service: SettingsService,
    clients: LabelRepo,
    types: LabelRepo,
) -> LogWindow:
    # Clock: Friday 11 Sep 2026 12:00 Brussels. Seed Tue–Thu of this week plus last week.
    nike = clients.create("Nike")
    asics = clients.create("ASICS")
    work = types.create("Work")
    email = types.create("Email/Chat")
    tue = datetime(2026, 9, 8, 7, 0, tzinfo=UTC)
    _add(entries, tue, 30, client_id=nike.id, type_id=email.id, note="tuesday mail")
    _add(entries, tue + timedelta(hours=2), 60, client_id=asics.id, type_id=work.id, note="draft")
    _add(entries, tue + timedelta(days=2), 45, client_id=nike.id, type_id=work.id)
    _add(entries, tue - timedelta(days=7), 90, client_id=asics.id, type_id=work.id, note="old")
    exporter = ExportService(clock, None)
    w = LogWindow(clock, entries, entry_service, labels, settings_service, exporter)
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    return w


def test_presets_monday_first() -> None:
    fri = date(2026, 9, 11)
    assert preset_range(DatePreset.TODAY, fri) == (fri, fri)
    assert preset_range(DatePreset.THIS_WEEK, fri) == (date(2026, 9, 7), date(2026, 9, 13))
    assert preset_range(DatePreset.LAST_WEEK, fri) == (date(2026, 8, 31), date(2026, 9, 6))
    assert preset_range(DatePreset.THIS_MONTH, fri) == (date(2026, 9, 1), date(2026, 9, 30))
    assert preset_range(DatePreset.LAST_MONTH, fri) == (date(2026, 8, 1), date(2026, 8, 31))
    assert preset_range(DatePreset.LAST_MONTH, date(2026, 3, 31)) == (
        date(2026, 2, 1),
        date(2026, 2, 28),
    )
    assert preset_range(DatePreset.ALL, fri) == (None, None)


def test_default_view_is_this_week_newest_first(window: LogWindow) -> None:
    assert window.current_preset() is DatePreset.THIS_WEEK
    m = window.model
    assert m.rowCount() == 3
    assert m.index(0, Col.DATE).data() == "Thu 10 Sep 2026"
    assert m.index(2, Col.START).data() == "09:00"
    assert m.index(2, Col.DURATION).data() == "0:30"
    assert m.index(2, Col.CLIENT).data() == "Nike"
    assert m.index(2, Col.METHOD).data() == "Start-Stop"
    assert "3 entries" in window.totals.text()
    assert "Total 2:15" in window.totals.text()
    assert "Clients: Nike 1:15, ASICS 1:00" in window.totals.text()
    assert "Types: Work 1:45, Email/Chat 0:30" in window.totals.text()


def test_filters_hit_sql(window: LogWindow, clients: LabelRepo) -> None:
    window.set_preset(DatePreset.ALL)
    assert window.model.rowCount() == 4
    window.set_preset(DatePreset.LAST_WEEK)
    assert window.model.rowCount() == 1
    assert window.model.index(0, Col.NOTE).data() == "old"
    window.set_preset(DatePreset.ALL)
    nike = clients.find_by_name("nike")
    assert nike is not None
    window.client.setCurrentIndex(window.client.findData(nike.id))
    assert window.model.rowCount() == 2
    window.client.setCurrentIndex(0)
    window.method.setCurrentIndex(window.method.findData("QUICKADD"))
    assert window.model.rowCount() == 0
    window.method.setCurrentIndex(0)
    window.search.setText("tues")
    window._search_timer.timeout.emit()  # noqa: SLF001 - skip the debounce
    assert window.model.rowCount() == 1
    assert "1 entry" in window.totals.text()


def test_range_fields_always_visible_and_editing_makes_it_custom(window: LogWindow) -> None:
    # A preset fills the two date fields in.
    assert window.date_from.isVisible() and window.date_to.isVisible()
    assert window.date_from.date() == QDate(2026, 9, 7)
    assert window.date_to.date() == QDate(2026, 9, 13)
    # Editing a date switches to "Custom range" and applies it.
    window.date_from.setDate(QDate(2026, 9, 1))
    assert window.current_preset() is DatePreset.CUSTOM
    window.date_to.setDate(QDate(2026, 9, 8))
    assert window.model.rowCount() == 3  # last week's + the two Tuesday rows
    assert window.model.filter.date_from == date(2026, 9, 1)
    # "to" can never precede "from".
    window.date_to.setDate(QDate(2026, 8, 1))
    assert window.date_to.date() == window.date_from.date()
    # Back to a preset: fields follow it again.
    window.set_preset(DatePreset.LAST_WEEK)
    assert window.date_from.date() == QDate(2026, 8, 31)
    # "All time" shows the span of the data.
    window.set_preset(DatePreset.ALL)
    assert window.model.filter.date_from is None
    assert window.date_from.date() == QDate(2026, 9, 1)  # earliest seeded row
    assert window.date_to.date() == QDate(2026, 9, 10)


def test_sort_by_header(window: LogWindow) -> None:
    window.set_preset(DatePreset.ALL)
    window._on_header_clicked(Col.DURATION)  # noqa: SLF001
    durations = [window.model.index(r, Col.DURATION).data() for r in range(4)]
    assert durations == ["1:30", "1:00", "0:45", "0:30"]
    window._on_header_clicked(Col.DURATION)  # noqa: SLF001 - toggles
    assert window.model.index(0, Col.DURATION).data() == "0:30"
    window._on_header_clicked(Col.CLIENT)  # noqa: SLF001
    assert window.model.index(0, Col.CLIENT).data() == "ASICS"


def test_inline_edit_marks_row_and_updates_totals(window: LogWindow, entries: EntryRepo) -> None:
    m = window.model
    idx = m.index(2, Col.DURATION)  # the 0:30 Tuesday mail
    entry_id = m.entry_at(2).id
    assert m.setData(idx, 45 * 60, Qt.ItemDataRole.EditRole)
    assert m.index(2, Col.DURATION).data() == "0:45"
    assert m.index(2, Col.END).data() == "09:45"  # end followed the duration
    assert GLYPH_EDITED in m.index(2, Col.FLAGS).data()
    assert "edited" in m.index(2, Col.FLAGS).data(Qt.ItemDataRole.AccessibleDescriptionRole)
    assert entries.get(entry_id).is_edited
    assert "Total 2:30" in window.totals.text()

    # Start edit shifts both anchors; end edit only the end → discrepancy glyph.
    assert m.setData(m.index(2, Col.START), time(8, 0), Qt.ItemDataRole.EditRole)
    assert m.index(2, Col.START).data() == "08:00"
    assert m.index(2, Col.END).data() == "08:45"
    assert m.setData(m.index(2, Col.END), time(10, 0), Qt.ItemDataRole.EditRole)
    assert GLYPH_DISCREPANCY in m.index(2, Col.FLAGS).data()
    assert m.index(2, Col.DURATION).data() == "0:45"  # duration untouched by the anchor edit

    # Label and note edits.
    assert m.setData(m.index(2, Col.CLIENT), None, Qt.ItemDataRole.EditRole)
    assert m.index(2, Col.CLIENT).data() == ""
    assert m.setData(m.index(2, Col.NOTE), "  renamed ", Qt.ItemDataRole.EditRole)
    assert m.index(2, Col.NOTE).data() == "renamed"
    # Same value again → no-op, method column is not editable.
    assert not m.setData(m.index(2, Col.NOTE), "renamed", Qt.ItemDataRole.EditRole)
    assert not (m.flags(m.index(2, Col.METHOD)) & Qt.ItemFlag.ItemIsEditable)


def test_date_edit_moves_entry_across_days(window: LogWindow) -> None:
    m = window.model
    window.set_preset(DatePreset.ALL)
    row = next(r for r in range(m.rowCount()) if m.index(r, Col.NOTE).data() == "old")
    assert m.setData(m.index(row, Col.DATE), date(2026, 9, 9), Qt.ItemDataRole.EditRole)
    window.set_preset(DatePreset.THIS_WEEK)
    notes = [m.index(r, Col.NOTE).data() for r in range(m.rowCount())]
    assert "old" in notes
    moved = next(r for r in range(m.rowCount()) if m.index(r, Col.NOTE).data() == "old")
    assert m.index(moved, Col.DATE).data() == "Wed 09 Sep 2026"
    assert m.index(moved, Col.START).data() == "09:00"  # time of day kept


def test_overlap_flag(window: LogWindow, entries: EntryRepo) -> None:
    tue = datetime(2026, 9, 8, 7, 15, tzinfo=UTC)  # inside the 09:00–09:30 mail
    _add(entries, tue, 5, note="overlapper")
    window.apply_filters()
    m = window.model
    m.compute_overlaps_now()
    flagged = {
        m.index(r, Col.NOTE).data()
        for r in range(m.rowCount())
        if GLYPH_OVERLAP in m.index(r, Col.FLAGS).data()
    }
    assert flagged == {"tuesday mail", "overlapper"}


def test_delete_and_undo(window: LogWindow, entries: EntryRepo, qtbot) -> None:  # type: ignore[no-untyped-def]
    window.table.selectRow(0)
    window.table.selectionModel().select(
        window.model.index(1, 0),
        window.table.selectionModel().SelectionFlag.Select
        | window.table.selectionModel().SelectionFlag.Rows,
    )
    assert window.delete_action.isEnabled()
    ids = window.delete_selected(confirm=False)
    assert len(ids) == 2
    assert window.model.rowCount() == 1
    assert entries.count() == 2
    assert window.undo_action.isEnabled()
    window.undo_delete()
    assert window.model.rowCount() == 3
    assert entries.count() == 4
    assert not window.undo_action.isEnabled()


def test_add_entry_form(
    window: LogWindow, entries: EntryRepo, clients: LabelRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    from timetracker.ui.dialogs.add_entry import AddEntryDialog

    asics = clients.find_by_name("asics")
    assert asics is not None
    captured: dict[str, AddEntryDialog] = {}

    def fake_exec(self: AddEntryDialog) -> int:
        captured["dialog"] = self
        self.date.setDate(QDate(2026, 9, 8))
        self.start.setTime(self.start.time().__class__(14, 0))
        self.duration.setText("1h30")
        self.client.setCurrentIndex(self.client.findData(asics.id))
        self.note.setText("gap on Tuesday")
        self._validate()  # noqa: SLF001
        return int(self.result())

    monkeypatch.setattr(AddEntryDialog, "exec", fake_exec)
    window.add_entry()
    m = window.model
    added = next(r for r in range(m.rowCount()) if m.index(r, Col.NOTE).data() == "gap on Tuesday")
    assert m.index(added, Col.DATE).data() == "Tue 08 Sep 2026"
    assert m.index(added, Col.START).data() == "14:00"
    assert m.index(added, Col.END).data() == "15:30"
    assert m.index(added, Col.DURATION).data() == "1:30"
    assert m.index(added, Col.CLIENT).data() == "ASICS"
    assert m.index(added, Col.METHOD).data() == "Manual"
    assert entries.count() == 5


def test_export_options_dialog_defaults_and_persistence(
    window: LogWindow, settings_service: SettingsService
) -> None:
    from timetracker.core.rounding import RoundingScope
    from timetracker.ui.dialogs.export_options import ExportOptionsDialog

    dialog = ExportOptionsDialog("xlsx", 3, 6, RoundingScope.PER_ENTRY)
    assert dialog.rounding_minutes() == 6
    assert dialog.rounding_scope() is RoundingScope.PER_ENTRY
    assert dialog.scope.isEnabled()
    dialog.increment.setCurrentIndex(0)
    assert not dialog.scope.isEnabled()
    dialog.close()
    assert window.default_export_name("csv") == "timetracker_2026-09-07_2026-09-13.csv"


def test_export_writes_file_through_the_window(
    window: LogWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qtbot, clock: FakeClock
) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtWidgets import QFileDialog

    from timetracker.core.rounding import RoundingScope
    from timetracker.services.export_service import ExportOptions

    target = tmp_path / "week.csv"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))
    )
    options = window.build_export_options("csv", 6, RoundingScope.PER_GROUP)
    assert isinstance(options, ExportOptions)
    # In-memory test DB has no path for the worker: run the sync path it delegates to.
    window._exporter.export_sync(window._repo, options, target)  # noqa: SLF001
    text = target.read_text(encoding="utf-8-sig")
    assert target.read_bytes().count(b"\r\n") >= 4
    d = options.csv_delimiter  # locale-dependent: ";" on a European locale, "," elsewhere
    assert f"Rounding{d}6 minutes, rounded up per day × client × type" in text.replace('"', "")


def test_add_entry_with_a_new_typed_client_outside_the_range(
    window: LogWindow, entries: EntryRepo, clients: LabelRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two M5 field reports: a typed client must become a label, and an entry
    added outside the current date range must still be shown (range widened)."""
    from timetracker.ui.dialogs.add_entry import AddEntryDialog

    def fake_exec(self: AddEntryDialog) -> int:
        self.date.setDate(QDate(2026, 8, 20))  # three weeks back: outside "This week"
        self.duration.setText("90")
        self.client.setEditText("ASICS Europe")  # does not exist yet
        self.type.setEditText("Site visit")  # neither does this
        self._validate()  # noqa: SLF001
        return int(self.result())

    monkeypatch.setattr(AddEntryDialog, "exec", fake_exec)
    assert clients.find_by_name("asics europe") is None
    window.add_entry()
    created = clients.find_by_name("asics europe")
    assert created is not None and created.name == "ASICS Europe"
    assert window.current_preset() is DatePreset.CUSTOM
    assert window.model.filter.date_from == date(2026, 8, 20)
    assert window.model.filter.date_to == date(2026, 9, 13)
    m = window.model
    rows = [m.index(r, Col.CLIENT).data() for r in range(m.rowCount())]
    assert "ASICS Europe" in rows
    selected = window.selected_entry_ids()
    assert len(selected) == 1 and entries.get(selected[0]).client_id == created.id
    assert "range widened" in window.status.currentMessage()


# -- FR-608 export presets --------------------------------------------------------


def test_export_dialog_columns_and_save_as_preset(
    window: LogWindow, settings_service: SettingsService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QMessageBox

    from timetracker.services.export_service import COLUMNS

    dialog = window.make_export_dialog("xlsx")
    assert dialog.columns() == COLUMNS  # FR-603: all on by default
    assert dialog.folder_path() == settings_service.export_folder
    dialog.column_boxes["Note"].setChecked(False)
    dialog.column_boxes["Record method"].setChecked(False)
    assert dialog.columns() == COLUMNS[:7]
    dialog.increment.setCurrentIndex(dialog.increment.findData(15))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    assert dialog.save_preset_named("  ") is False  # empty name refused with a message
    assert dialog.save_preset_named("Invoice") is True
    saved = settings_service.export_presets().get("Invoice")
    assert saved is not None
    assert (saved.fmt, saved.columns, saved.rounding_minutes) == ("xlsx", COLUMNS[:7], 15)
    assert saved.folder is None or saved.folder == str(settings_service.export_folder)
    # Every column off disables Export and Save.
    for cb in dialog.column_boxes.values():
        cb.setChecked(False)
    assert not dialog.save_preset_button.isEnabled()
    dialog.close()
    # The Export menu lists it, after the separator.
    texts = [a.text() for a in window.export_menu.actions() if not a.isSeparator()]
    assert texts == ["CSV…", "Excel (XLSX)…", "Invoice  (XLSX)"]
    settings_service.remove_export_preset("Invoice")
    texts = [a.text() for a in window.export_menu.actions() if not a.isSeparator()]
    assert texts == ["CSV…", "Excel (XLSX)…"]


def test_run_preset_exports_the_current_view_in_one_click(
    window: LogWindow,
    settings_service: SettingsService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from timetracker.core.export_presets import ExportPreset

    out = tmp_path / "invoices"
    settings_service.save_export_preset(
        ExportPreset("Weekly", "csv", ("Date", "Client", "Duration (h:mm)"), 6, folder=str(out))
    )
    # The in-memory test DB has no path for the worker: route through the sync path.
    monkeypatch.setattr(
        window._exporter,  # noqa: SLF001
        "export",
        lambda options, path: window._exporter.export_sync(window._repo, options, path),  # noqa: SLF001
    )
    first = window.run_preset("Weekly")
    assert first == out / "timetracker_2026-09-07_2026-09-13.csv"
    assert first.exists()
    header = first.read_text(encoding="utf-8-sig").splitlines()[0].replace('"', "")
    d = settings_service.csv_delimiter
    assert header == d.join(("Date", "Client", "Duration (h:mm)"))
    second = window.run_preset("Weekly")  # never overwrites
    assert second == out / "timetracker_2026-09-07_2026-09-13-2.csv"
    assert window.run_preset("gone") is None
