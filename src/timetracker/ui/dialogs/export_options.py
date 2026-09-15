"""Export options: rounding increment and scope (FR-604, FR-606), chosen at export time."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QWidget

from timetracker.core.rounding import INCREMENTS, RoundingScope


class ExportOptionsDialog(QDialog):
    def __init__(
        self,
        fmt: str,
        entry_count: int,
        rounding_minutes: int,
        scope: RoundingScope,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Export {fmt.upper()}")
        self.setModal(True)
        self.increment = QComboBox()
        for minutes in INCREMENTS:
            self.increment.addItem("none" if minutes == 0 else f"{minutes} minutes", minutes)
        pos = self.increment.findData(rounding_minutes)
        self.increment.setCurrentIndex(pos if pos >= 0 else 0)
        self.scope = QComboBox()
        for s in (RoundingScope.PER_GROUP, RoundingScope.PER_ENTRY):
            self.scope.addItem(s.display, s.value)
        self.scope.setCurrentIndex(max(0, self.scope.findData(scope.value)))
        self.increment.currentIndexChanged.connect(self._sync)

        form = QFormLayout(self)
        form.addRow(QLabel(f"{entry_count} entries in the current filter."))
        form.addRow("Round up to", self.increment)
        form.addRow("Rounding scope", self.scope)
        form.addRow(QLabel("Rounding is applied to the file only; stored records never change."))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Export…")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self._sync()

    def _sync(self) -> None:
        self.scope.setEnabled(int(self.increment.currentData()) > 0)

    def rounding_minutes(self) -> int:
        return int(self.increment.currentData())

    def rounding_scope(self) -> RoundingScope:
        return RoundingScope(str(self.scope.currentData()))
