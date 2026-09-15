"""FR-107: single instance via a file lock; second launch leaves a show request."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from timetracker.instance_lock import InstanceLock

_HOLD = """
import sys, time
from pathlib import Path
from timetracker.instance_lock import InstanceLock
lock = InstanceLock(Path(sys.argv[1]))
print("acquired" if lock.acquire() else "busy", flush=True)
if lock._fh is not None:
    time.sleep(float(sys.argv[2]))
"""


def test_lock_is_exclusive_across_processes(tmp_path: Path) -> None:
    primary = InstanceLock(tmp_path)
    assert primary.acquire() is True
    assert primary.path.exists()

    # A second process cannot take the lock while we hold it...
    out = subprocess.run(
        [sys.executable, "-c", _HOLD, str(tmp_path), "0"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    ).stdout.strip()
    assert out == "busy"

    # ...and can as soon as we release it.
    primary.release()
    out = subprocess.run(
        [sys.executable, "-c", _HOLD, str(tmp_path), "0"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    ).stdout.strip()
    assert out == "acquired"
    primary.release()  # idempotent


def test_lock_survives_a_hard_kill_of_the_holder(tmp_path: Path) -> None:
    """A killed primary must not leave a stale lock that blocks the next launch."""
    holder = subprocess.Popen(
        [sys.executable, "-c", _HOLD, str(tmp_path), "60"],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout is not None
    assert holder.stdout.readline().strip() == "acquired"
    second = InstanceLock(tmp_path)
    assert second.acquire() is False
    holder.kill()
    holder.wait(timeout=30)
    # The venv python.exe is a launcher: its real child dies via a job object a
    # few milliseconds after the launcher, so poll briefly rather than race it.
    deadline = time.monotonic() + 5
    acquired = False
    while not acquired and time.monotonic() < deadline:
        acquired = second.acquire()
        if not acquired:
            time.sleep(0.05)
    assert acquired
    second.release()


def test_show_request_round_trip(tmp_path: Path) -> None:
    primary = InstanceLock(tmp_path)
    assert primary.acquire()
    assert primary.consume_show_request() is False
    loser = InstanceLock(tmp_path)
    assert loser.acquire() is False
    loser.request_show()
    assert primary.show_request_path.exists()
    assert primary.consume_show_request() is True
    assert not primary.show_request_path.exists()
    assert primary.consume_show_request() is False
    primary.release()
