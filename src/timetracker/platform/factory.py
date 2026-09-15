"""Pick the idle provider for this machine, or say why there is none (PRD-02 §7, P7)."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path

from timetracker.platform.base import AutostartProvider, IdleProvider, Unavailable


def autostart_provider() -> AutostartProvider | Unavailable:
    try:
        if sys.platform == "win32":
            from timetracker.platform.win32 import Win32Autostart

            return Win32Autostart()
        if sys.platform == "darwin":
            from timetracker.platform.macos import LaunchAgentAutostart

            return LaunchAgentAutostart()
        if sys.platform.startswith("linux"):
            from timetracker.platform.linux import DesktopAutostart

            return DesktopAutostart()
    except Exception as exc:  # noqa: BLE001
        return Unavailable(f"start at login not available: {exc}")
    return Unavailable(f"start at login not available on '{sys.platform}'")


def launch_command() -> list[str]:
    """How to start this installation again: the frozen exe, the GUI script, or ``pythonw -m``."""
    exe = Path(sys.executable)
    if getattr(sys, "frozen", False):
        return [str(exe)]
    script = exe.with_name("timetracker.exe" if sys.platform == "win32" else "timetracker")
    if script.exists():
        return [str(script)]
    interpreter = exe.with_name("pythonw.exe") if sys.platform == "win32" else exe
    if not interpreter.exists():
        interpreter = exe
    return [str(interpreter), "-m", "timetracker"]


def idle_provider() -> IdleProvider | Unavailable:
    candidates: list[Callable[[], IdleProvider]] = []
    if sys.platform == "win32":
        from timetracker.platform.win32 import Win32IdleProvider

        candidates.append(Win32IdleProvider)
    elif sys.platform == "darwin":
        from timetracker.platform.macos import QuartzIdleProvider

        candidates.append(QuartzIdleProvider)
    elif sys.platform.startswith("linux"):
        from timetracker.platform.linux import WaylandIdleProvider, X11IdleProvider

        # Under XWayland DISPLAY is set too but the X server only sees X clients;
        # prefer the compositor's answer when the session is Wayland.
        if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
            candidates.extend((WaylandIdleProvider, X11IdleProvider))
        else:
            candidates.extend((X11IdleProvider, WaylandIdleProvider))
    else:
        return Unavailable(f"no idle detection for platform '{sys.platform}'")

    reasons: list[str] = []
    for make in candidates:
        try:
            return make()
        except Exception as exc:  # noqa: BLE001 - every failure is a reason, not a crash
            reasons.append(f"{make.__name__}: {exc}")
    return Unavailable(
        "idle detection not available on this desktop session — " + "; ".join(reasons)
    )
