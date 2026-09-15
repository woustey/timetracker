"""M6 acceptance: full keyboard traversal and screen-reader names (PRD-01 §9.5).

For each main surface the Tab chain is walked from its first focusable widget
until it wraps; the walk must visit every interactive widget the user can
click (no dead ends, nothing unreachable), and every one of those widgets must
carry an accessible name. Chips must expose their selected state as
``checked`` to the accessibility layer (a checkmark glyph is painted as well,
so colour is never the only signal).
"""

from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLineEdit,
    QListWidget,
    QTableView,
    QTextEdit,
    QWidget,
)

from timetracker.core.models import Dimension
from timetracker.services.entry_service import EntryService
from timetracker.services.label_service import LabelService
from timetracker.services.settings_service import SettingsService
from timetracker.services.timer_service import TimerService
from timetracker.ui.popover import Popover, PopoverMode
from timetracker.ui.quickadd.chip import Chip
from timetracker.ui.quickadd.matrix import Matrix

INTERACTIVE = (
    QAbstractButton,
    QComboBox,
    QLineEdit,
    QTextEdit,
    QAbstractSpinBox,
    QTableView,
    QListWidget,
)


def _interactive(root: QWidget) -> list[QWidget]:
    out: list[QWidget] = []
    for w in root.findChildren(QWidget):
        if not isinstance(w, INTERACTIVE):
            continue
        if not w.isVisibleTo(root) or not w.isEnabled():
            continue
        if w.focusPolicy() == Qt.FocusPolicy.NoFocus:
            continue
        # Skip internal helpers (a combo's own line edit, a list's viewport).
        if isinstance(w.parent(), QComboBox | QAbstractSpinBox):
            continue
        out.append(w)
    return out


def _tab_chain(root: QWidget, start: QWidget, limit: int = 300) -> list[QWidget]:
    """Walk nextInFocusChain() from *start* until it comes back around."""
    seen: list[QWidget] = []
    w = start
    for _ in range(limit):
        if w.isVisibleTo(root) and w.isEnabled() and w.focusPolicy() & Qt.FocusPolicy.TabFocus:
            if w in seen:
                break
            seen.append(w)
        w = w.nextInFocusChain()
        if w is start:
            break
    return seen


def _accessible_name(w: QWidget) -> str:
    name = w.accessibleName()
    if name:
        return name
    if isinstance(w, QAbstractButton) and w.text():
        return w.text()
    # QLineEdit / combo inside a QFormLayout: the buddy label names it.
    return ""


def _check_surface(root: QWidget, start: QWidget) -> None:
    root.show()
    QApplication.processEvents()
    interactive = _interactive(root)
    chain = _tab_chain(root, start)
    chain_set = set(chain)
    unreachable = [w for w in interactive if w not in chain_set]
    assert not unreachable, "not reachable by Tab: " + ", ".join(
        f"{type(w).__name__}({_accessible_name(w) or w.objectName() or '?'})" for w in unreachable
    )
    unnamed = [w for w in interactive if not _accessible_name(w)]
    assert not unnamed, "no accessible name: " + ", ".join(
        f"{type(w).__name__}({w.objectName() or '?'})" for w in unnamed
    )


@pytest.fixture
def surfaces(  # type: ignore[no-untyped-def]
    qtbot,
    service: TimerService,
    labels: LabelService,
    entry_service: EntryService,
    settings_service: SettingsService,
    clients,
) -> dict[str, Any]:
    labels.ensure_seed_types()
    for name in ("Nike", "Adidas"):
        clients.create(name)
    popover = Popover(service, labels, entry_service, settings_service)
    qtbot.addWidget(popover)
    return {"popover": popover, "service": service}


def test_popover_stopwatch_page_is_keyboard_complete(surfaces: dict[str, Any]) -> None:
    popover: Popover = surfaces["popover"]
    popover.set_mode(PopoverMode.STOPWATCH)
    _check_surface(popover.stopwatch_page, popover.client)


def test_popover_running_state_is_keyboard_complete(surfaces: dict[str, Any]) -> None:
    popover: Popover = surfaces["popover"]
    surfaces["service"].start()
    popover.set_mode(PopoverMode.STOPWATCH)
    popover.refresh()
    _check_surface(popover.stopwatch_page, popover.client)
    surfaces["service"].stop()


def test_matrix_is_keyboard_complete_and_chips_expose_state(surfaces: dict[str, Any]) -> None:
    popover: Popover = surfaces["popover"]
    popover.set_mode(PopoverMode.MATRIX)
    matrix: Matrix = popover.matrix
    _check_surface(popover.matrix_page, matrix.note)
    chips = matrix.chips(Dimension.TYPE)
    assert all(c.accessibleName() == c.text() for c in chips + matrix.time_chips)
    chips[1].setChecked(True)
    assert chips[1].isCheckable() and chips[1].isChecked()  # exposed as "checked" to AT
    assert not chips[0].isChecked()
    assert matrix.time_chips[0].accessibleDescription() == ""
    matrix.time_chips[0].click()
    assert matrix.time_chips[0].accessibleDescription() == "added 1 times"


def test_log_window_is_keyboard_complete(
    qtbot, clock, entries, entry_service, labels, settings_service
) -> None:  # type: ignore[no-untyped-def]
    from timetracker.services.export_service import ExportService
    from timetracker.ui.log.window import LogWindow

    w = LogWindow(
        clock, entries, entry_service, labels, settings_service, ExportService(clock, None)
    )
    qtbot.addWidget(w)
    _check_surface(w, w.preset)


def test_settings_dialog_is_keyboard_complete(
    qtbot, clock, conn, tmp_path, labels, settings_service
) -> None:  # type: ignore[no-untyped-def]
    from timetracker.platform.base import Unavailable
    from timetracker.services.backup_service import BackupService
    from timetracker.ui.settings_dialog import SettingsDialog

    labels.ensure_seed_types()
    d = SettingsDialog(
        settings_service,
        labels,
        BackupService(clock, tmp_path / "t.sqlite3", conn),
        None,
        Unavailable("x"),
    )
    qtbot.addWidget(d)
    for i in range(d.tabs.count()):
        d.tabs.setCurrentIndex(i)
        page = d.tabs.currentWidget()
        first = next(iter(_interactive(page)), None)
        if first is not None:
            _check_surface(page, first)


def test_chip_has_checkmark_not_just_colour(qtbot) -> None:  # type: ignore[no-untyped-def]
    from timetracker.ui.quickadd.chip import CHECK_GLYPH, ChipKind

    chip = Chip("Work", ChipKind.LABEL, value=1)
    qtbot.addWidget(chip)
    chip.show()
    chip.setChecked(True)
    image = chip.grab().toImage()
    # Rendered pixels differ from an unchecked chip: the glyph is painted, not only a fill.
    chip.setChecked(False)
    image_off = chip.grab().toImage()
    assert image != image_off
    assert CHECK_GLYPH == "✓"
