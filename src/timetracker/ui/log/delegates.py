"""Inline editors for the log table (PRD-02 §8.3, FR-505)."""

from __future__ import annotations

from datetime import date, time
from typing import Any

from PySide6.QtCore import QDate, QModelIndex, QPersistentModelIndex, Qt, QTime
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QLineEdit,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTimeEdit,
    QWidget,
)

from timetracker.core.duration import format_hms, parse_duration
from timetracker.core.models import Dimension
from timetracker.services.label_service import LabelService


class DurationDelegate(QStyledItemDelegate):
    """Accepts the §5.5 grammar; an unparseable value leaves the entry unchanged."""

    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QWidget:  # noqa: N802
        editor = QLineEdit(parent)
        editor.setPlaceholderText("e.g. 1:30, 1h15, 45")
        return editor

    def setEditorData(self, editor: QWidget, index: QModelIndex | QPersistentModelIndex) -> None:  # noqa: N802
        assert isinstance(editor, QLineEdit)
        editor.setText(format_hms(int(index.data(Qt.ItemDataRole.EditRole))))
        editor.selectAll()

    def setModelData(
        self, editor: QWidget, model: Any, index: QModelIndex | QPersistentModelIndex
    ) -> None:  # noqa: N802
        assert isinstance(editor, QLineEdit)
        text = editor.text().strip()
        parsed = parse_duration(text)
        if parsed is None and text.count(":") == 2:
            h, m, s = (int(p) for p in text.split(":"))
            parsed = h * 3600 + m * 60 + s
        if parsed is not None:
            model.setData(index, parsed, Qt.ItemDataRole.EditRole)


class DateDelegate(QStyledItemDelegate):
    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QWidget:  # noqa: N802
        editor = QDateEdit(parent)
        editor.setCalendarPopup(True)
        editor.setDisplayFormat("ddd d MMM yyyy")
        return editor

    def setEditorData(self, editor: QWidget, index: QModelIndex | QPersistentModelIndex) -> None:  # noqa: N802
        assert isinstance(editor, QDateEdit)
        d = index.data(Qt.ItemDataRole.EditRole)
        assert isinstance(d, date)
        editor.setDate(QDate(d.year, d.month, d.day))

    def setModelData(
        self, editor: QWidget, model: Any, index: QModelIndex | QPersistentModelIndex
    ) -> None:  # noqa: N802
        assert isinstance(editor, QDateEdit)
        q = editor.date()
        model.setData(index, date(q.year(), q.month(), q.day()), Qt.ItemDataRole.EditRole)


class TimeDelegate(QStyledItemDelegate):
    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QWidget:  # noqa: N802
        editor = QTimeEdit(parent)
        editor.setDisplayFormat("HH:mm")
        return editor

    def setEditorData(self, editor: QWidget, index: QModelIndex | QPersistentModelIndex) -> None:  # noqa: N802
        assert isinstance(editor, QTimeEdit)
        t = index.data(Qt.ItemDataRole.EditRole)
        assert isinstance(t, time)
        editor.setTime(QTime(t.hour, t.minute))

    def setModelData(
        self, editor: QWidget, model: Any, index: QModelIndex | QPersistentModelIndex
    ) -> None:  # noqa: N802
        assert isinstance(editor, QTimeEdit)
        q = editor.time()
        model.setData(index, time(q.hour(), q.minute()), Qt.ItemDataRole.EditRole)


class LabelDelegate(QStyledItemDelegate):
    """Combo over one dimension; the first item is "—" (unlabelled)."""

    def __init__(self, dimension: Dimension, labels: LabelService, parent: QWidget | None = None):
        super().__init__(parent)
        self._dim = dimension
        self._labels = labels

    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QWidget:  # noqa: N802
        combo = QComboBox(parent)
        combo.addItem("—", None)
        for label in self._labels.list(self._dim):
            combo.addItem(label.name, label.id)
        return combo

    def setEditorData(self, editor: QWidget, index: QModelIndex | QPersistentModelIndex) -> None:  # noqa: N802
        assert isinstance(editor, QComboBox)
        current = index.data(Qt.ItemDataRole.EditRole)
        pos = editor.findData(current) if current is not None else 0
        editor.setCurrentIndex(pos if pos >= 0 else 0)

    def setModelData(
        self, editor: QWidget, model: Any, index: QModelIndex | QPersistentModelIndex
    ) -> None:  # noqa: N802
        assert isinstance(editor, QComboBox)
        model.setData(index, editor.currentData(), Qt.ItemDataRole.EditRole)
