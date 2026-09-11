from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from timetracker.core.clock import FakeClock
from timetracker.core.models import Dimension
from timetracker.data.db import connect
from timetracker.data.entry_repo import EntryRepo
from timetracker.data.label_repo import LabelRepo
from timetracker.data.migrate import migrate
from timetracker.data.settings_repo import SettingsRepo
from timetracker.data.timer_repo import TimerRepo


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(now=datetime(2026, 9, 11, 10, 0, tzinfo=UTC), tz="Europe/Brussels")


@pytest.fixture
def conn(clock: FakeClock) -> Iterator[sqlite3.Connection]:
    c = connect(":memory:")
    migrate(c, clock=clock)
    yield c
    c.close()


@pytest.fixture
def clients(conn: sqlite3.Connection, clock: FakeClock) -> LabelRepo:
    return LabelRepo(conn, Dimension.CLIENT, clock)


@pytest.fixture
def types(conn: sqlite3.Connection, clock: FakeClock) -> LabelRepo:
    return LabelRepo(conn, Dimension.TYPE, clock)


@pytest.fixture
def entries(conn: sqlite3.Connection, clock: FakeClock) -> EntryRepo:
    return EntryRepo(conn, clock)


@pytest.fixture
def timer(conn: sqlite3.Connection) -> TimerRepo:
    return TimerRepo(conn)


@pytest.fixture
def settings(conn: sqlite3.Connection) -> SettingsRepo:
    return SettingsRepo(conn)
