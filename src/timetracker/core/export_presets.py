"""Named export presets (FR-608, v1.1): column set + rounding + scope + destination folder.

A preset is what the Export dialog was last told, given a name so it can be
re-run in one click from the log's *Export* menu. It never stores a filter —
the current log view is always what gets exported (FR-601). Stored as one JSON
list in the ``setting`` table (``export.presets``); this module is the only
place that knows the shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from timetracker.core.errors import ValidationError
from timetracker.core.rounding import INCREMENTS, RoundingScope

FORMATS = ("csv", "xlsx")
NAME_MAX_CHARS = 60


@dataclass(frozen=True, slots=True)
class ExportPreset:
    name: str
    fmt: str  # "csv" | "xlsx"
    columns: tuple[str, ...]
    rounding_minutes: int = 0
    scope: RoundingScope = RoundingScope.PER_GROUP
    folder: str | None = None  # None → the default export folder setting

    def validate(self, all_columns: tuple[str, ...]) -> None:
        name = self.name.strip()
        if not name:
            raise ValidationError("preset name is empty")
        if len(name) > NAME_MAX_CHARS:
            raise ValidationError(f"preset name exceeds {NAME_MAX_CHARS} characters")
        if self.fmt not in FORMATS:
            raise ValidationError(f"unknown export format {self.fmt!r}")
        if not self.columns:
            raise ValidationError("a preset needs at least one column")
        unknown = [c for c in self.columns if c not in all_columns]
        if unknown:
            raise ValidationError(f"unknown export column(s): {', '.join(unknown)}")
        if self.rounding_minutes not in INCREMENTS:
            raise ValidationError(f"rounding must be one of {INCREMENTS}")

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "fmt": self.fmt,
            "columns": list(self.columns),
            "rounding_minutes": self.rounding_minutes,
            "scope": self.scope.value,
            "folder": self.folder,
        }

    @classmethod
    def from_json(cls, raw: Any) -> ExportPreset:
        """Lenient: a malformed entry raises ``ValidationError`` and the caller skips it."""
        if not isinstance(raw, dict):
            raise ValidationError("preset is not an object")
        try:
            scope = RoundingScope(str(raw.get("scope", RoundingScope.PER_GROUP.value)))
        except ValueError:
            scope = RoundingScope.PER_GROUP
        try:
            rounding = int(raw.get("rounding_minutes", 0))
        except (TypeError, ValueError):
            rounding = 0
        columns = raw.get("columns")
        if not isinstance(columns, list):
            raise ValidationError("preset has no column list")
        folder = raw.get("folder")
        return cls(
            name=str(raw.get("name", "")).strip(),
            fmt=str(raw.get("fmt", "csv")),
            columns=tuple(str(c) for c in columns),
            rounding_minutes=rounding if rounding in INCREMENTS else 0,
            scope=scope,
            folder=str(folder) if isinstance(folder, str) and folder else None,
        )


@dataclass(frozen=True, slots=True)
class PresetList:
    """Ordered, name-unique (case-insensitive) collection with JSON round-trip."""

    presets: tuple[ExportPreset, ...] = field(default_factory=tuple)

    def names(self) -> list[str]:
        return [p.name for p in self.presets]

    def get(self, name: str) -> ExportPreset | None:
        key = name.strip().casefold()
        return next((p for p in self.presets if p.name.casefold() == key), None)

    def upsert(self, preset: ExportPreset) -> PresetList:
        """Replace a preset of the same name (case-insensitively) or append."""
        key = preset.name.strip().casefold()
        kept = [p for p in self.presets if p.name.casefold() != key]
        pos = next((i for i, p in enumerate(self.presets) if p.name.casefold() == key), len(kept))
        kept.insert(pos, preset)
        return PresetList(tuple(kept))

    def remove(self, name: str) -> PresetList:
        key = name.strip().casefold()
        return PresetList(tuple(p for p in self.presets if p.name.casefold() != key))

    def to_json(self) -> list[dict[str, Any]]:
        return [p.to_json() for p in self.presets]

    @classmethod
    def from_json(cls, raw: Any, all_columns: tuple[str, ...]) -> PresetList:
        """Skips entries that do not validate rather than losing the whole list."""
        if not isinstance(raw, list):
            return cls()
        kept: list[ExportPreset] = []
        seen: set[str] = set()
        for item in raw:
            try:
                preset = ExportPreset.from_json(item)
                preset.validate(all_columns)
            except ValidationError:
                continue
            if preset.name.casefold() in seen:
                continue
            seen.add(preset.name.casefold())
            kept.append(preset)
        return cls(tuple(kept))
