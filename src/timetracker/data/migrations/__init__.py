"""Versioned, forward-only migrations (PRD-02 §4.3).

One module per version named ``m{NNNN}_{slug}.py``, each exposing
``version: int`` and ``upgrade(conn) -> None``. :func:`all_migrations` returns
them sorted and validates that versions are contiguous from 1.
"""

from __future__ import annotations

import importlib
import pkgutil
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    upgrade: Callable[[sqlite3.Connection], None]


def all_migrations() -> list[Migration]:
    found: list[Migration] = []
    for info in pkgutil.iter_modules(__path__):
        if not info.name.startswith("m"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        found.append(Migration(int(module.version), info.name, module.upgrade))
    found.sort(key=lambda m: m.version)
    expected = list(range(1, len(found) + 1))
    if [m.version for m in found] != expected:
        raise RuntimeError(f"migration versions are not contiguous: {[m.version for m in found]}")
    return found
