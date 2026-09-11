"""Labels for the UI: list per dimension, and the FR-401/402 "typed once, a chip forever" path."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from timetracker.core.labels import near_duplicates
from timetracker.core.models import Dimension, Label
from timetracker.data.label_repo import LabelRepo


class LabelService(QObject):
    labels_changed = Signal(object)  # Dimension

    def __init__(self, clients: LabelRepo, types: LabelRepo, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._repos = {Dimension.CLIENT: clients, Dimension.TYPE: types}

    def list(self, dimension: Dimension) -> list[Label]:
        return self._repos[dimension].list_all()

    def get(self, dimension: Dimension, label_id: int) -> Label:
        return self._repos[dimension].get(label_id)

    def exact(self, dimension: Dimension, name: str) -> Label | None:
        return self._repos[dimension].find_by_name(name)

    def near_duplicates(self, dimension: Dimension, name: str) -> list[Label]:
        """Existing labels within edit distance 2 of *name* (FR-403), closest first."""
        return near_duplicates(name, self._repos[dimension].list_all())

    def get_or_create(self, dimension: Dimension, name: str) -> Label:
        repo = self._repos[dimension]
        before = repo.count(include_archived=True)
        label = repo.get_or_create(name)
        if repo.count(include_archived=True) != before:
            self.labels_changed.emit(dimension)
        return label

    def ensure_seed_types(self) -> None:
        if self._repos[Dimension.TYPE].ensure_seed():
            self.labels_changed.emit(Dimension.TYPE)
