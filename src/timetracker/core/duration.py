"""Duration formatting. Parsing (PRD-02 §5.5) arrives with the matrix in M3."""

from __future__ import annotations


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
