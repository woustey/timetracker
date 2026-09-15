"""Process measurements for NFR-01 / NFR-03, stdlib only. Nothing is transmitted.

``TIMETRACKER_MEASURE_BOOT=<idle seconds>`` makes ``__main__`` boot, stay idle
for that long, print one JSON line to stdout and exit — the harness the NFR
test drives. ``TIMETRACKER_ASSUME_TRAY=1`` skips the tray-availability check so
the measurement also runs on headless CI runners (offscreen platform).
"""

from __future__ import annotations

import ctypes
import os
import sys
import time

MEASURE_ENV = "TIMETRACKER_MEASURE_BOOT"
ASSUME_TRAY_ENV = "TIMETRACKER_ASSUME_TRAY"


def rss_bytes() -> int:
    """Resident set size of this process."""
    if sys.platform == "win32":

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):  # noqa: N801 - Win32 name
            _fields_ = [
                ("cb", ctypes.c_uint32),
                ("PageFaultCount", ctypes.c_uint32),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        psapi = ctypes.windll.psapi  # type: ignore[attr-defined]
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
            ctypes.c_uint32,
        ]
        psapi.GetProcessMemoryInfo.restype = ctypes.c_int
        if not psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            return 0
        return int(counters.WorkingSetSize)
    try:
        with open("/proc/self/statm", encoding="ascii") as fh:  # Linux: exact current RSS
            return int(fh.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError):
        pass
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak) if sys.platform == "darwin" else int(peak) * 1024  # bytes vs KiB


def cpu_seconds() -> float:
    t = os.times()
    return t.user + t.system


class IdleProbe:
    """Measures CPU used over a wall-clock window; call ``start()`` then ``finish()``."""

    def __init__(self) -> None:
        self._cpu0 = 0.0
        self._wall0 = 0.0

    def start(self) -> None:
        self._cpu0 = cpu_seconds()
        self._wall0 = time.perf_counter()

    def finish(self) -> tuple[float, float]:
        """(cpu seconds used, wall seconds elapsed)."""
        return cpu_seconds() - self._cpu0, time.perf_counter() - self._wall0
