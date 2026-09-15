"""Bundled resources: icons rendered by ``scripts/make_icons.py``.

Works from a source checkout, a wheel, a PyInstaller directory and a Nuitka
standalone build — all keep the package directory layout.
"""

from __future__ import annotations

from pathlib import Path

_HERE = Path(__file__).resolve().parent


def icon_path() -> Path | None:
    """The best icon file for the running platform, or ``None`` if not shipped."""
    for name in ("icon.ico", "icon.png"):
        candidate = _HERE / name
        if candidate.is_file():
            return candidate
    return None


def png_path(size: int) -> Path | None:
    candidate = _HERE / f"icon-{size}.png"
    return candidate if candidate.is_file() else None
