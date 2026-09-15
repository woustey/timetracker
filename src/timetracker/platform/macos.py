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
