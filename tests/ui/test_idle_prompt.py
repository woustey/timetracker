"""Idle and long-running dialogs: buttons map to outcomes; closing answers nothing."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from PySide6.QtCore import Qt

from timetracker.services.idle_monitor import IdleOutcome, IdleSource, IdleSpan
from timetracker.ui.dialogs.idle_prompt import IdlePromptDialog
from timetracker.ui.dialogs.long_running import LongRunningDialog


def _span(
    seconds: int = 750, source: IdleSource = IdleSource.INPUT, still: bool = False
) -> IdleSpan:
    return IdleSpan(
        started_at_utc=datetime(2026, 9, 11, 12, 5, tzinfo=UTC),  # 14:05 Brussels
        seconds=seconds,
        counted_seconds=seconds,
        source=source,
        still_idle=still,
    )


@pytest.mark.parametrize(
    ("button", "outcome"),
    [
        ("keep", IdleOutcome.KEEP),
        ("discard", IdleOutcome.DISCARD),
        ("discard_stop", IdleOutcome.DISCARD_AND_STOP),
        ("split", IdleOutcome.LOG_SEPARATELY),
    ],
)
def test_buttons_answer(qtbot, button: str, outcome: IdleOutcome) -> None:  # type: ignore[no-untyped-def]
    dialog = IdlePromptDialog(_span(), "Europe/Brussels")
    qtbot.addWidget(dialog)
    dialog.show()
    with qtbot.waitSignal(dialog.answered, timeout=1000) as blocker:
        qtbot.mouseClick(getattr(dialog, button), Qt.MouseButton.LeftButton)
    assert blocker.args == [outcome]
    assert dialog.result() == IdlePromptDialog.DialogCode.Accepted


def test_summary_text_and_live_update(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = IdlePromptDialog(_span(still=True), "Europe/Brussels")
    qtbot.addWidget(dialog)
    assert dialog.summary.text().startswith("No input for 0:12:30 and counting, since 14:05.")
    dialog.update_span(_span(900))
    assert dialog.summary.text().startswith("No input for 0:15:00, since 14:05.")
    dialog.update_span(_span(1800, IdleSource.SUSPEND))
    assert dialog.summary.text().startswith("The machine was asleep for 0:30:00, since 14:05.")


def test_escape_answers_nothing(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = IdlePromptDialog(_span(), "Europe/Brussels")
    qtbot.addWidget(dialog)
    dialog.show()
    with qtbot.assertNotEmitted(dialog.answered):
        qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert dialog.result() == IdlePromptDialog.DialogCode.Rejected
    assert not dialog.isModal()


def test_long_running_dialog(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = LongRunningDialog(12 * 3600 + 180, "02:00")
    qtbot.addWidget(dialog)
    dialog.show()
    with qtbot.waitSignal(dialog.stop_requested, timeout=1000):
        qtbot.mouseClick(dialog.stop, Qt.MouseButton.LeftButton)
    keep = LongRunningDialog(1, "02:00")
    qtbot.addWidget(keep)
    keep.show()
    with qtbot.assertNotEmitted(keep.stop_requested):
        qtbot.mouseClick(keep.keep, Qt.MouseButton.LeftButton)
    assert not keep.isModal()
