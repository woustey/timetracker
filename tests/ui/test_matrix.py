"""The Add Time matrix under pytest-qt (PRD-02 §11 "UI"; FR-301–FR-315, FR-401–FR-403).

Includes the M3 acceptance test: a 30-minute entry in ≤ 4 clicks and < 5 s.
"""

from __future__ import annotations

import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from timetracker.core.clock import FakeClock
from timetracker.core.models import Dimension, RecordMethod
from timetracker.data.entry_repo import EntryRepo
from timetracker.data.label_repo import LabelRepo
from timetracker.services.entry_service import EntryService
from timetracker.services.label_service import LabelService
from timetracker.services.settings_service import (
    KEY_MANDATORY_CLIENT,
    KEY_MANDATORY_TYPE,
    SettingsService,
)
from timetracker.ui.quickadd.matrix import Matrix


@pytest.fixture
def matrix(  # type: ignore[no-untyped-def]
    qtbot,
    entry_service: EntryService,
    labels: LabelService,
    settings_service: SettingsService,
    clients: LabelRepo,
) -> Matrix:
    labels.ensure_seed_types()
    for name in ("Nike", "Adidas", "ASICS", "Reebok"):
        clients.create(name)
    w = Matrix(entry_service, labels, settings_service)
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    return w


def _chip(matrix: Matrix, dimension: Dimension, name: str):  # type: ignore[no-untyped-def]
    return next(c for c in matrix.chips(dimension) if c.text() == name)


# -- layout ----------------------------------------------------------------------


def test_columns_and_custom_cells(matrix: Matrix) -> None:
    assert [c.text() for c in matrix.time_chips] == ["+6min", "+15min", "+30min", "+45min"]
    assert [c.text() for c in matrix.chips(Dimension.TYPE)] == [
        "Email/Chat",
        "Phone",
        "Meeting/Call",
        "Work",
    ]
    assert [c.text() for c in matrix.chips(Dimension.CLIENT)] == [
        "Nike",
        "Adidas",
        "ASICS",
        "Reebok",
    ]
    for cell in (matrix.custom_time, matrix.custom_type, matrix.custom_client):
        assert not cell.is_editing
        assert cell.button.text() == "Custom…"
    assert matrix.pending_total.label.text() == "Pending: 0:00"
    assert matrix.today.text() == "Today: 0:00"
    assert not matrix.add_button.isEnabled()


# -- time column (FR-303, FR-304, FR-305) ------------------------------------------


def test_time_is_additive_with_badges(matrix: Matrix, qtbot) -> None:  # type: ignore[no-untyped-def]
    plus15 = matrix.time_chips[1]
    qtbot.mouseClick(plus15, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(plus15, Qt.MouseButton.LeftButton)  # +15 twice = 30 (FR-303)
    qtbot.mouseClick(matrix.time_chips[0], Qt.MouseButton.LeftButton)
    assert matrix.pending_seconds == 36 * 60
    assert matrix.pending_total.label.text() == "Pending: 0:36"
    assert plus15.count == 2
    assert matrix.time_chips[0].count == 1


def test_shift_click_subtracts_and_floors_at_zero(matrix: Matrix, qtbot) -> None:  # type: ignore[no-untyped-def]
    plus30, plus45 = matrix.time_chips[2], matrix.time_chips[3]
    qtbot.mouseClick(plus30, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(plus45, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier)
    assert matrix.pending_seconds == 0  # 30 − 45 floors at zero (FR-305)
    assert plus30.count == 0 and plus45.count == 0  # nothing contributes to zero
    qtbot.mouseClick(plus30, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(plus30, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier)
    assert matrix.pending_seconds == 0
    assert plus30.count == 0


def test_clear_resets_total_and_note_but_keeps_labels(matrix: Matrix, qtbot) -> None:  # type: ignore[no-untyped-def]
    qtbot.mouseClick(matrix.time_chips[2], Qt.MouseButton.LeftButton)
    _chip(matrix, Dimension.CLIENT, "Nike").click()
    matrix.note.setPlainText("hello")
    qtbot.mouseClick(matrix.clear_button, Qt.MouseButton.LeftButton)
    assert matrix.pending_seconds == 0
    assert matrix.note_text() == ""
    assert matrix.time_chips[2].count == 0
    assert _chip(matrix, Dimension.CLIENT, "Nike").isChecked()


def test_custom_time_parses_grammar_and_flags_errors(matrix: Matrix, qtbot) -> None:  # type: ignore[no-untyped-def]
    qtbot.mouseClick(matrix.custom_time.button, Qt.MouseButton.LeftButton)
    assert matrix.custom_time.is_editing
    qtbot.keyClicks(matrix.custom_time.edit, "1h15")
    qtbot.keyClick(matrix.custom_time.edit, Qt.Key.Key_Return)
    assert matrix.pending_seconds == 75 * 60
    assert not matrix.custom_time.is_editing

    qtbot.mouseClick(matrix.custom_time.button, Qt.MouseButton.LeftButton)
    qtbot.keyClicks(matrix.custom_time.edit, "banana")
    qtbot.keyClick(matrix.custom_time.edit, Qt.Key.Key_Return)
    assert matrix.custom_time.is_editing  # stays open in error state
    assert matrix.custom_time.edit.property("error") is True
    assert matrix.pending_seconds == 75 * 60  # total unchanged (§5.5)
    qtbot.keyClick(matrix.custom_time.edit, Qt.Key.Key_Escape)
    assert not matrix.custom_time.is_editing


def test_pending_total_click_to_edit(matrix: Matrix, qtbot) -> None:  # type: ignore[no-untyped-def]
    qtbot.mouseClick(matrix.time_chips[0], Qt.MouseButton.LeftButton)
    qtbot.mouseClick(matrix.pending_total.label, Qt.MouseButton.LeftButton)
    assert matrix.pending_total.currentWidget() is matrix.pending_total.edit
    matrix.pending_total.edit.setText("0:50")
    qtbot.keyClick(matrix.pending_total.edit, Qt.Key.Key_Return)
    assert matrix.pending_seconds == 50 * 60
    assert matrix.time_chips[0].count == 0  # no longer attributable to a chip


# -- label columns (FR-306, FR-307, FR-309, FR-401–FR-403) --------------------------


def test_label_columns_are_exclusive(matrix: Matrix) -> None:
    email, phone = (
        _chip(matrix, Dimension.TYPE, "Email/Chat"),
        _chip(matrix, Dimension.TYPE, "Phone"),
    )
    email.click()
    assert email.isChecked()
    phone.click()
    assert phone.isChecked() and not email.isChecked()
    assert matrix.selected(Dimension.TYPE) == phone.value
    # Selecting in one column never touches the other.
    nike = _chip(matrix, Dimension.CLIENT, "Nike")
    nike.click()
    assert phone.isChecked() and nike.isChecked()
    assert matrix.selected(Dimension.CLIENT) == nike.value


def test_custom_label_promotes_to_chip_and_selects_it(
    matrix: Matrix, clients: LabelRepo, qtbot
) -> None:  # type: ignore[no-untyped-def]
    qtbot.mouseClick(matrix.custom_client.button, Qt.MouseButton.LeftButton)
    qtbot.keyClicks(matrix.custom_client.edit, " Puma ")
    qtbot.keyClick(matrix.custom_client.edit, Qt.Key.Key_Return)
    puma = clients.find_by_name("puma")
    assert puma is not None and puma.name == "Puma"
    names = [c.text() for c in matrix.chips(Dimension.CLIENT)]
    assert names == ["Nike", "Adidas", "ASICS", "Reebok", "Puma"]
    assert matrix.selected(Dimension.CLIENT) == puma.id
    assert not matrix.custom_client.is_editing


def test_custom_label_resolves_case_insensitively(
    matrix: Matrix, clients: LabelRepo, qtbot
) -> None:  # type: ignore[no-untyped-def]
    qtbot.mouseClick(matrix.custom_client.button, Qt.MouseButton.LeftButton)
    qtbot.keyClicks(matrix.custom_client.edit, "NIKE ")
    qtbot.keyClick(matrix.custom_client.edit, Qt.Key.Key_Return)
    nike = clients.find_by_name("nike")
    assert nike is not None
    assert matrix.selected(Dimension.CLIENT) == nike.id
    assert clients.count() == 4  # no new label (FR-402)


def test_near_duplicate_offers_existing_label(matrix: Matrix, clients: LabelRepo, qtbot) -> None:  # type: ignore[no-untyped-def]
    qtbot.mouseClick(matrix.custom_client.button, Qt.MouseButton.LeftButton)
    qtbot.keyClicks(matrix.custom_client.edit, "Addidas")
    qtbot.keyClick(matrix.custom_client.edit, Qt.Key.Key_Return)
    menu = matrix._near_dup_menu  # noqa: SLF001 - test hook
    texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert texts == ["Use “Adidas”", "Create “Addidas”"]
    menu.actions()[0].trigger()
    menu.close()
    adidas = clients.find_by_name("adidas")
    assert adidas is not None
    assert matrix.selected(Dimension.CLIENT) == adidas.id
    assert clients.count() == 4


def test_near_duplicate_can_be_overridden(matrix: Matrix, clients: LabelRepo, qtbot) -> None:  # type: ignore[no-untyped-def]
    qtbot.mouseClick(matrix.custom_client.button, Qt.MouseButton.LeftButton)
    qtbot.keyClicks(matrix.custom_client.edit, "Addidas")
    qtbot.keyClick(matrix.custom_client.edit, Qt.Key.Key_Return)
    menu = matrix._near_dup_menu  # noqa: SLF001 - test hook
    menu.actions()[-1].trigger()  # Create “Addidas”
    menu.close()
    created = clients.find_by_name("addidas")
    assert created is not None
    assert matrix.selected(Dimension.CLIENT) == created.id
    assert clients.count() == 5


# -- Add enablement and commit (FR-310, FR-311, FR-312, FR-314) --------------------


def test_add_enablement_and_tooltip(matrix: Matrix, settings_service: SettingsService) -> None:
    assert not matrix.add_button.isEnabled()
    assert matrix.add_button.toolTip() == "Add some time first"
    matrix.time_chips[2].click()
    assert matrix.add_button.toolTip() == "Choose a category"
    _chip(matrix, Dimension.TYPE, "Work").click()
    assert matrix.add_button.toolTip() == "Choose a client"
    assert not matrix.add_button.isEnabled()
    _chip(matrix, Dimension.CLIENT, "ASICS").click()
    assert matrix.add_button.isEnabled()
    # Optional labels (Q1 setting) relax the gate.
    matrix.select(Dimension.CLIENT, None)
    assert not matrix.add_button.isEnabled()
    settings_service.set(KEY_MANDATORY_CLIENT, False)
    assert matrix.add_button.isEnabled()
    settings_service.set(KEY_MANDATORY_TYPE, False)
    matrix.select(Dimension.TYPE, None)
    assert matrix.add_button.isEnabled()


def test_commit_writes_entry_shows_toast_and_keeps_labels(
    matrix: Matrix, entries: EntryRepo, clients: LabelRepo, clock: FakeClock, qtbot
) -> None:  # type: ignore[no-untyped-def]
    matrix.time_chips[2].click()
    _chip(matrix, Dimension.TYPE, "Meeting/Call").click()
    _chip(matrix, Dimension.CLIENT, "ASICS").click()
    matrix.note.setPlainText("kick-off")
    with qtbot.waitSignal(matrix.committed, timeout=1000) as blocker:
        qtbot.mouseClick(matrix.add_button, Qt.MouseButton.LeftButton)
    entry = blocker.args[0]
    assert entry.record_method is RecordMethod.QUICKADD
    assert entry.duration_seconds == 1800
    assert entry.note == "kick-off"
    assert entry.client_id == clients.find_by_name("asics").id  # type: ignore[union-attr]
    assert entries.count() == 1

    assert matrix.toast.isVisible()
    assert matrix.toast.message.text() == "0:30 · Meeting/Call · ASICS — added"
    assert matrix.toast.is_active
    # FR-312: total and note reset, labels retained.
    assert matrix.pending_seconds == 0
    assert matrix.note_text() == ""
    assert _chip(matrix, Dimension.TYPE, "Meeting/Call").isChecked()
    assert _chip(matrix, Dimension.CLIENT, "ASICS").isChecked()
    assert matrix.today.text() == "Today: 0:30"
    assert not matrix.add_button.isEnabled()


def test_toast_undo_removes_the_entry(matrix: Matrix, entries: EntryRepo, qtbot) -> None:  # type: ignore[no-untyped-def]
    matrix.time_chips[1].click()
    _chip(matrix, Dimension.TYPE, "Phone").click()
    _chip(matrix, Dimension.CLIENT, "Nike").click()
    matrix.commit()
    assert entries.count() == 1
    qtbot.mouseClick(matrix.toast.undo_button, Qt.MouseButton.LeftButton)
    assert entries.count() == 0
    assert matrix.today.text() == "Today: 0:00"
    assert matrix.toast.message.text() == "Entry removed"
    assert matrix.toast.undo_button.isHidden()


def test_note_is_capped_at_500_with_warning(matrix: Matrix) -> None:
    matrix.note.setPlainText("x" * 600)
    assert len(matrix.note.toPlainText()) == 500
    assert matrix.note_warning.isVisible()
    matrix.note.setPlainText("short")
    assert not matrix.note_warning.isVisible()


def test_prepare_prefills_mru_labels(
    matrix: Matrix, entry_service: EntryService, clients: LabelRepo, types: LabelRepo
) -> None:
    reebok = clients.find_by_name("reebok")
    work = types.find_by_name("work")
    assert reebok is not None and work is not None
    entry_service.add_quick(600, reebok.id, work.id, None)
    matrix.prepare()
    assert matrix.selected(Dimension.CLIENT) == reebok.id
    assert matrix.selected(Dimension.TYPE) == work.id


# -- keyboard map (§9.3.5, FR-315) --------------------------------------------------


def test_keyboard_map(matrix: Matrix, entries: EntryRepo, qtbot) -> None:  # type: ignore[no-untyped-def]
    matrix.setFocus()
    qtbot.keyClick(matrix, Qt.Key.Key_3)  # +30
    qtbot.keyClick(matrix, Qt.Key.Key_1)  # +6
    qtbot.keyClick(matrix, Qt.Key.Key_1, Qt.KeyboardModifier.ShiftModifier)  # −6
    assert matrix.pending_seconds == 1800
    qtbot.keyClick(matrix, Qt.Key.Key_E)  # 3rd category: Meeting/Call
    qtbot.keyClick(matrix, Qt.Key.Key_D)  # 3rd client: ASICS
    assert _chip(matrix, Dimension.TYPE, "Meeting/Call").isChecked()
    assert _chip(matrix, Dimension.CLIENT, "ASICS").isChecked()

    qtbot.keyClick(matrix, Qt.Key.Key_Tab)  # Tab reaches the note
    assert QApplication.focusWidget() is matrix.note
    qtbot.keyClicks(matrix.note, "typed 3 things")  # digits in the note are text, not chips
    assert matrix.pending_seconds == 1800
    qtbot.keyClick(matrix.note, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert "\n" in matrix.note.toPlainText()
    qtbot.keyClick(matrix.note, Qt.Key.Key_Return)  # Enter commits, even from the note
    assert entries.count() == 1
    assert entries.recent(1)[0].note == "typed 3 things"

    qtbot.keyClick(matrix, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)  # undo
    assert entries.count() == 0

    qtbot.keyClick(matrix, Qt.Key.Key_5)  # 5th time cell = Custom…
    assert matrix.custom_time.is_editing
    qtbot.keyClick(matrix.custom_time.edit, Qt.Key.Key_Escape)  # Esc in the editor only reverts it
    assert not matrix.custom_time.is_editing

    with qtbot.waitSignal(matrix.dismiss_requested, timeout=1000):
        qtbot.keyClick(matrix, Qt.Key.Key_Escape)


def test_fifth_label_key_opens_custom_cell(matrix: Matrix, qtbot) -> None:  # type: ignore[no-untyped-def]
    matrix.setFocus()
    qtbot.keyClick(matrix, Qt.Key.Key_T)  # 5th category (only 4 exist) → Custom…
    assert matrix.custom_type.is_editing
    qtbot.keyClick(matrix.custom_type.edit, Qt.Key.Key_Escape)
    qtbot.keyClick(matrix, Qt.Key.Key_G)
    assert matrix.custom_client.is_editing


# -- M3 acceptance: ≤ 4 clicks and < 5 s for a 30-minute entry ----------------------


def test_acceptance_thirty_minutes_in_three_clicks(
    matrix: Matrix,
    entry_service: EntryService,
    entries: EntryRepo,
    clients: LabelRepo,
    types: LabelRepo,
    qtbot,
) -> None:  # type: ignore[no-untyped-def]
    """Steady state: labels are sticky/MRU, so tray-click + `+30min` + `Add` = 3 clicks.

    The tray click itself is outside this widget; counting it, the total is
    3 ≤ 4 (G1). Wall time is measured for the record; the human budget is 5 s.
    """
    asics = clients.find_by_name("asics")
    meeting = types.find_by_name("meeting/call")
    assert asics is not None and meeting is not None
    entry_service.add_quick(600, asics.id, meeting.id, None)  # yesterday's last entry
    matrix.prepare()  # what the popover does on open (the tray click)

    clicks = 0
    started = time.perf_counter()
    qtbot.mouseClick(matrix.time_chips[2], Qt.MouseButton.LeftButton)
    clicks += 1
    assert matrix.add_button.isEnabled()
    with qtbot.waitSignal(matrix.committed, timeout=1000):
        qtbot.mouseClick(matrix.add_button, Qt.MouseButton.LeftButton)
    clicks += 1
    elapsed = time.perf_counter() - started

    assert clicks + 1 <= 4  # + the tray click
    assert elapsed < 5.0
    latest = entry_service.last_added
    assert latest is not None
    assert entries.count() == 2
    assert latest.duration_seconds == 1800
    assert latest.client_id == asics.id and latest.type_id == meeting.id
    assert latest.record_method is RecordMethod.QUICKADD
