"""v2: covering index for the log window's totals (FR-504, NFR-04).

``GROUP BY client_id`` / ``type_id`` with ``SUM(duration_seconds)`` over 50 000
rows took ~180 ms with table lookups; an index that carries the duration makes
it an index-only scan (~7 ms).
"""

from __future__ import annotations

import sqlite3

from timetracker.data.db import execute_script
from timetracker.data.schema import DDL_V2_ADDITIONS

version = 2


def upgrade(conn: sqlite3.Connection) -> None:
    execute_script(conn, DDL_V2_ADDITIONS)
