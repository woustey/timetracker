"""Duration parsing and formatting (PRD-02 §5.5, FR-304)."""

from __future__ import annotations

import re

# Accepted grammar, all case-insensitive and whitespace-tolerant:
#   45        → 45 min          1:30      → 90 min
#   1h15      → 75 min          1h 15m    → 75 min
#   0.75h     → 45 min          1,5h      → 90 min (comma decimal, Belgian keyboard)
#   90m       → 90 min          2h        → 120 min
_NUMBER = r"(?:\d+(?:[.,]\d+)?)"
_BARE = re.compile(rf"^{_NUMBER}$")
_COLON = re.compile(r"^(\d+):(\d{1,2})$")
_HM = re.compile(
    rf"^(?:(?P<h>{_NUMBER})\s*h(?:ours?|rs?)?)?\s*(?:(?P<m>{_NUMBER})\s*(?:m(?:in(?:utes?)?)?)?)?$"
)


def parse_duration(text: str) -> int | None:
    """Return whole seconds, or ``None`` if *text* is not a duration.

    Bare numbers are minutes. Fractions are allowed on hours and minutes and
    are truncated to whole seconds. Zero is a valid duration (the caller
    decides whether it is useful); negatives cannot be expressed.
    """
    s = text.strip().casefold().replace(" ", "")
    if not s:
        return None
    if _BARE.match(s):
        return _to_seconds(_num(s) * 60)
    m = _COLON.match(s)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60
    m = _HM.match(s)
    if m and (m.group("h") or m.group("m")):
        hours = _num(m.group("h")) if m.group("h") else 0.0
        minutes = _num(m.group("m")) if m.group("m") else 0.0
        return _to_seconds(hours * 3600 + minutes * 60)
    return None


def _num(token: str) -> float:
    return float(token.replace(",", "."))


def _to_seconds(value: float) -> int:
    return int(value + 1e-9)


def format_hms(seconds: int) -> str:
    """``1:02:03`` — hours unpadded, minutes and seconds two digits. Negative clamps to zero."""
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def format_hm(seconds: int) -> str:
    """``1:02`` — the log/tooltip form. Truncates, never rounds (P2)."""
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    return f"{h}:{m:02d}"
