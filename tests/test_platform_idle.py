"""Idle providers: the factory never returns a broken stub (P7), and the native one works here."""

from __future__ import annotations

import sys
import time

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
def test_win32_provider_counts_up_without_input() -> None:
    from timetracker.platform.win32 import Win32IdleProvider

    provider = Win32IdleProvider()
    first = provider.seconds_idle()
    time.sleep(1.2)
    second = provider.seconds_idle()
    # No synthetic input here; the counter must have grown by about the sleep
    # (unless a human touched the machine mid-test, in which case it reset).
    assert second >= first + 1.0 or second < first


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
