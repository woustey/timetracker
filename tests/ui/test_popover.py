"""Popover interactions with pytest-qt (FR-102, FR-201–FR-204, FR-206, FR-401)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QRect, Qt

from timetracker.core.clock import FakeClock
from timetracker.core.models import Dimension, RecordMethod
from timetracker.data.entry_repo import EntryRepo
from timetracker.data.label_repo import LabelRepo
from timetracker.data.timer_repo import TimerRepo
from timetracker.services.label_service import LabelService
from timetracker.services.timer_service import TimerService
from timetracker.ui.popover import Popover


@pytest.fixture
def popover(
    qtbot, service: TimerService, labels: LabelService, entry_service, settings_service
) -> Popover:  # type: ignore[no-untyped-def]
    labels.ensure_seed_types()
    w = Popover(service, labels, entry_service, settings_service)
    qtbot.addWidget(w)
    return w


def test_idle_layout(popover: Popover) -> None:
    popover.refresh()
    assert popover.start_stop.text() == "Start"
    assert popover.elapsed.text() == "0:00:00"
    assert not popover.elapsed.isEnabled()
    assert popover.note.isHidden()
    assert popover.started_at.isHidden()
    assert popover.pause_resume.isHidden()
    assert popover.today.text() == "Today: 0:00"
    # Seeded types are present; clients are empty except the placeholder.
    assert [popover.type.itemText(i) for i in range(popover.type.count())] == [
        "—",
        "Email/Chat",
        "Phone",
        "Meeting/Call",
        "Work",
    ]
    assert popover.client.count() == 1


def test_start_and_stop_from_button(
    popover: Popover,
    service: TimerService,
    entries: EntryRepo,
    timers: TimerRepo,
    clock: FakeClock,
    qtbot,
) -> None:  # type: ignore[no-untyped-def]
    popover.refresh()
    popover.type.setCurrentIndex(popover.type.findText("Work"))
    qtbot.mouseClick(popover.start_stop, Qt.MouseButton.LeftButton)

    assert service.is_running
    assert popover.start_stop.text() == "Stop"
    assert popover.elapsed.isEnabled()
    assert popover.note.isVisibleTo(popover)
    assert popover.started_at.text() == "Started 12:00"  # 10:00 UTC in Brussels (CEST)
    row = timers.get()
    assert row is not None
    assert row.type_id is not None

    clock.advance(4983)
    service.on_tick()
    assert popover.elapsed.text() == "1:23:03"

    qtbot.mouseClick(popover.start_stop, Qt.MouseButton.LeftButton)
    assert not service.is_running
    assert popover.start_stop.text() == "Start"
    assert popover.elapsed.text() == "0:00:00"
    assert popover.today.text() == "Today: 1:23"
    (entry,) = entries.query()
    assert entry.record_method is RecordMethod.STOPWATCH
    assert entry.duration_seconds == 4983
    assert entry.type_id == row.type_id


def test_typing_a_new_client_creates_the_label(
    popover: Popover, service: TimerService, clients: LabelRepo, labels: LabelService, qtbot
) -> None:  # type: ignore[no-untyped-def]
    popover.refresh()
    with qtbot.waitSignal(labels.labels_changed, timeout=1000):
        popover.client.setEditText("  Puma ")
        qtbot.mouseClick(popover.start_stop, Qt.MouseButton.LeftButton)
    puma = clients.find_by_name("puma")
    assert puma is not None and puma.name == "Puma"
    assert service.running is not None and service.running.client_id == puma.id
    # The chip is now in the list and selected.
    assert popover.client.currentText() == "Puma"
    assert popover.client.selected_id() == puma.id

    # Typing the same name in another casing resolves to the same label (FR-402).
    popover.client.setEditText("PUMA")
    assert popover.client.commit() == puma.id
    assert clients.count() == 1


def test_labels_and_note_edit_while_running(
    popover: Popover, service: TimerService, clients: LabelRepo, timers: TimerRepo, qtbot
) -> None:  # type: ignore[no-untyped-def]
    nike = clients.create("Nike")
    service.start()
    popover.refresh()
    popover.client.setCurrentIndex(popover.client.findData(nike.id))
    popover.client.activated.emit(popover.client.currentIndex())
    popover.note.setText("drafting the brief")
    popover.note.editingFinished.emit()
    row = timers.get()
    assert row is not None
    assert row.client_id == nike.id
    assert row.note == "drafting the brief"


def test_default_labels_prefilled_from_last_entry(
    popover: Popover, service: TimerService, clients: LabelRepo, types: LabelRepo, clock: FakeClock
) -> None:
    nike = clients.create("Nike")
    work = types.find_by_name("Work")
    assert work is not None
    service.start(nike.id, work.id)
    clock.advance(5)
    service.stop()
    popover.refresh()
    assert popover.client.selected_id() == nike.id
    assert popover.type.selected_id() == work.id


def test_show_near_clamps_to_screen_and_esc_dismisses(popover: Popover, qtbot) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtGui import QGuiApplication

    avail = QGuiApplication.primaryScreen().availableGeometry()
    # A bottom-right anchor (Windows tray) must not push the popover off-screen.
    anchor = QRect(avail.right() - 8, avail.bottom() - 8, 16, 16)
    popover.show_near(anchor)
    qtbot.waitExposed(popover)
    frame = popover.frameGeometry()
    assert avail.contains(frame), (frame, avail)
    assert popover.isVisible()

    with qtbot.waitSignal(popover.dismissed, timeout=1000):
        qtbot.keyClick(popover, Qt.Key.Key_Escape)
    assert not popover.isVisible()


def test_new_labels_appear_without_reopen(popover: Popover, labels: LabelService) -> None:
    popover.refresh()
    before = popover.client.count()
    labels.get_or_create(Dimension.CLIENT, "Reebok")
    assert popover.client.count() == before + 1
    assert popover.client.findText("Reebok") > 0


def test_mode_switch_and_add_time_button(popover: Popover, qtbot) -> None:  # type: ignore[no-untyped-def]
    from timetracker.ui.popover import MATRIX_WIDTH, POPOVER_WIDTH, PopoverMode

    assert popover.mode is PopoverMode.STOPWATCH
    assert popover.width() == POPOVER_WIDTH
    qtbot.mouseClick(popover.add_time, Qt.MouseButton.LeftButton)
    assert popover.mode is PopoverMode.MATRIX
    assert popover.pages.currentWidget() is popover.matrix_page
    assert popover.width() == MATRIX_WIDTH
    qtbot.mouseClick(popover.back_button, Qt.MouseButton.LeftButton)
    assert popover.mode is PopoverMode.STOPWATCH
    assert popover.width() == POPOVER_WIDTH


def test_matrix_mode_persists_across_dismiss(popover: Popover, qtbot) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtGui import QGuiApplication

    from timetracker.ui.popover import PopoverMode

    popover.set_mode(PopoverMode.MATRIX)
    popover.matrix.time_chips[2].click()  # +30
    anchor = QRect(
        QGuiApplication.primaryScreen().availableGeometry().center(), QRect(0, 0, 16, 16).size()
    )
    popover.show_near(anchor)
    qtbot.waitExposed(popover)
    with qtbot.waitSignal(popover.dismissed, timeout=1000):
        qtbot.keyClick(popover.matrix, Qt.Key.Key_Escape)
    assert not popover.isVisible()
    assert popover.mode is PopoverMode.MATRIX
    assert popover.matrix.pending_seconds == 1800  # not lost by an accidental Esc


def test_last_mode_is_remembered_across_launches(
    popover: Popover,
    service: TimerService,
    labels: LabelService,
    entry_service,
    settings_service,
    qtbot,
) -> None:  # type: ignore[no-untyped-def]
    from timetracker.ui.popover import PopoverMode

    popover.set_mode(PopoverMode.MATRIX)
    # A fresh popover over the same settings (what a relaunch does) lands on the matrix.
    again = Popover(service, labels, entry_service, settings_service)
    qtbot.addWidget(again)
    assert again.mode is PopoverMode.MATRIX
    assert again.pages.currentWidget() is again.matrix_page
    again.set_mode(PopoverMode.STOPWATCH)
    third = Popover(service, labels, entry_service, settings_service)
    qtbot.addWidget(third)
    assert third.mode is PopoverMode.STOPWATCH


def test_fr212_pause_and_resume_from_the_popover(
    popover: Popover, service: TimerService, entries: EntryRepo, clock: FakeClock, qtbot
) -> None:  # type: ignore[no-untyped-def]
    popover.refresh()
    qtbot.mouseClick(popover.start_stop, Qt.MouseButton.LeftButton)
    assert popover.pause_resume.isVisibleTo(popover)
    assert popover.pause_resume.text() == "Pause"
    clock.advance(600)
    service.on_tick()
    qtbot.mouseClick(popover.pause_resume, Qt.MouseButton.LeftButton)
    assert service.is_paused
    assert popover.pause_resume.text() == "Resume"
    assert popover.start_stop.text() == "Stop"
    assert popover.started_at.text() == "Started 12:00 · paused"
    assert not popover.elapsed.isEnabled()
    assert popover.elapsed.text() == "0:10:00"
    clock.advance(300)
    assert popover.elapsed.text() == "0:10:00"
    qtbot.mouseClick(popover.pause_resume, Qt.MouseButton.LeftButton)
    assert service.is_running
    assert popover.pause_resume.text() == "Pause"
    assert popover.started_at.text() == "Started 12:00 · paused 0:05"
    assert popover.elapsed.isEnabled()
    clock.advance(60)
    service.on_tick()
    assert popover.elapsed.text() == "0:11:00"
    qtbot.mouseClick(popover.start_stop, Qt.MouseButton.LeftButton)
    (entry,) = entries.query()
    assert (entry.duration_seconds, entry.paused_seconds) == (660, 300)
    assert popover.pause_resume.isHidden()
