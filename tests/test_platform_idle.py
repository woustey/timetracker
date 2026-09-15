"""Idle providers: the factory never returns a broken stub (P7), and the native one works here."""

from __future__ import annotations

import sys

import pytest

from timetracker.platform.base import Unavailable
from timetracker.platform.factory import idle_provider


def test_factory_returns_a_provider_or_a_reason() -> None:
    result = idle_provider()
    if isinstance(result, Unavailable):
        assert result.reason.strip()
        assert "idle detection" in result.reason
    else:
        assert result.name
        value = result.seconds_idle()
        assert isinstance(value, float)
        assert value >= 0.0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only provider")
def test_win32_provider_arithmetic_with_stubbed_kernel() -> None:
    """Deterministic: stub the two Win32 calls, including the 32-bit tick wrap."""
    import ctypes

    from timetracker.platform.win32 import Win32IdleProvider

    provider = Win32IdleProvider()  # real probe once: the calls exist and work

    class FakeKernel32:
        tick = 0

        @staticmethod
        def GetTickCount64() -> int:  # noqa: N802 - Win32 name
            return FakeKernel32.tick

    class FakeUser32:
        last_input = 0

        @staticmethod
        def GetLastInputInfo(ref: object) -> int:  # noqa: N802 - Win32 name
            info = ctypes.cast(ref, ctypes.POINTER(provider._struct)).contents  # noqa: SLF001
            info.dwTime = FakeUser32.last_input
            return 1

    provider._kernel32 = FakeKernel32  # noqa: SLF001
    provider._user32 = FakeUser32  # noqa: SLF001

    FakeUser32.last_input, FakeKernel32.tick = 10_000, 10_000
    assert provider.seconds_idle() == 0.0
    FakeKernel32.tick = 10_000 + 90_500
    assert provider.seconds_idle() == 90.5
    # GetTickCount wraps every 49.7 days; dwTime is the low 32 bits.
    FakeUser32.last_input, FakeKernel32.tick = 0xFFFF_FF00, 0x1_0000_0100
    assert provider.seconds_idle() == 0.512
    # Never negative even if the last-input tick is somehow ahead.
    FakeUser32.last_input, FakeKernel32.tick = 5_000, 4_000
    assert provider.seconds_idle() >= 0.0


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only provider")
def test_quartz_provider_constructs() -> None:
    from timetracker.platform.macos import QuartzIdleProvider

    provider = QuartzIdleProvider()
    assert provider.seconds_idle() >= 0.0


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux-only providers")
def test_linux_providers_fail_loudly_without_a_desktop() -> None:
    """Under offscreen CI there is no X server and no compositor: both must raise, not lie."""
    import os

    from timetracker.platform.linux import WaylandIdleProvider, X11IdleProvider

    if not os.environ.get("DISPLAY"):
        with pytest.raises(OSError):
            X11IdleProvider()
    if not os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        with pytest.raises(OSError):
            WaylandIdleProvider()
