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


class Win32IdleProvider:
    """``GetLastInputInfo`` against ``GetTickCount64`` (PRD-02 §7.1). No permissions needed.

    While the workstation is locked the input goes to the secure desktop and the
    last-input tick stops advancing, so a lock counts as idle (FR-211).
    """

    name = "Windows (GetLastInputInfo)"

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("Win32IdleProvider is Windows-only")
        self._user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        self._kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        self._kernel32.GetTickCount64.restype = ctypes.c_ulonglong

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        self._struct = LASTINPUTINFO
        self.seconds_idle()  # probe: raises if the call fails

    def seconds_idle(self) -> float:
        info = self._struct()
        info.cbSize = ctypes.sizeof(info)
        if not self._user32.GetLastInputInfo(ctypes.byref(info)):
            raise OSError("GetLastInputInfo failed")
        now_ms = int(self._kernel32.GetTickCount64())
        # dwTime is a 32-bit tick; compare in the same 32-bit ring.
        last_ms = int(info.dwTime)
        idle_ms = (now_ms - last_ms) & 0xFFFFFFFF
        return max(0.0, idle_ms / 1000.0)
