"""LabelRepo: CRUD, FR-402 normalisation, FR-404 rename, FR-405 archive/restrict, FR-409 seed."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from timetracker.core.clock import FakeClock
from timetracker.core.errors import (
    DuplicateLabelError,
    LabelInUseError,
    NotFoundError,
    ValidationError,
)
from timetracker.core.models import Dimension, NewEntry, RecordMethod
from timetracker.data.entry_repo import EntryRepo
from timetracker.data.label_repo import SEED_TYPES, LabelRepo


def test_create_and_get(clients: LabelRepo, clock: FakeClock) -> None:
    label = clients.create("Nike")
    assert label.id > 0
    assert label.dimension is Dimension.CLIENT
    assert label.name == "Nike"
    assert label.name_norm == "nike"
    assert label.colour is None
    assert not label.is_archived
    assert not label.is_pinned
    assert label.created_at == clock.now_utc()
    assert label.last_used_at is None
    assert clients.get(label.id) == label


def test_get_missing_raises(clients: LabelRepo) -> None:
    with pytest.raises(NotFoundError):
        clients.get(999)


def test_dimensions_are_separate_tables(clients: LabelRepo, types: LabelRepo) -> None:
    clients.create("Work")
    types.create("Work")  # same name, different dimension: allowed
    assert clients.count() == 1
    assert types.count() == 1


@pytest.mark.parametrize("dup", ["nike", "Nike ", "  NIKE", "N i k e".replace(" ", "")])
def test_case_and_whitespace_duplicates_rejected(clients: LabelRepo, dup: str) -> None:
    clients.create("Nike")
    with pytest.raises(DuplicateLabelError):
        clients.create(dup)


def test_first_casing_is_preserved(clients: LabelRepo) -> None:
    clients.create("Nike")
    assert clients.get_or_create("NIKE").name == "Nike"
    assert clients.count() == 1


def test_get_or_create_creates_when_absent(clients: LabelRepo) -> None:
    label = clients.get_or_create("  Adidas  Europe ")
    assert label.name == "Adidas Europe"
    assert clients.count() == 1


def test_empty_name_rejected(clients: LabelRepo) -> None:
    with pytest.raises(ValidationError):
        clients.create("   ")


def test_find_by_name(clients: LabelRepo) -> None:
    created = clients.create("ASICS")
    assert clients.find_by_name("asics ") == created
    assert clients.find_by_name("Puma") is None


def test_rename_propagates_to_entries(
    clients: LabelRepo, entries: EntryRepo, clock: FakeClock
) -> None:
    label = clients.create("Adiddas")
    t0 = clock.now_utc()
    entry = entries.insert(NewEntry(t0, t0, "UTC", 60, RecordMethod.QUICKADD, client_id=label.id))
    renamed = clients.rename(label.id, "Adidas")
    assert renamed.name == "Adidas"
    assert renamed.name_norm == "adidas"
    # Entries reference the id, so they follow the rename without being touched.
    assert entries.get(entry.id).client_id == label.id
    assert not entries.get(entry.id).is_edited


def test_rename_to_self_casing_allowed_but_clash_rejected(clients: LabelRepo) -> None:
    a = clients.create("nike")
    clients.create("Adidas")
    assert clients.rename(a.id, "NIKE").name == "NIKE"
    with pytest.raises(DuplicateLabelError):
        clients.rename(a.id, "adidas")


def test_archive_hides_from_default_list(clients: LabelRepo) -> None:
    a = clients.create("A")
    b = clients.create("B")
    clients.set_archived(a.id, True)
    assert [x.id for x in clients.list_all()] == [b.id]
    assert {x.id for x in clients.list_all(include_archived=True)} == {a.id, b.id}
    assert clients.count() == 1
    assert clients.count(include_archived=True) == 2
    clients.set_archived(a.id, False)
    assert clients.count() == 2


def test_delete_unreferenced(clients: LabelRepo) -> None:
    a = clients.create("A")
    clients.delete(a.id)
    with pytest.raises(NotFoundError):
        clients.get(a.id)
    with pytest.raises(NotFoundError):
        clients.delete(a.id)


def test_delete_referenced_is_refused_by_restrict(
    clients: LabelRepo, types: LabelRepo, entries: EntryRepo, clock: FakeClock
) -> None:
    c = clients.create("Nike")
    t = types.create("Work")
    now = clock.now_utc()
    entries.insert(
        NewEntry(now, now, "UTC", 60, RecordMethod.STOPWATCH, client_id=c.id, type_id=t.id)
    )
    with pytest.raises(LabelInUseError):
        clients.delete(c.id)
    with pytest.raises(LabelInUseError):
        types.delete(t.id)
    # Still there; archive is the offered path (FR-405).
    assert clients.get(c.id).name == "Nike"
    assert clients.entry_count(c.id) == 1
    assert types.entry_count(t.id) == 1


def test_list_ordering_pinned_then_mru_then_creation(clients: LabelRepo, clock: FakeClock) -> None:
    zed = clients.create("Zed")
    clients.create("Alpha")
    mid = clients.create("Mid")
    clients.create("Beta")
    pinned = clients.create("Pinned")
    clients.set_pinned(pinned.id, True)
    clients.touch_last_used(zed.id)
    clock.advance(60)
    clients.touch_last_used(mid.id)
    order = [x.name for x in clients.list_all()]
    assert order == ["Pinned", "Mid", "Zed", "Alpha", "Beta"]
    assert clients.get(mid.id).last_used_at == datetime(2026, 9, 11, 10, 1, tzinfo=UTC)


def test_seed_types_only_when_empty(types: LabelRepo) -> None:
    seeded = types.ensure_seed()
    assert [x.name for x in seeded] == list(SEED_TYPES)
    types.set_archived(seeded[1].id, True)  # archive "Phone"
    assert types.ensure_seed() == []  # not re-seeded
    assert types.get(seeded[1].id).is_archived


def test_seed_not_applied_to_clients_by_default(clients: LabelRepo) -> None:
    # FR-409: clients start empty. ensure_seed is only *called* for types; verify
    # the repo makes no assumption about its own dimension.
    assert clients.count() == 0


def test_colour(clients: LabelRepo) -> None:
    a = clients.create("A", colour="#ff0000")
    assert a.colour == "#ff0000"
    assert clients.set_colour(a.id, None).colour is None
