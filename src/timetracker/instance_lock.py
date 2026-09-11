"""Single-instance guard without sockets (FR-107, NFR-05).

The primary instance holds an OS-level lock on ``<data dir>/instance.lock`` for
its lifetime. A second launch fails to acquire it, drops a ``show.request``
file next to it and exits; the primary watches its data directory with
``QFileSystemWatcher`` and opens the popover when that file appears.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import IO

LOCK_NAME = "instance.lock"
SHOW_REQUEST_NAME = "show.request"


class InstanceLock:
    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._path = directory / LOCK_NAME
        self._fh: IO[bytes] | None = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def show_request_path(self) -> Path:
        return self._dir / SHOW_REQUEST_NAME

    def acquire(self) -> bool:
        """Return ``True`` if this process is now the primary instance."""
        self._dir.mkdir(parents=True, exist_ok=True)
        fh = open(self._path, "a+b")  # noqa: SIM115 - held for the process lifetime
        try:
            _lock(fh)
        except OSError:
            fh.close()
            return False
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()).encode())
        fh.flush()
        self._fh = fh
        return True

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            _unlock(self._fh)
        finally:
            self._fh.close()
            self._fh = None

    def request_show(self) -> None:
        """Called by the losing instance: ask the primary to surface its popover."""
        self.show_request_path.write_text(str(os.getpid()), encoding="utf-8")

    def consume_show_request(self) -> bool:
        """Called by the primary: ``True`` once per request file, which is removed."""
        try:
            self.show_request_path.unlink()
        except FileNotFoundError:
            return False
        return True


if sys.platform == "win32":
    import msvcrt

    def _lock(fh: IO[bytes]) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(fh: IO[bytes]) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(fh: IO[bytes]) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fh: IO[bytes]) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
