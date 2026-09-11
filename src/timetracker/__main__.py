"""Entry point: ``python -m timetracker`` or the ``timetracker`` console script."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    from timetracker.app import App

    app = App(sys.argv if argv is None else argv)
    if not app.bootstrap():
        return 1
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
