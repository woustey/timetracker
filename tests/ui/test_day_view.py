"""Day view (FR-509): header totals, navigation, canvas geometry, double-click → log."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from PySide6.QtCore import QPoint

from timetracker.core.clock import FakeClock
from timetracker.core.models import NewEntry, RecordMethod
from timetracker.data.entry_repo import EntryRepo
from timetracker.data.label_repo import LabelRepo
from timetracker.services.entry_service import EntryService
from timetracker.services.label_service import LabelService
from timetracker.ui.views.day_view import AXIS_W, HOUR_PX, MARGIN
from timetracker.ui.views.window import ViewsWindow


def _add(entries: EntryRepo, start: datetime, minutes: int, **kw: object) -> None:
    entries.insert(
        NewEntry(
            started_at_utc=start,
            ended_at_utc=start + timedelta(minutes=minutes),
            tz_name="Europe/Brussels",
            duration_seconds=minutes * 60,
            record_method=RecordMethod.STOPWATCH,
            **kw,  # type: ignore[arg-type]
        )
    )


@pytest.fixture
def views(  # type: ignore[no-untyped-def]
    qtbot,
    clock: FakeClock,
    entries: EntryRepo,
    entry_service: EntryService,
    labels: LabelService,
    clients: LabelRepo,
) -> ViewsWindow:
    # Clock: Fri 11 Sep 2026 12:00 Brussels; entries 09:00–10:00, 10:30–11:00, 11:00–11:45 + overlap
    nike = clients.create("Nike")
    day = datetime(2026, 9, 11, 7, 0, tzinfo=UTC)  # 09:00 CEST
    _add(entries, day, 60, client_id=nike.id, note="kick-off")
    _add(entries, day + timedelta(minutes=90), 30)
    _add(entries, day + timedelta(minutes=120), 45)
    _add(entries, day + timedelta(minutes=135), 15, note="overlap")
    w = ViewsWindow(clock, entries, entry_service, labels)
    qtbot.addWidget(w)
    w.resize(640, 700)
    w.show()
    return w


def test_header_totals_and_canvas_geometry(views: ViewsWindow) -> None:
    dv = views.day_view
    assert dv.day == date(2026, 9, 11)
    assert dv.totals.text() == "4 entries · tracked 2:30 · gaps 0:30 · 09:00–11:45"
    canvas = dv.canvas
    lay = canvas.layout_data
    assert [(g.start_min, g.end_min) for g in lay.gaps] == [(600, 630)]
    rects = dict(canvas.block_rects())
    first = rects[1]
    assert first.top() == pytest.approx(MARGIN + (540 - canvas._first_hour * 60) * HOUR_PX / 60)  # noqa: SLF001
    assert first.height() == pytest.approx(HOUR_PX - 1)
    assert first.left() == AXIS_W + 1
    # Overlapping 3 and 4 share the width in two lanes.
    assert rects[3].width() == pytest.approx(rects[4].width())
    assert rects[3].width() < first.width()
    assert canvas.block_at(QPoint(int(first.center().x()), int(first.center().y()))) == 1
    assert canvas.block_at(QPoint(2, 2)) == -1


def test_navigation_and_empty_day(views: ViewsWindow) -> None:
    dv = views.day_view
    dv.next_button.click()
    assert dv.day == date(2026, 9, 12)
    assert dv.totals.text() == "No entries"
    assert dv.canvas.layout_data.is_empty
    dv.prev_button.click()
    dv.prev_button.click()
    assert dv.day == date(2026, 9, 10)
    dv.today_button.click()
    assert dv.day == date(2026, 9, 11)
    views.show_day(date(2026, 9, 1))
    assert dv.day == date(2026, 9, 1) and dv.date_edit.date().toPython() == date(2026, 9, 1)


def test_entries_changed_refreshes_and_double_click_reveals(
    views: ViewsWindow, entry_service: EntryService, qtbot
) -> None:  # type: ignore[no-untyped-def]
    dv = views.day_view
    entry_service.add_quick(1800, None, None, "late")  # today 11:30–12:00 (ends now)
    assert dv.totals.text().startswith("5 entries · tracked 3:00")
    rect = dict(dv.canvas.block_rects())[1]
    with qtbot.waitSignal(views.entry_activated, timeout=1000) as blocker:
        dv.canvas.entry_activated.emit(1)
    assert blocker.args == [1, date(2026, 9, 11)]
    assert rect.height() > 0


def test_log_toolbar_opens_the_views_window(booted_app) -> None:  # type: ignore[no-untyped-def]
    app = booted_app
    app.show_log()
    assert app.views_window is None
    app.log_window.views_action.trigger()
    assert app.views_window is not None and app.views_window.isVisible()
    app.views_window.close()
    assert app.views_window is None
    app.log_window.close()
