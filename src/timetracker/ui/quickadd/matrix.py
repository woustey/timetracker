"""The Add Time matrix — a composer for exactly one pending entry (PRD-01 §9.3, FR-301–FR-315).

Layout per §9.3.1: a header (title · Pending total), four columns (Time ·
Category · Client · Note) with a *Custom…* cell at the foot of the first three,
and a footer (Today's total · Clear · Add).

- Time is additive: click adds, Shift-click subtracts, the total never goes
  below zero (FR-303/305). The pending total is the single source of truth and
  is click-to-edit.
- Category and Client are radio columns via ``QButtonGroup`` (FR-306/307).
- Custom… swaps the cell for a line edit; Enter commits, Esc reverts (FR-304/309).
  A label typed there becomes a permanent chip (FR-401); a near-duplicate offers
  the existing label first (FR-403).
- Add is enabled only when pending > 0 and mandatory labels are set; its
  tooltip names the unmet condition (FR-310).
- After commit: toast with Undo, pending → 0, note cleared, labels retained
  (FR-311/312).
- Keyboard map per §9.3.5, handled in :meth:`keyPressEvent` so it never leaks
  beyond this widget.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QAction, QFont, QKeyEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from timetracker.core.duration import format_hm, parse_duration
from timetracker.core.models import NOTE_MAX_CHARS, Dimension, Entry, Label
from timetracker.services.entry_service import EntryService
from timetracker.services.label_service import LabelService
from timetracker.services.settings_service import SettingsService
from timetracker.ui.quickadd.chip import CHIP_STYLE, Chip, ChipKind
from timetracker.ui.quickadd.toast import Toast

TIME_CHIPS: tuple[tuple[str, int], ...] = (
    ("+6min", 6 * 60),
    ("+15min", 15 * 60),
    ("+30min", 30 * 60),
    ("+45min", 45 * 60),
)
MAX_KEYED_CHIPS = 5
TYPE_KEYS = (Qt.Key.Key_Q, Qt.Key.Key_W, Qt.Key.Key_E, Qt.Key.Key_R, Qt.Key.Key_T)
CLIENT_KEYS = (Qt.Key.Key_A, Qt.Key.Key_S, Qt.Key.Key_D, Qt.Key.Key_F, Qt.Key.Key_G)
DIGIT_KEYS = (Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_3, Qt.Key.Key_4, Qt.Key.Key_5)
# US-layout shifted digits, so Shift+1..5 works there too.
SHIFTED_DIGIT_KEYS = (
    Qt.Key.Key_Exclam,
    Qt.Key.Key_At,
    Qt.Key.Key_NumberSign,
    Qt.Key.Key_Dollar,
    Qt.Key.Key_Percent,
)


class CustomEdit(QLineEdit):
    """Inline editor for a Custom… cell. Consumes Enter and Esc so the popup does not."""

    committed = Signal(str)
    cancelled = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt override
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.committed.emit(self.text())
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt override
        super().focusOutEvent(event)  # type: ignore[arg-type]
        # editingFinished without text reverts (§8.2); with text it is left for Enter.
        if not self.text().strip():
            self.cancelled.emit()


class CustomCell(QStackedWidget):
    """``Custom…`` button ⇄ line edit."""

    committed = Signal(str)

    def __init__(self, placeholder: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.button = QToolButton()
        self.button.setText("Custom…")
        self.button.setAccessibleName(f"Custom {placeholder}")
        self.button.setProperty("chip", True)
        self.button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.button.setMinimumHeight(30)
        self.button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.button.clicked.connect(self.open_editor)
        self.edit = CustomEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setAccessibleName(f"Custom {placeholder}")
        self.edit.committed.connect(self._on_commit)
        self.edit.cancelled.connect(self.close_editor)
        self.addWidget(self.button)
        self.addWidget(self.edit)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    @property
    def is_editing(self) -> bool:
        return self.currentWidget() is self.edit

    def open_editor(self) -> None:
        self.edit.clear()
        self.set_error(False)
        self.setCurrentWidget(self.edit)
        self.edit.setFocus()

    def close_editor(self) -> None:
        self.setCurrentWidget(self.button)
        self.set_error(False)

    def set_error(self, on: bool) -> None:
        self.edit.setProperty("error", on)
        self.edit.style().unpolish(self.edit)
        self.edit.style().polish(self.edit)

    def _on_commit(self, text: str) -> None:
        if text.strip():
            self.committed.emit(text)
        else:
            self.close_editor()


class PendingTotal(QStackedWidget):
    """``Pending: 0:30`` label that becomes an editor on click (§9.3.2)."""

    edited = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = QLabel("Pending: 0:00")
        self.label.setAccessibleName("Pending total")
        self.label.setCursor(Qt.CursorShape.IBeamCursor)
        self.label.setToolTip("Click to edit")
        font = QFont(self.label.font())
        font.setPointSize(font.pointSize() + 3)
        font.setBold(True)
        self.label.setFont(font)
        self.edit = CustomEdit()
        self.edit.setPlaceholderText("e.g. 1:30, 1h15, 45")
        self.edit.setAccessibleName("Pending total")
        self.edit.committed.connect(self._on_commit)
        self.edit.cancelled.connect(lambda: self.setCurrentWidget(self.label))
        self.addWidget(self.label)
        self.addWidget(self.edit)
        self._seconds = 0
        self.label.installEventFilter(self)

    def set_seconds(self, seconds: int) -> None:
        self._seconds = seconds
        self.label.setText(f"Pending: {format_hm(seconds)}")

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt override
        if watched is self.label and event.type() == QEvent.Type.MouseButtonRelease:
            self.edit.setText(format_hm(self._seconds))
            self.setCurrentWidget(self.edit)
            self.edit.setFocus()
            self.edit.selectAll()
            return True
        return super().eventFilter(watched, event)

    def _on_commit(self, text: str) -> None:
        parsed = parse_duration(text)
        if parsed is None:
            self.edit.setProperty("error", True)
            self.edit.style().unpolish(self.edit)
            self.edit.style().polish(self.edit)
            return
        self.setCurrentWidget(self.label)
        self.edited.emit(parsed)


class Matrix(QWidget):
    committed = Signal(object)  # Entry
    dismiss_requested = Signal()

    def __init__(
        self,
        entries: EntryService,
        labels: LabelService,
        settings: SettingsService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._entries = entries
        self._labels = labels
        self._settings = settings
        self._pending = 0
        self._time_chips: list[Chip] = []
        self._label_chips: dict[Dimension, list[Chip]] = {Dimension.TYPE: [], Dimension.CLIENT: []}
        self._groups: dict[Dimension, QButtonGroup] = {}
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(CHIP_STYLE + '\nQLineEdit[error="true"] { border: 1px solid #e5484d; }')

        # -- header ----------------------------------------------------------
        self.title = QLabel("Add time")
        title_font = QFont(self.title.font())
        title_font.setPointSize(title_font.pointSize() + 3)
        title_font.setBold(True)
        self.title.setFont(title_font)
        self.pending_total = PendingTotal()
        self.pending_total.edited.connect(self._set_pending_from_edit)
        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.pending_total)

        # -- grid ------------------------------------------------------------
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(6)
        for col, name in enumerate(("Time", "Category", "Client", "Note")):
            head = QLabel(name)
            head.setStyleSheet("font-weight: 600; color: palette(mid);")
            self.grid.addWidget(head, 0, col)
        for col in range(4):
            self.grid.setColumnStretch(col, 1)

        self.custom_time = CustomCell("duration")
        self.custom_time.committed.connect(self._on_custom_time)
        self.custom_type = CustomCell("category")
        self.custom_type.committed.connect(lambda t: self._on_custom_label(Dimension.TYPE, t))
        self.custom_client = CustomCell("client")
        self.custom_client.committed.connect(lambda t: self._on_custom_label(Dimension.CLIENT, t))

        self.note = QTextEdit()
        self.note.setPlaceholderText("Note (optional)")
        self.note.setAccessibleName("Note")
        self.note.setTabChangesFocus(True)
        self.note.setAcceptRichText(False)
        self.note.textChanged.connect(self._on_note_changed)
        self.note.installEventFilter(self)
        self.note_warning = QLabel("")
        self.note_warning.setStyleSheet("color: #e5484d;")
        self.note_warning.hide()

        for chip_text, seconds in TIME_CHIPS:
            chip = Chip(chip_text, ChipKind.TIME, value=seconds)
            chip.activated.connect(
                lambda shift, s=seconds, c=chip: self._add_time(s, subtract=shift, chip=c)
            )
            self._time_chips.append(chip)
        for dim in (Dimension.TYPE, Dimension.CLIENT):
            group = QButtonGroup(self)
            group.setExclusive(True)
            group.idToggled.connect(lambda *_: self._update_add_enabled())
            self._groups[dim] = group
        self._rebuild_labels(Dimension.TYPE)
        self._rebuild_labels(Dimension.CLIENT)
        self._relayout()

        # -- footer ----------------------------------------------------------
        self.today = QLabel("")
        self.today.setAccessibleName("Today's total")
        self.clear_button = QPushButton("Clear")
        self.clear_button.setAccessibleName("Clear pending time")
        self.clear_button.clicked.connect(self.clear)
        self.add_button = QPushButton("Add")
        self.add_button.setAccessibleName("Add entry")
        self.add_button.setMinimumHeight(34)
        self.add_button.clicked.connect(self.commit)
        footer = QHBoxLayout()
        footer.addWidget(self.today)
        footer.addStretch(1)
        footer.addWidget(self.clear_button)
        footer.addWidget(self.add_button)

        self.toast = Toast(self)
        self.toast.undo_requested.connect(self.undo)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.addLayout(header)
        root.addLayout(self.grid)
        root.addWidget(self.note_warning)
        root.addLayout(footer)

        labels.labels_changed.connect(self._on_labels_changed)
        entries.entries_changed.connect(lambda _uuids: self.refresh_totals())
        settings.setting_changed.connect(lambda _key: self._update_add_enabled())

        self.setTabOrder(self, self.note)
        self._update_pending_display()
        self.refresh_totals()

    # -- public state --------------------------------------------------------

    @property
    def pending_seconds(self) -> int:
        return self._pending

    def selected(self, dimension: Dimension) -> int | None:
        button = self._groups[dimension].checkedButton()
        if button is None:
            return None
        chip = button
        assert isinstance(chip, Chip)
        return int(chip.value) if chip.value is not None else None

    def select(self, dimension: Dimension, label_id: int | None) -> None:
        group = self._groups[dimension]
        if label_id is None:
            checked = group.checkedButton()
            if checked is not None:
                group.setExclusive(False)
                checked.setChecked(False)
                group.setExclusive(True)
            self._update_add_enabled()
            return
        for chip in self._label_chips[dimension]:
            if chip.value == label_id:
                chip.setChecked(True)
                break
        self._update_add_enabled()

    def chips(self, dimension: Dimension) -> list[Chip]:
        return list(self._label_chips[dimension])

    @property
    def time_chips(self) -> list[Chip]:
        return list(self._time_chips)

    def prepare(self) -> None:
        """Called before the matrix is shown: prefill MRU labels if nothing is selected (FR-312)."""
        if self.selected(Dimension.CLIENT) is None and self.selected(Dimension.TYPE) is None:
            client_id, type_id = self._entries.default_labels()
            self.select(Dimension.CLIENT, client_id)
            self.select(Dimension.TYPE, type_id)
        self.refresh_totals()
        self.setFocus()

    def refresh_totals(self) -> None:
        self.today.setText(f"Today: {format_hm(self._entries.today_total_seconds())}")

    # -- time ----------------------------------------------------------------

    def _add_time(self, seconds: int, *, subtract: bool = False, chip: Chip | None = None) -> None:
        if subtract:
            delta = -min(seconds, self._pending)  # never below zero (FR-305)
        else:
            delta = seconds
        self._pending += delta
        if chip is not None:
            chip.set_count(chip.count + (-1 if subtract else 1))
        if self._pending == 0:
            for c in self._time_chips:
                c.set_count(0)  # nothing is contributing any more
        self._update_pending_display()

    def _set_pending_from_edit(self, seconds: int) -> None:
        self._pending = max(0, seconds)
        for chip in self._time_chips:
            chip.set_count(0)  # no longer attributable to chips
        self._update_pending_display()

    def clear(self) -> None:
        """One action clears the pending total and note; labels stay (FR-305, FR-312)."""
        self._pending = 0
        for chip in self._time_chips:
            chip.set_count(0)
        self.note.clear()
        self._update_pending_display()

    def _on_custom_time(self, text: str) -> None:
        parsed = parse_duration(text)
        if parsed is None:
            self.custom_time.set_error(True)  # unparseable: field in error, total unchanged
            return
        self._add_time(parsed)
        self.custom_time.close_editor()
        self.setFocus()

    def _update_pending_display(self) -> None:
        self.pending_total.set_seconds(self._pending)
        self._update_add_enabled()

    # -- labels --------------------------------------------------------------

    def _rebuild_labels(self, dimension: Dimension) -> None:
        keep = self.selected(dimension)
        group = self._groups[dimension]
        for chip in self._label_chips[dimension]:
            group.removeButton(chip)
            chip.setParent(None)
            chip.deleteLater()
        chips: list[Chip] = []
        for label in self._labels.list(dimension):
            chip = Chip(label.name, ChipKind.LABEL, value=label.id)
            group.addButton(chip)
            chips.append(chip)
        self._label_chips[dimension] = chips
        if keep is not None:
            self.select(dimension, keep)

    def _relayout(self) -> None:
        """Lay out chips row by row; the note spans the full height of the chip rows."""
        rows = max(
            len(self._time_chips),
            len(self._label_chips[Dimension.TYPE]),
            len(self._label_chips[Dimension.CLIENT]),
        )
        # Remove everything below the header row.
        for i in reversed(range(self.grid.count())):
            item = self.grid.itemAt(i)
            w = item.widget() if item is not None else None
            if w is None:
                continue
            r, _c, _rs, _cs = self.grid.getItemPosition(i)
            if r > 0:
                self.grid.removeWidget(w)
                w.hide()
        columns = (
            (self._time_chips, self.custom_time),
            (self._label_chips[Dimension.TYPE], self.custom_type),
            (self._label_chips[Dimension.CLIENT], self.custom_client),
        )
        for col, (chips, custom) in enumerate(columns):
            for row, chip in enumerate(chips, start=1):
                self.grid.addWidget(chip, row, col)
                chip.show()
            self.grid.addWidget(custom, rows + 1, col)
            custom.show()
        self.grid.addWidget(self.note, 1, 3, rows + 1, 1)
        self.note.show()

    def _on_labels_changed(self, dimension: Dimension) -> None:
        self._rebuild_labels(dimension)
        self._relayout()
        self._update_add_enabled()

    def _on_custom_label(self, dimension: Dimension, text: str) -> None:
        cell = self.custom_type if dimension is Dimension.TYPE else self.custom_client
        existing = self._labels.exact(dimension, text)
        if existing is None:
            candidates = self._labels.near_duplicates(dimension, text)
            if candidates:
                self._offer_near_duplicate(dimension, text, candidates, cell)
                return
        self._apply_custom_label(dimension, text, cell)

    def _apply_custom_label(self, dimension: Dimension, text: str, cell: CustomCell) -> None:
        label = self._labels.get_or_create(dimension, text)  # emits labels_changed → rebuild
        cell.close_editor()
        self.select(dimension, label.id)
        self.setFocus()

    def _offer_near_duplicate(
        self, dimension: Dimension, typed: str, candidates: list[Label], cell: CustomCell
    ) -> None:
        """FR-403: offer the existing label; the user may override with one click."""
        menu = QMenu(self)
        menu.setAccessibleName("Similar label found")
        for label in candidates[:3]:
            action = QAction(f"Use “{label.name}”", menu)
            action.triggered.connect(
                lambda _=False, lab=label: self._use_existing(dimension, lab, cell)
            )
            menu.addAction(action)
        menu.addSeparator()
        create = QAction(f"Create “{' '.join(typed.split())}”", menu)
        create.triggered.connect(lambda: self._apply_custom_label(dimension, typed, cell))
        menu.addAction(create)
        menu.setDefaultAction(menu.actions()[0])
        self._near_dup_menu = menu  # test hook; also keeps it alive
        menu.popup(cell.mapToGlobal(cell.rect().bottomLeft()))
        menu.setActiveAction(menu.actions()[0])

    def _use_existing(self, dimension: Dimension, label: Label, cell: CustomCell) -> None:
        cell.close_editor()
        self.select(dimension, label.id)
        self.setFocus()

    # -- note ----------------------------------------------------------------

    def note_text(self) -> str:
        return self.note.toPlainText().strip()

    def _on_note_changed(self) -> None:
        text = self.note.toPlainText()
        if len(text) > NOTE_MAX_CHARS:
            cursor = self.note.textCursor()
            self.note.blockSignals(True)
            self.note.setPlainText(text[:NOTE_MAX_CHARS])
            self.note.blockSignals(False)
            cursor.setPosition(min(cursor.position(), NOTE_MAX_CHARS))
            self.note.setTextCursor(cursor)
            self.note_warning.setText(f"Note truncated to {NOTE_MAX_CHARS} characters.")
            self.note_warning.show()
        elif self.note_warning.isVisible() and len(text) < NOTE_MAX_CHARS:
            self.note_warning.hide()

    # -- commit / undo -------------------------------------------------------

    def unmet_condition(self) -> str | None:
        if self._pending <= 0:
            return "Add some time first"
        if self._settings.mandatory_type and self.selected(Dimension.TYPE) is None:
            return "Choose a category"
        if self._settings.mandatory_client and self.selected(Dimension.CLIENT) is None:
            return "Choose a client"
        return None

    def _update_add_enabled(self) -> None:
        reason = self.unmet_condition()
        self.add_button.setEnabled(reason is None)
        self.add_button.setToolTip(reason or "Add this entry (Enter)")

    def commit(self) -> Entry | None:
        if self.unmet_condition() is not None:
            return None
        client_id = self.selected(Dimension.CLIENT)
        type_id = self.selected(Dimension.TYPE)
        entry = self._entries.add_quick(self._pending, client_id, type_id, self.note_text())
        summary = " · ".join(
            part
            for part in (
                format_hm(entry.duration_seconds),
                self._name(Dimension.TYPE, type_id),
                self._name(Dimension.CLIENT, client_id),
            )
            if part
        )
        self.clear()  # pending → 0, note cleared, labels retained (FR-312)
        self.toast.show_message(f"{summary} — added")
        self._place_toast()
        self.setFocus()
        self.committed.emit(entry)
        return entry

    def undo(self) -> Entry | None:
        removed = self._entries.undo_last()
        if removed is not None:
            self.toast.show_message("Entry removed", undoable=False)
            self._place_toast()
        return removed

    def _name(self, dimension: Dimension, label_id: int | None) -> str | None:
        return None if label_id is None else self._labels.get(dimension, label_id).name

    def _place_toast(self) -> None:
        self.toast.adjustSize()
        width = min(self.width() - 32, max(self.toast.sizeHint().width(), 260))
        self.toast.setFixedWidth(width)
        x = (self.width() - width) // 2
        y = self.height() - self.toast.height() - 56
        self.toast.move(x, max(0, y))

    # -- keyboard (§9.3.5) ---------------------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt override
        if watched is self.note and event.type() == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False  # Shift+Enter: newline in the note
                self.commit()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.dismiss_requested.emit()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt override
        key = event.key()
        mods = event.modifiers()
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not shift:
            self.commit()
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self.dismiss_requested.emit()
            event.accept()
            return
        if ctrl and key == Qt.Key.Key_Z:
            self.undo()
            event.accept()
            return
        if ctrl:
            super().keyPressEvent(event)
            return

        digit = _digit_index(event)
        if digit is not None:
            # Physical top-row key + Shift subtracts (§9.3.5). Resolved from the
            # native key so it holds on AZERTY, where the digits themselves are shifted.
            self._activate_time(digit, subtract=shift)
            event.accept()
            return
        if key in TYPE_KEYS:
            self._activate_label(Dimension.TYPE, TYPE_KEYS.index(key))
            event.accept()
            return
        if key in CLIENT_KEYS:
            self._activate_label(Dimension.CLIENT, CLIENT_KEYS.index(key))
            event.accept()
            return
        super().keyPressEvent(event)

    def _activate_time(self, index: int, *, subtract: bool) -> None:
        if index < len(self._time_chips):
            chip = self._time_chips[index]
            self._add_time(int(chip.value), subtract=subtract, chip=chip)  # type: ignore[arg-type]
        elif index == len(self._time_chips) and not subtract:
            self.custom_time.open_editor()

    def _activate_label(self, dimension: Dimension, index: int) -> None:
        chips = self._label_chips[dimension]
        if index < len(chips):
            chips[index].setChecked(True)
            self._update_add_enabled()
        elif index == len(chips):
            cell = self.custom_type if dimension is Dimension.TYPE else self.custom_client
            cell.open_editor()


_MAC_DIGIT_KEYCODES = (18, 19, 20, 21, 23)  # physical 1..5 on Apple keyboards
_X11_DIGIT_SCANCODES = (10, 11, 12, 13, 14)  # evdev keycodes + 8 for the top row


def _digit_index(event: QKeyEvent) -> int | None:
    """0..4 for the physical top-row keys 1..5, independent of layout; else ``None``."""
    if sys.platform == "win32":
        vk = event.nativeVirtualKey()
        if 0x31 <= vk <= 0x35:
            return vk - 0x31
    elif sys.platform == "darwin":
        code = event.nativeVirtualKey()
        if code in _MAC_DIGIT_KEYCODES:
            return _MAC_DIGIT_KEYCODES.index(code)
    else:
        scan = event.nativeScanCode()
        if scan in _X11_DIGIT_SCANCODES:
            return _X11_DIGIT_SCANCODES.index(scan)
    # Synthetic events (tests) and unknown platforms: fall back to the logical key.
    key = event.key()
    if key in DIGIT_KEYS:
        return DIGIT_KEYS.index(key)  # type: ignore[arg-type]
    if key in SHIFTED_DIGIT_KEYS:
        return SHIFTED_DIGIT_KEYS.index(key)  # type: ignore[arg-type]
    text = event.text()
    if len(text) == 1 and text in "12345":
        return int(text) - 1
    return None
