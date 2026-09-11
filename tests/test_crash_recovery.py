"""M2 acceptance: a timer survives a crash to within one heartbeat of the truth.

Real file database, real ``SystemClock``, real ``QTimer`` heartbeat (shortened to
1 s). The "crash" is dropping the service without ``stop()``, exactly what
``kill -9`` leaves behind: a ``running_timer`` row and nothing else. A second
service on the same file must offer recovery, and the recovered duration must be
within one heartbeat interval (+ scheduling slack) of the wall time that passed.
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer

from timetracker.app import system_tz_name
from timetracker.core.clock import SystemClock
from timetracker.core.models import Dimension, RecordMethod
from timetracker.data.db import connect
from timetracker.data.entry_repo import EntryRepo
from timetracker.data.label_repo import LabelRepo
from timetracker.data.migrate import migrate
from timetracker.data.timer_repo import TimerRepo
from timetracker.services.timer_service import TimerService

HEARTBEAT_MS = 1_000
RUN_SECONDS = 3.2


def _services(db: Path, clock: SystemClock) -> tuple[TimerService, EntryRepo, TimerRepo, LabelRepo]:
    conn = connect(db)
    migrate(conn, db, clock=clock)
    clients = LabelRepo(conn, Dimension.CLIENT, clock)
    types = LabelRepo(conn, Dimension.TYPE, clock)
    entries = EntryRepo(conn, clock)
    timers = TimerRepo(conn)
    svc = TimerService(clock, timers, entries, clients, types, heartbeat_ms=HEARTBEAT_MS)
    return svc, entries, timers, clients


def _pump(seconds: float) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def test_kill_mid_timer_then_recover(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "timetracker.sqlite3"
    clock = SystemClock(tz_name=system_tz_name())

    # --- first process: start a timer, let heartbeats land, then "crash" -----
    svc, _, timers, clients = _services(db, clock)
    nike = clients.create("Nike")
    t_start = time.monotonic()
    svc.start(client_id=nike.id, note="mid-call")
    _pump(RUN_SECONDS)
    truth = time.monotonic() - t_start
    row = timers.get()
    assert row is not None and row.heartbeat_accrued_sec >= 1
    # Drop the service without stop(): the row is all that survives, as after kill -9.
    del svc

    # --- second process: relaunch on the same file ---------------------------
    svc2, entries2, timers2, _ = _services(db, clock)
    offer = svc2.pending_recovery
    assert offer is not None, "relaunch did not detect the crashed timer"
    recovered = offer.duration_seconds

    slack = HEARTBEAT_MS / 1000 + 0.5
    assert truth - slack <= recovered <= truth + 0.5, (recovered, truth)

    entry = svc2.recover()
    assert entry.duration_seconds == recovered
    assert entry.record_method is RecordMethod.STOPWATCH
    assert entry.client_id == nike.id
    assert entry.note == "mid-call"
    assert entry.ended_at_utc == row.heartbeat_at_utc
    assert timers2.get() is None
    assert entries2.count() == 1
