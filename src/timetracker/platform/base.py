"""Platform protocols (PRD-02 §7).

``factory.py`` returns a working implementation or an explicit
:class:`Unavailable` with a human-readable reason — never a silently broken
stub — so the settings UI can say *why* a feature is greyed out (P7).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class IdleProvider(Protocol):
    name: str

    def seconds_idle(self) -> float:
        """Seconds since the last keyboard or mouse input. Never negative."""
        ...


@dataclass(frozen=True, slots=True)
class Unavailable:
    reason: str
