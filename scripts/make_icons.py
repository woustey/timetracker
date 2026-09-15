"""Render the painted tray clock to real icon files (PNG set + .ico).

Usage: ``python scripts/make_icons.py`` — writes into ``src/timetracker/resources``.
The ``.icns`` for macOS is produced in CI with ``iconutil`` from the PNG set.
Stdlib + PySide6 only: the ICO container is written by hand (PNG-in-ICO, which
Windows has accepted since Vista).
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "timetracker" / "resources"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QGuiApplication

    from timetracker.ui.icons import TrayState, make_icon

    app = QGuiApplication.instance() or QGuiApplication([])
    icon = make_icon(TrayState.IDLE)
    OUT.mkdir(parents=True, exist_ok=True)
    pngs: list[tuple[int, bytes]] = []
    for size in SIZES:
        pixmap = icon.pixmap(size, size)
        if pixmap.width() != size:
            pixmap = pixmap.scaled(size, size)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "PNG")
        data = bytes(buffer.data())
        (OUT / f"icon-{size}.png").write_bytes(data)
        pngs.append((size, data))
    (OUT / "icon.png").write_bytes(dict(pngs)[256])
    (OUT / "icon.ico").write_bytes(build_ico(pngs))
    print(f"wrote {len(pngs)} PNGs and icon.ico to {OUT}")
    del app
    return 0


def build_ico(pngs: list[tuple[int, bytes]]) -> bytes:
    """ICO container with one PNG-encoded image per size."""
    header = struct.pack("<HHH", 0, 1, len(pngs))
    directory = b""
    offset = 6 + 16 * len(pngs)
    payload = b""
    for size, data in pngs:
        dim = 0 if size >= 256 else size  # 0 means 256 in the ICO directory
        directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        payload += data
        offset += len(data)
    return header + directory + payload


if __name__ == "__main__":
    sys.exit(main())
