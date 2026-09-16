"""ExportPreset / PresetList (FR-608): validation, JSON round-trip, lenient loading."""

from __future__ import annotations

import pytest

from timetracker.core.errors import ValidationError
from timetracker.core.export_presets import ExportPreset, PresetList
from timetracker.core.rounding import RoundingScope

COLS = ("Date", "Start", "End", "Duration (h:mm)", "Client", "Note")


def _preset(name: str = "Invoice", **kw: object) -> ExportPreset:
    base: dict[str, object] = dict(
        name=name, fmt="xlsx", columns=("Date", "Client", "Duration (h:mm)"), rounding_minutes=15
    )
    base.update(kw)
    return ExportPreset(**base)  # type: ignore[arg-type]


def test_round_trip_and_defaults() -> None:
    p = _preset(scope=RoundingScope.PER_ENTRY, folder="C:/exports")
    again = ExportPreset.from_json(p.to_json())
    assert again == p
    assert ExportPreset.from_json({"name": "x", "columns": ["Date"]}) == ExportPreset(
        "x", "csv", ("Date",), 0, RoundingScope.PER_GROUP, None
    )


@pytest.mark.parametrize(
    "bad",
    [
        dict(name="   "),
        dict(name="n" * 61),
        dict(fmt="pdf"),
        dict(columns=()),
        dict(columns=("Date", "Bogus")),
        dict(rounding_minutes=7),
    ],
)
def test_validation(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _preset(**bad).validate(COLS)


def test_list_upsert_is_case_insensitive_and_keeps_order() -> None:
    lst = PresetList().upsert(_preset("A")).upsert(_preset("B")).upsert(_preset("C"))
    assert lst.names() == ["A", "B", "C"]
    lst = lst.upsert(_preset("b", rounding_minutes=30))
    assert lst.names() == ["A", "b", "C"]
    assert lst.get("B") is not None and lst.get("B").rounding_minutes == 30
    assert lst.remove(" c ").names() == ["A", "b"]
    assert lst.get("nope") is None


def test_lenient_loading_skips_broken_and_duplicate_entries() -> None:
    raw = [
        _preset("ok").to_json(),
        "not an object",
        {"name": "no columns"},
        {"name": "bad column", "columns": ["Nope"]},
        {"name": "OK", "columns": ["Date"]},  # duplicate name, case-insensitively
        {"name": "odd values", "columns": ["Date"], "rounding_minutes": "x", "scope": "?"},
    ]
    lst = PresetList.from_json(raw, COLS)
    assert lst.names() == ["ok", "odd values"]
    odd = lst.get("odd values")
    assert odd is not None and odd.rounding_minutes == 0 and odd.scope is RoundingScope.PER_GROUP
    assert PresetList.from_json("garbage", COLS).presets == ()
    assert PresetList.from_json(lst.to_json(), COLS) == lst
