"""Crash logging for console-less launches (PRD-02 §10, minimal slice).

A GUI-script launch has no console, so an unhandled exception would vanish.
``install()`` routes every uncaught exception to ``<data dir>/timetracker.log``
(rotating, 5 × 1 MB) and, if there is still a console, to stderr as before.
Nothing is ever transmitted (NFR-06).
"""

from __future__ import annotations

import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

LOG_NAME = "timetracker.log"
_LOGGER = "timetracker"


def install(data_dir: Path) -> Path:
    """Attach the file handler and the excepthook. Idempotent. Returns the log path."""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / LOG_NAME
    logger = logging.getLogger(_LOGGER)
    if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    previous = sys.excepthook

    def hook(
        exc_type: type[BaseException],
        exc: BaseException,
        tb: TracebackType | None,
    ) -> None:
        logger.critical(
            "Unhandled exception\n%s", "".join(traceback.format_exception(exc_type, exc, tb))
        )
        previous(exc_type, exc, tb)

    sys.excepthook = hook
    return path


def log() -> logging.Logger:
    return logging.getLogger(_LOGGER)
