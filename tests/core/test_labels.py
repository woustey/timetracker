from __future__ import annotations

from datetime import UTC, datetime

import pytest

from timetracker.core.labels import levenshtein, near_duplicates
from timetracker.core.models import Dimension, Label, normalise_label_name


def _label(idx: int, name: str) -> Label:
    now = datetime(2026, 9, 11, tzinfo=UTC)
    return Label(
        idx, Dimension.CLIENT, name, normalise_label_name(name), None, False, False, now, None
    )


@pytest.mark.parametrize(
    ("a", "b", "d"),
    [
        ("", "", 0),
        ("abc", "", 3),
        ("", "abc", 3),
        ("kitten", "sitting", 3),
        ("adidas", "addidas", 1),
        ("nike", "nikey", 1),
        ("flaw", "lawn", 2),
        ("same", "same", 0),
        ("ab", "ba", 2),
    ],
)
def test_levenshtein(a: str, b: str, d: int) -> None:
    assert levenshtein(a, b) == d


def test_near_duplicates_offers_close_existing_labels() -> None:
    labels = [
        _label(1, "Adidas"),
        _label(2, "ASICS"),
        _label(3, "Reebok"),
        _label(4, "Adidas Europe"),
    ]
    assert [x.name for x in near_duplicates("Addidas", labels)] == ["Adidas"]
    assert [x.name for x in near_duplicates("asic", labels)] == ["ASICS"]
    assert near_duplicates("Reebok", labels) == []  # exact match is not a duplicate
    assert near_duplicates("Puma", labels) == []


def test_short_names_are_not_flagged() -> None:
    labels = [_label(1, "Nike"), _label(2, "Puma"), _label(3, "ABC")]
    assert near_duplicates("Nika", labels) == [labels[0]]  # 4 chars: within reach
    assert near_duplicates("ABD", labels) == []  # 3 chars: too short to judge
    assert near_duplicates("Pume", labels) == [labels[1]]
    assert near_duplicates("", labels) == []


def test_closest_first_then_alphabetical() -> None:
    labels = [_label(1, "Brandt"), _label(2, "Brand"), _label(3, "Brands")]
    assert [x.name for x in near_duplicates("Brand", labels)] == ["Brands", "Brandt"]
    assert [x.name for x in near_duplicates("Brant", labels)] == ["Brand", "Brandt", "Brands"]
