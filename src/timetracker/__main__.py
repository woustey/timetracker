"""Entry point: the ``timetracker`` GUI script, or ``pythonw -m timetracker``.

``python -m timetracker`` also works but keeps a console attached — closing
that console kills the tray app — so it is for debugging only.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    from timetracker import crashlog
    from timetracker.app import App
    from timetracker.data import paths

    crashlog.install(paths.data_dir())
    app = App(sys.argv if argv is None else argv)
    if not app.bootstrap():
        return 1
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
