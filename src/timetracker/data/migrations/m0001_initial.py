"""v1: the initial schema."""

from __future__ import annotations

import sqlite3

from timetracker.data.db import execute_script
from timetracker.data.schema import DDL_V1

version = 1


def upgrade(conn: sqlite3.Connection) -> None:
    execute_script(conn, DDL_V1)
