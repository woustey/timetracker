"""Windows specifics. Safe to import on any platform; functions no-op elsewhere."""

from __future__ import annotations

import ctypes
import sys


def detach_orphan_console() -> bool:
    """Free a console that exists only for this process. Returns ``True`` if detached.

    A GUI launch can still end up with a console — the venv ``pythonw.exe``
    redirector on some 3.13 installs execs the console ``python.exe`` — and the
    window then sits there for the app's lifetime. ``GetConsoleProcessList``
    tells us whether anyone else (a shell the user ran us from) shares the
    console; if we are alone, it was created for us and is useless, so we
    ``FreeConsole()`` and Windows closes the window. Launched from a terminal
    for debugging, the shell is attached too and we keep stderr.
    """
    if sys.platform != "win32":
        return False
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    if kernel32.GetConsoleWindow() == 0:
        return False  # no console at all: the normal pythonw case
    count = kernel32.GetConsoleProcessList((ctypes.c_uint * 2)(), 2)
    if count != 1:
        return False
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            if stream is not None:
                stream.flush()
        except (OSError, ValueError):
            pass
    if not kernel32.FreeConsole():
        return False
    # The old handles now point nowhere; give Python inert streams so a stray
    # print() cannot raise inside the event loop.
    devnull = open("nul", "w", encoding="utf-8")  # noqa: SIM115 - lives for the process
    sys.stdout = devnull
    sys.stderr = devnull
    return True
