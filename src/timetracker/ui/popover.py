"""The popover — the main control surface (PRD-01 §9.2, FR-102, FR-201–FR-204, FR-206).

A frameless ``Qt.Popup`` anchored to the tray icon and clamped to the screen.
``Qt.Popup`` gives dismiss-on-click-outside and Esc for free. Two states share
one layout; widgets are shown or hidden per state rather than swapped.

Two pages: the **stopwatch** page (elapsed display, client/type selectors,
Start/Stop, note while running, started-at, today's total, an *Add Time*
button) and the **matrix** page (§9.3). The mode is remembered across open/close
*and* across launches (a setting), so an accidental Esc does not lose a
half-composed entry and a matrix-first user lands on the matrix with one click. The three "continue"
rows (FR-213, *could*) and the footer links (M5/M6) are absent.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from timetracker.core.duration import format_hm, format_hms
from timetracker.core.models import Dimension, Label
from timetracker.services.entry_service import EntryService
from timetracker.services.label_service import LabelService
from timetracker.services.settings_service import KEY_POPOVER_MODE, SettingsService
from timetracker.services.timer_service import TimerService, TimerState
from timetracker.ui.quickadd.matrix import Matrix

POPOVER_WIDTH = 380
MATRIX_WIDTH = 640
_NO_LABEL = "—"


class PopoverMode(Enum):
    STOPWATCH = "stopwatch"
    MATRIX = "matrix"


class LabelCombo(QComboBox):
    """Editable combo over one label dimension. Typing a new name creates it on commit."""

    def __init__(self, dimension: Dimension, labels: LabelService, parent: QWidget | None = None):
        super().__init__(parent)
        self._dim = dimension
        self._labels = labels
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setAccessibleName(dimension.name.title())
        self.reload()

    def reload(self, selected_id: int | None = None) -> None:
        current = selected_id if selected_id is not None else self.selected_id()
        self.blockSignals(True)
        self.clear()
        self.addItem(_NO_LABEL, None)
        for label in self._labels.list(self._dim):
            self.addItem(label.name, label.id)
        self.select(current)
        self.blockSignals(False)

    def select(self, label_id: int | None) -> None:
        index = self.findData(label_id) if label_id is not None else 0
        self.setCurrentIndex(index if index >= 0 else 0)

    def selected_id(self) -> int | None:
        """Id of the chosen label; ``None`` for the placeholder or unknown text."""
        text = self.currentText().strip()
        if not text or text == _NO_LABEL:
            return None
        index = self.findText(text, Qt.MatchFlag.MatchFixedString)
        if index > 0:
            data = self.itemData(index)
            return int(data) if data is not None else None
        return None

    def commit(self) -> int | None:
        """Resolve the text to a label id, creating the label if it is new (FR-401)."""
        text = self.currentText().strip()
        if not text or text == _NO_LABEL:
            self.select(None)
            return None
        known = self.selected_id()
        if known is not None:
            return known
        label: Label = self._labels.get_or_create(self._dim, text)
        self.reload(label.id)
        return label.id


class Popover(QWidget):
    dismissed = Signal()

    def __init__(
        self,
        timer: TimerService,
        labels: LabelService,
        entries: EntryService,
        settings: SettingsService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self._timer = timer
        self._labels = labels
        self._entries = entries
        self._settings = settings
        self._mode = _stored_mode(settings)
        self._last_anchor = QRect()
        self.setObjectName("popover")
        self.pages = QStackedWidget()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.pages)

        # -- stopwatch page --------------------------------------------------
        self.stopwatch_page = QWidget()

        self.elapsed = QLabel("0:00:00")
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono.setPointSize(28)
        mono.setWeight(QFont.Weight.DemiBold)
        self.elapsed.setFont(mono)
        self.elapsed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.elapsed.setAccessibleName("Elapsed time")

        self.client = LabelCombo(Dimension.CLIENT, labels)
        self.type = LabelCombo(Dimension.TYPE, labels)
        self.note = QLineEdit()
        self.note.setPlaceholderText("Note (optional)")
        self.note.setMaxLength(500)
        self.note.setAccessibleName("Note")

        self.start_stop = QPushButton("Start")
        self.start_stop.setDefault(True)
        self.start_stop.setMinimumHeight(36)

        self.add_time = QPushButton("Add Time…")
        self.add_time.setAccessibleName("Add time")
        self.add_time.setMinimumHeight(30)
        self.add_time.clicked.connect(lambda: self.set_mode(PopoverMode.MATRIX))

        self.started_at = QLabel("")
        self.started_at.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.today = QLabel("")
        self.today.setAlignment(Qt.AlignmentFlag.AlignCenter)

        form = QFormLayout()
        form.addRow("Client", self.client)
        form.addRow("Type", self.type)
        form.addRow("Note", self.note)

        footer = QHBoxLayout()
        footer.addWidget(self.started_at)
        footer.addStretch(1)
        footer.addWidget(self.today)

        root = QVBoxLayout(self.stopwatch_page)
        root.setContentsMargins(16, 12, 16, 12)
        root.addWidget(self.elapsed)
        root.addLayout(form)
        root.addWidget(self.start_stop)
        root.addWidget(self.add_time)
        root.addLayout(footer)
        self.pages.addWidget(self.stopwatch_page)

        # -- matrix page -----------------------------------------------------
        self.matrix_page = QWidget()
        self.back_button = QToolButton()
        self.back_button.setText("‹ Timer")
        self.back_button.setAccessibleName("Back to timer")
        self.back_button.setAutoRaise(True)
        self.back_button.clicked.connect(lambda: self.set_mode(PopoverMode.STOPWATCH))
        self.matrix = Matrix(entries, labels, settings)
        self.matrix.dismiss_requested.connect(self.hide)
        matrix_layout = QVBoxLayout(self.matrix_page)
        matrix_layout.setContentsMargins(8, 6, 8, 0)
        matrix_layout.setSpacing(0)
        matrix_layout.addWidget(self.back_button, 0, Qt.AlignmentFlag.AlignLeft)
        matrix_layout.addWidget(self.matrix)
        self.pages.addWidget(self.matrix_page)
        entries.entries_changed.connect(lambda _uuids: self._refresh_today())
        timer.stopped.connect(lambda _entry: self.matrix.refresh_totals())
        self._apply_mode()

        self.start_stop.clicked.connect(self._on_start_stop)
        self.client.activated.connect(self._on_label_edited)
        self.type.activated.connect(self._on_label_edited)
        self.client.lineEdit().editingFinished.connect(self._on_label_edited)
        self.type.lineEdit().editingFinished.connect(self._on_label_edited)
        self.note.editingFinished.connect(self._on_note_edited)

        timer.ticked.connect(self._on_tick)
        timer.state_changed.connect(self._apply_state)
        labels.labels_changed.connect(self._on_labels_changed)

        self._apply_state(timer.state)

    # -- mode ----------------------------------------------------------------

    @property
    def mode(self) -> PopoverMode:
        return self._mode

    def set_mode(self, mode: PopoverMode) -> None:
        if mode is self._mode:
            return
        self._mode = mode
        self._settings.set(KEY_POPOVER_MODE, mode.value)
        self._apply_mode()
        if self.isVisible():
            self.show_near(self._last_anchor)

    def _apply_mode(self) -> None:
        if self._mode is PopoverMode.MATRIX:
            self.pages.setCurrentWidget(self.matrix_page)
            self.setFixedWidth(MATRIX_WIDTH)
            self.matrix.prepare()
        else:
            self.pages.setCurrentWidget(self.stopwatch_page)
            self.setFixedWidth(POPOVER_WIDTH)
            self.start_stop.setFocus()

    # -- showing -------------------------------------------------------------

    def show_near(self, anchor: QRect) -> None:
        """Open next to *anchor* (tray icon geometry), clamped to that screen (§8.1)."""
        self._last_anchor = QRect(anchor)
        self.refresh()
        self.adjustSize()
        size = self.size()
        if anchor.isNull() or anchor.isEmpty():
            anchor = QRect(
                QGuiApplication.primaryScreen().availableGeometry().bottomRight(), anchor.size()
            )
        screen = QGuiApplication.screenAt(anchor.center()) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        # Prefer below the anchor; flip above if that would overflow.
        x = anchor.center().x() - size.width() // 2
        y = anchor.bottom() + 6
        if y + size.height() > avail.bottom():
            y = anchor.top() - size.height() - 6
        x = max(avail.left(), min(x, avail.right() - size.width()))
        y = max(avail.top(), min(y, avail.bottom() - size.height()))
        self.move(QPoint(x, y))
        self.show()
        self.raise_()
        self.activateWindow()
        if self._mode is PopoverMode.MATRIX:
            self.matrix.prepare()
        else:
            self.start_stop.setFocus()

    def refresh(self) -> None:
        """Re-read labels, defaults and totals; called before every show."""
        if self._timer.is_running:
            running = self._timer.running
            assert running is not None
            self.client.reload(running.client_id)
            self.type.reload(running.type_id)
            self.note.setText(running.note or "")
        else:
            client_id, type_id = self._timer.default_labels()
            self.client.reload(client_id)
            self.type.reload(type_id)
            self.note.clear()
        self._on_tick(self._timer.elapsed_seconds())
        self._refresh_today()

    def _refresh_today(self) -> None:
        self.today.setText(f"Today: {format_hm(self._timer.today_total_seconds())}")

    # -- state ---------------------------------------------------------------

    def _apply_state(self, state: TimerState) -> None:
        running = state is TimerState.RUNNING
        self.start_stop.setText("Stop" if running else "Start")
        self.start_stop.setAccessibleName("Stop timer" if running else "Start timer")
        self.note.setVisible(running)
        self.started_at.setVisible(running)
        self.elapsed.setEnabled(running)
        if running:
            self.started_at.setText(f"Started {self._timer.started_local_time()}")
        else:
            self.elapsed.setText("0:00:00")
        self._refresh_today()

    def _on_tick(self, seconds: int) -> None:
        self.elapsed.setText(format_hms(seconds))

    def _on_labels_changed(self, dimension: Dimension) -> None:
        combo = self.client if dimension is Dimension.CLIENT else self.type
        combo.reload()

    # -- actions -------------------------------------------------------------

    def _on_start_stop(self) -> None:
        if self._timer.is_running:
            self._timer.stop()
            self.hide()
        else:
            client_id = self.client.commit()
            type_id = self.type.commit()
            self._timer.start(client_id, type_id, None)
            self.refresh()

    def _on_label_edited(self, *_: object) -> None:
        if not self._timer.is_running:
            return
        self._timer.set_labels(self.client.commit(), self.type.commit())

    def _on_note_edited(self) -> None:
        if self._timer.is_running:
            self._timer.set_note(self.note.text().strip() or None)

    # -- events --------------------------------------------------------------

    def hideEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt override
        super().hideEvent(event)
        self.dismissed.emit()


def _stored_mode(settings: SettingsService) -> PopoverMode:
    try:
        return PopoverMode(str(settings.get(KEY_POPOVER_MODE)))
    except ValueError:
        return PopoverMode.STOPWATCH
