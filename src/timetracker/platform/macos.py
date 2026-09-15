"""macOS specifics. Importable everywhere; the provider only constructs on Darwin."""

from __future__ import annotations

import sys


class QuartzIdleProvider:
    """``CGEventSourceSecondsSinceLastEventType(HIDSystemState, AnyInput)`` (PRD-02 §7.1).

    Needs ``pyobjc-framework-Quartz`` (declared for darwin only). This call does
    *not* require the Accessibility permission, unlike global event monitoring.
    """

    name = "macOS (Quartz HID event source)"

    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise OSError("QuartzIdleProvider is macOS-only")
        try:
            from Quartz import (  # type: ignore[import-not-found]
                CGEventSourceSecondsSinceLastEventType,
                kCGAnyInputEventType,
                kCGEventSourceStateHIDSystemState,
            )
        except ImportError as exc:  # pragma: no cover - depends on the install
            raise OSError("pyobjc-framework-Quartz is not installed") from exc
        self._fn = CGEventSourceSecondsSinceLastEventType
        self._state = kCGEventSourceStateHIDSystemState
        self._any = kCGAnyInputEventType
        self.seconds_idle()  # probe

    def seconds_idle(self) -> float:
        value = float(self._fn(self._state, self._any))
        return max(0.0, value)


class LaunchAgentAutostart:
    """``~/Library/LaunchAgents/<label>.plist`` with ``RunAtLoad`` (FR-108).

    ``SMAppService`` (macOS 13+) would need ``pyobjc-framework-ServiceManagement``,
    a fifth dependency, so the plist fallback is the only route in v1.
    """

    name = "macOS LaunchAgent"

    def __init__(self, label: str = "be.dawasal.timetracker") -> None:
        if sys.platform != "darwin":
            raise OSError("LaunchAgentAutostart is macOS-only")
        from pathlib import Path

        self._path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
        self._label = label

    def is_enabled(self) -> bool:
        return self._path.exists()

    def set_enabled(self, enabled: bool, command: list[str]) -> None:
        import plistlib

        if not enabled:
            self._path.unlink(missing_ok=True)
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "wb") as fh:
            plistlib.dump(
                {"Label": self._label, "ProgramArguments": command, "RunAtLoad": True},
                fh,
            )
