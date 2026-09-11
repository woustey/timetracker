"""Shared fixtures.

The socket audit hook is installed at import time — before any ``QApplication``
exists — so that :mod:`tests.test_no_network` can assert that nothing in the whole
test process, application boot included, touched the socket layer.

``TIMETRACKER_DATA_DIR`` is pointed at a throwaway directory for the whole
session so no test ever touches the user's real database.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SESSION_DATA_DIR = Path(tempfile.mkdtemp(prefix="timetracker-tests-"))
os.environ["TIMETRACKER_DATA_DIR"] = str(_SESSION_DATA_DIR)

SOCKET_EVENTS: list[tuple[str, tuple[Any, ...]]] = []


def _audit(event: str, args: tuple[Any, ...]) -> None:
    if event.startswith("socket."):
        SOCKET_EVENTS.append((event, args))


sys.addaudithook(_audit)


@pytest.fixture(scope="session")
def qapp_cls() -> type:
    """Make pytest-qt's ``qapp`` fixture an instance of our ``App`` subclass."""
    from timetracker.app import App

    return App


@pytest.fixture
def booted_app(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """The application bootstrapped against a fresh data directory, torn down after."""
    from PySide6.QtWidgets import QSystemTrayIcon

    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    assert qapp.bootstrap(tmp_path / "data") is True
    try:
        yield qapp
    finally:
        qapp.shutdown()


# -- shared data/service fixtures (in-memory database under a FakeClock) --------


@pytest.fixture
def clock() -> Any:
    from timetracker.core.clock import FakeClock

    return FakeClock(now=datetime(2026, 9, 11, 10, 0, tzinfo=UTC), tz="Europe/Brussels")


@pytest.fixture
def conn(clock: Any) -> Iterator[sqlite3.Connection]:
    from timetracker.data.db import connect
    from timetracker.data.migrate import migrate

    c = connect(":memory:")
    migrate(c, clock=clock)
    yield c
    c.close()


@pytest.fixture
def clients(conn: sqlite3.Connection, clock: Any) -> Any:
    from timetracker.core.models import Dimension
    from timetracker.data.label_repo import LabelRepo

    return LabelRepo(conn, Dimension.CLIENT, clock)


@pytest.fixture
def types(conn: sqlite3.Connection, clock: Any) -> Any:
    from timetracker.core.models import Dimension
    from timetracker.data.label_repo import LabelRepo

    return LabelRepo(conn, Dimension.TYPE, clock)


@pytest.fixture
def entries(conn: sqlite3.Connection, clock: Any) -> Any:
    from timetracker.data.entry_repo import EntryRepo

    return EntryRepo(conn, clock)


@pytest.fixture
def timers(conn: sqlite3.Connection) -> Any:
    from timetracker.data.timer_repo import TimerRepo

    return TimerRepo(conn)


@pytest.fixture
def timer(timers: Any) -> Any:
    return timers


@pytest.fixture
def settings(conn: sqlite3.Connection) -> Any:
    from timetracker.data.settings_repo import SettingsRepo

    return SettingsRepo(conn)


@pytest.fixture
def labels(clients: Any, types: Any) -> Any:
    from timetracker.services.label_service import LabelService

    return LabelService(clients, types)


@pytest.fixture
def service(qapp: Any, clock: Any, timers: Any, entries: Any, clients: Any, types: Any) -> Any:
    from timetracker.services.timer_service import TimerService

    return TimerService(clock, timers, entries, clients, types)
