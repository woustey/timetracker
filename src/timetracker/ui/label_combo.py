"""Editable combo over one label dimension; a typed name becomes a label on commit (FR-401/402)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QWidget

from timetracker.core.models import Dimension, Label
from timetracker.services.label_service import LabelService

NO_LABEL = "—"


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
        self.addItem(NO_LABEL, None)
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
        if not text or text == NO_LABEL:
            return None
        index = self.findText(text, Qt.MatchFlag.MatchFixedString)
        if index > 0:
            data = self.itemData(index)
            return int(data) if data is not None else None
        return None

    def commit(self) -> int | None:
        """Resolve the text to a label id, creating the label if it is new (FR-401)."""
        text = self.currentText().strip()
        if not text or text == NO_LABEL:
            self.select(None)
            return None
        known = self.selected_id()
        if known is not None:
            return known
        label: Label = self._labels.get_or_create(self._dim, text)
        self.reload(label.id)
        return label.id
