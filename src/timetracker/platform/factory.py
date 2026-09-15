"""Pick the idle provider for this machine, or say why there is none (PRD-02 §7, P7)."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable

from timetracker.platform.base import IdleProvider, Unavailable


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
