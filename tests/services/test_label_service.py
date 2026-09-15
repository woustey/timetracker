"""LabelService management ops (FR-404, FR-405) as the settings dialog uses them."""

from __future__ import annotations

import pytest

from timetracker.core.errors import DuplicateLabelError, LabelInUseError
from timetracker.core.models import Dimension
from timetracker.services.entry_service import EntryService
from timetracker.services.label_service import LabelService


def test_rename_propagates_and_signals(
    labels: LabelService, entry_service: EntryService, qtbot
) -> None:  # type: ignore[no-untyped-def]
    nike = labels.get_or_create(Dimension.CLIENT, "Nkie")
    e = entry_service.add_quick(60, nike.id, None, None)
    with qtbot.waitSignal(labels.labels_changed, timeout=1000) as blocker:
        renamed = labels.rename(Dimension.CLIENT, nike.id, "Nike")
    assert blocker.args == [Dimension.CLIENT]
    assert renamed.name == "Nike"
    assert entry_service._entries.get(e.id).client_id == nike.id  # noqa: SLF001
    labels.get_or_create(Dimension.CLIENT, "Adidas")
    with pytest.raises(DuplicateLabelError):
        labels.rename(Dimension.CLIENT, nike.id, "adidas")


def test_archive_hides_from_chips_but_keeps_history(
    labels: LabelService, entry_service: EntryService
) -> None:
    nike = labels.get_or_create(Dimension.CLIENT, "Nike")
    entry_service.add_quick(60, nike.id, None, None)
    labels.set_archived(Dimension.CLIENT, nike.id, True)
    assert [x.id for x in labels.list(Dimension.CLIENT)] == []  # chips/combos
    assert [x.id for x in labels.list_all(Dimension.CLIENT)] == [nike.id]  # management
    assert labels.entry_count(Dimension.CLIENT, nike.id) == 1
    labels.set_archived(Dimension.CLIENT, nike.id, False)
    assert [x.id for x in labels.list(Dimension.CLIENT)] == [nike.id]


def test_delete_only_when_unused(labels: LabelService, entry_service: EntryService) -> None:
    used = labels.get_or_create(Dimension.TYPE, "Work")
    unused = labels.get_or_create(Dimension.TYPE, "Travel")
    entry_service.add_quick(60, None, used.id, None)
    with pytest.raises(LabelInUseError):
        labels.delete(Dimension.TYPE, used.id)
    labels.delete(Dimension.TYPE, unused.id)
    assert [x.name for x in labels.list_all(Dimension.TYPE)] == ["Work"]
