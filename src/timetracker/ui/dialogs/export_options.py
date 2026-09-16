"""Export options: rounding increment and scope (FR-604, FR-606), the column set
(FR-603) and the destination folder — chosen at export time, and savable as a
named preset (FR-608) that the log's *Export* menu re-runs in one click."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
)

from timetracker.core.errors import ValidationError
from timetracker.core.export_presets import ExportPreset
from timetracker.core.rounding import INCREMENTS, RoundingScope
from timetracker.services.export_service import COLUMNS


class ExportOptionsDialog(QDialog):
    preset_saved = Signal(object)  # ExportPreset — the window persists it while the dialog is open

    def __init__(
        self,
        fmt: str,
        entry_count: int,
        rounding_minutes: int,
        scope: RoundingScope,
        parent: QWidget | None = None,
        *,
        columns: tuple[str, ...] = COLUMNS,
        folder: Path | None = None,
        preset_names: list[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self._fmt = fmt
        self._preset_names = list(preset_names or [])
        self.saved_preset: ExportPreset | None = None
        self.setWindowTitle(f"Export {fmt.upper()}")
        self.setModal(True)
        self.increment = QComboBox()
        self.increment.setAccessibleName("Round up to")
        for minutes in INCREMENTS:
            self.increment.addItem("none" if minutes == 0 else f"{minutes} minutes", minutes)
        pos = self.increment.findData(rounding_minutes)
        self.increment.setCurrentIndex(pos if pos >= 0 else 0)
        self.scope = QComboBox()
        self.scope.setAccessibleName("Rounding scope")
        for s in (RoundingScope.PER_GROUP, RoundingScope.PER_ENTRY):
            self.scope.addItem(s.display, s.value)
        self.scope.setCurrentIndex(max(0, self.scope.findData(scope.value)))
        self.increment.currentIndexChanged.connect(self._sync)

        form = QFormLayout(self)
        form.addRow(QLabel(f"{entry_count} entries in the current filter."))
        form.addRow("Round up to", self.increment)
        form.addRow("Rounding scope", self.scope)

        # FR-603: column selection.
        box = QGroupBox("Columns")
        grid = QGridLayout(box)
        self.column_boxes: dict[str, QCheckBox] = {}
        for i, name in enumerate(COLUMNS):
            cb = QCheckBox(name)
            cb.setChecked(name in columns)
            cb.toggled.connect(self._sync)
            self.column_boxes[name] = cb
            grid.addWidget(cb, i // 3, i % 3)
        form.addRow(box)

        self.folder = QLineEdit(str(folder) if folder is not None else "")
        self.folder.setAccessibleName("Export folder")
        self.folder.setReadOnly(True)
        browse = QPushButton("Choose…")
        browse.clicked.connect(self._choose_folder)
        row = QHBoxLayout()
        row.addWidget(self.folder, 1)
        row.addWidget(browse)
        form.addRow("Folder", row)

        form.addRow(QLabel("Rounding is applied to the file only; stored records never change."))
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Export…")
        self.save_preset_button = self.buttons.addButton(
            "Save as preset…", QDialogButtonBox.ButtonRole.ActionRole
        )
        self.save_preset_button.clicked.connect(self._save_preset)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self._sync()

    # -- values --------------------------------------------------------------

    def _sync(self, *_: object) -> None:
        self.scope.setEnabled(int(self.increment.currentData()) > 0)
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setEnabled(bool(self.columns()))
        self.save_preset_button.setEnabled(bool(self.columns()))

    def rounding_minutes(self) -> int:
        return int(self.increment.currentData())

    def rounding_scope(self) -> RoundingScope:
        return RoundingScope(str(self.scope.currentData()))

    def columns(self) -> tuple[str, ...]:
        return tuple(c for c in COLUMNS if self.column_boxes[c].isChecked())

    def folder_path(self) -> Path | None:
        text = self.folder.text().strip()
        return Path(text) if text else None

    def preset(self, name: str) -> ExportPreset:
        return ExportPreset(
            name=name.strip(),
            fmt=self._fmt,
            columns=self.columns(),
            rounding_minutes=self.rounding_minutes(),
            scope=self.rounding_scope(),
            folder=self.folder.text().strip() or None,
        )

    # -- actions -------------------------------------------------------------

    def _choose_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Export folder", self.folder.text())
        if chosen:
            self.folder.setText(chosen)

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Save as preset", "Preset name:")
        if not ok:
            return
        self.save_preset_named(name)

    def save_preset_named(self, name: str) -> bool:
        """Validate and stash the preset for the caller; ``False`` (with a message) if invalid."""
        preset = self.preset(name)
        try:
            preset.validate(COLUMNS)
        except ValidationError as exc:
            QMessageBox.warning(self, "Save as preset", str(exc))
            return False
        if preset.name.casefold() in (n.casefold() for n in self._preset_names):
            answer = QMessageBox.question(
                self,
                "Save as preset",
                f"A preset named “{preset.name}” exists. Replace it?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        self.saved_preset = preset
        self.preset_saved.emit(preset)
        return True
