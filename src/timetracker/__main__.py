"""Entry point: the ``timetracker`` GUI script, or ``pythonw -m timetracker``.

``python -m timetracker`` also works and keeps the console you ran it from
(useful for debugging). A console that exists *only* for this process — which
some venv launchers create even for GUI launches — is released at startup.
"""

from __future__ import annotations

import sys


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
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
