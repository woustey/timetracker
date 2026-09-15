"""Linux specifics: X11 via ``libXss`` (ctypes) and Wayland via D-Bus (PRD-02 §7.1).

Neither Wayland path is universal — GNOME exposes Mutter's IdleMonitor, KDE the
freedesktop ScreenSaver interface — so the factory tries each and otherwise
reports :class:`Unavailable` with the reason. ``PySide6.QtDBus`` ships with
PySide6 and is not a network module (NFR-05 is about sockets to the outside
world; the session bus is a local IPC socket owned by the desktop).
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys


class X11IdleProvider:
    name = "Linux / X11 (XScreenSaverQueryInfo)"

    def __init__(self) -> None:
        if not sys.platform.startswith("linux"):
            raise OSError("X11IdleProvider is Linux-only")
        if not os.environ.get("DISPLAY"):
            raise OSError("no X11 DISPLAY in this session")
        x11_name = ctypes.util.find_library("X11")
        xss_name = ctypes.util.find_library("Xss")
        if not x11_name or not xss_name:
            raise OSError("libX11 / libXss not found")
        self._x11 = ctypes.cdll.LoadLibrary(x11_name)
        self._xss = ctypes.cdll.LoadLibrary(xss_name)

        class XScreenSaverInfo(ctypes.Structure):
            _fields_ = [
                ("window", ctypes.c_ulong),
                ("state", ctypes.c_int),
                ("kind", ctypes.c_int),
                ("til_or_since", ctypes.c_ulong),
                ("idle", ctypes.c_ulong),
                ("eventMask", ctypes.c_ulong),
            ]

        self._x11.XOpenDisplay.restype = ctypes.c_void_p
        self._x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self._x11.XDefaultRootWindow.restype = ctypes.c_ulong
        self._x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        self._xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(XScreenSaverInfo)
        self._xss.XScreenSaverQueryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(XScreenSaverInfo),
        ]
        self._display = self._x11.XOpenDisplay(None)
        if not self._display:
            raise OSError("XOpenDisplay failed")
        self._root = self._x11.XDefaultRootWindow(self._display)
        self._info = self._xss.XScreenSaverAllocInfo()
        self.seconds_idle()  # probe

    def seconds_idle(self) -> float:
        if not self._xss.XScreenSaverQueryInfo(self._display, self._root, self._info):
            raise OSError("XScreenSaverQueryInfo failed")
        return max(0.0, self._info.contents.idle / 1000.0)


class WaylandIdleProvider:
    """GNOME ``org.gnome.Mutter.IdleMonitor`` (ms) or KDE ``org.freedesktop.ScreenSaver`` (s)."""

    name = "Linux / Wayland (D-Bus)"

    _CANDIDATES = (
        # (service, path, interface, method, divisor to seconds, label)
        (
            "org.gnome.Mutter.IdleMonitor",
            "/org/gnome/Mutter/IdleMonitor/Core",
            "org.gnome.Mutter.IdleMonitor",
            "GetIdletime",
            1000.0,
            "GNOME Mutter IdleMonitor",
        ),
        (
            "org.freedesktop.ScreenSaver",
            "/ScreenSaver",
            "org.freedesktop.ScreenSaver",
            "GetSessionIdleTime",
            1.0,
            "freedesktop ScreenSaver (KDE)",
        ),
    )

    def __init__(self) -> None:
        if not sys.platform.startswith("linux"):
            raise OSError("WaylandIdleProvider is Linux-only")
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusInterface
        except ImportError as exc:  # pragma: no cover - depends on the build
            raise OSError("QtDBus is not available in this PySide6 build") from exc
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            raise OSError("no D-Bus session bus")
        for service, path, iface, method, divisor, label in self._CANDIDATES:
            proxy = QDBusInterface(service, path, iface, bus)
            if not proxy.isValid():
                continue
            reply = proxy.call(method)
            args = reply.arguments()
            if args and isinstance(args[0], int | float):
                self._proxy = proxy
                self._method = method
                self._divisor = divisor
                self.name = f"Linux / Wayland ({label})"
                return
        raise OSError("no idle-time D-Bus service on this desktop (GNOME Mutter / KDE)")

    def seconds_idle(self) -> float:
        args = self._proxy.call(self._method).arguments()
        if not args:
            raise OSError("D-Bus idle query returned nothing")
        return max(0.0, float(args[0]) / self._divisor)
