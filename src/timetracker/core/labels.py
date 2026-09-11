"""Near-duplicate label detection (FR-403, PRD-01 Q6).

Edit distance ≤ 2 on the normalised names, but only once the shorter name has
at least :data:`MIN_LENGTH` characters — otherwise every four-letter client
would collide with every other. Exact normalised matches are not duplicates
(they resolve to the same label already, FR-402).
"""

from __future__ import annotations

from collections.abc import Iterable

from timetracker.core.models import Label, normalise_label_name

MAX_DISTANCE = 2
MIN_LENGTH = 4


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def near_duplicates(name: str, labels: Iterable[Label]) -> list[Label]:
    """Existing labels the user probably meant, closest first."""
    norm = normalise_label_name(name)
    if not norm:
        return []
    scored: list[tuple[int, Label]] = []
    for label in labels:
        if label.name_norm == norm:
            continue
        if min(len(norm), len(label.name_norm)) < MIN_LENGTH:
            continue
        d = levenshtein(norm, label.name_norm)
        if d <= MAX_DISTANCE:
            scored.append((d, label))
    scored.sort(key=lambda pair: (pair[0], pair[1].name_norm))
    return [label for _, label in scored]
