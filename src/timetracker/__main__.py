"""Entry point: the ``timetracker`` GUI script, or ``pythonw -m timetracker``.

``python -m timetracker`` also works and keeps the console you ran it from
(useful for debugging). A console that exists *only* for this process — which
some venv launchers create even for GUI launches — is released at startup.
"""

from __future__ import annotations

import os
import sys
import time

_T0 = time.perf_counter()  # cold-start reference (NFR-01): before any heavy import


def main(argv: list[str] | None = None) -> int:
    from timetracker import crashlog
    from timetracker.app import App
    from timetracker.data import paths
    from timetracker.platform.win32 import detach_orphan_console

    detach_orphan_console()
    crashlog.install(paths.data_dir())
    app = App(sys.argv if argv is None else argv)
    if not app.bootstrap():
        return 1
    measure = os.environ.get("TIMETRACKER_MEASURE_BOOT")
    if measure:
        _measure_and_exit(app, float(measure))
    return app.exec()


def _measure_and_exit(app: object, idle_seconds: float) -> None:
    """NFR-01/03 harness: report boot time, idle CPU and RSS as one JSON line, then quit."""
    import json

    from PySide6.QtCore import QTimer

    from timetracker import diagnostics

    boot_seconds = time.perf_counter() - _T0
    probe = diagnostics.IdleProbe()

    def start_probe() -> None:
        probe.start()
        QTimer.singleShot(int(idle_seconds * 1000), report)

    def report() -> None:
        cpu, wall = probe.finish()
        print(
            json.dumps(
                {
                    "boot_seconds": round(boot_seconds, 3),
                    "idle_cpu_seconds": round(cpu, 4),
                    "idle_wall_seconds": round(wall, 3),
                    "idle_cpu_percent": round(100.0 * cpu / wall, 3) if wall else 0.0,
                    "rss_mb": round(diagnostics.rss_bytes() / (1024 * 1024), 1),
                }
            ),
            flush=True,
        )
        app.quit()  # type: ignore[attr-defined]

    QTimer.singleShot(0, start_probe)


if __name__ == "__main__":
    sys.exit(main())
