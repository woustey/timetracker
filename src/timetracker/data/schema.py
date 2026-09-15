"""DDL for the *current* schema version (PRD-02 §4.1).

This is documentation and a drift guard, not the upgrade path: databases are
always built by applying ``migrations/`` in order. ``tests/data/test_migrate.py``
asserts that the migrated schema equals :data:`CURRENT_DDL`.

The DDL is kept as named pieces so a migration that rebuilds a table (SQLite
cannot alter a CHECK constraint) can reuse the exact text, which keeps the
``sqlite_master`` entries byte-identical to a fresh build.
"""

from __future__ import annotations

TARGET_VERSION = 3

LABEL_TABLES = """
CREATE TABLE client (
    id           INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL,
    name_norm    TEXT    NOT NULL UNIQUE,
    colour       TEXT,
    is_archived  INTEGER NOT NULL DEFAULT 0,
    is_pinned    INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL,
    last_used_at TEXT
);

CREATE TABLE work_type (
    id           INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL,
    name_norm    TEXT    NOT NULL UNIQUE,
    colour       TEXT,
    is_archived  INTEGER NOT NULL DEFAULT 0,
    is_pinned    INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL,
    last_used_at TEXT
);
"""

_ENTRY_TABLE_TEMPLATE = """
CREATE TABLE entry (
    id               INTEGER PRIMARY KEY,
    uuid             TEXT    NOT NULL UNIQUE,
    started_at_utc   TEXT    NOT NULL,
    ended_at_utc     TEXT    NOT NULL,
    tz_name          TEXT    NOT NULL,
    local_date       TEXT    NOT NULL,
    duration_seconds INTEGER NOT NULL CHECK (duration_seconds >= 0),
    paused_seconds   INTEGER NOT NULL DEFAULT 0,
    client_id        INTEGER REFERENCES client(id)    ON DELETE RESTRICT,
    type_id          INTEGER REFERENCES work_type(id) ON DELETE RESTRICT,
    note             TEXT,
    record_method    TEXT    NOT NULL CHECK (record_method IN ({methods})),
    is_edited        INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL,
    modified_at      TEXT    NOT NULL
);
"""

ENTRY_TABLE_V1 = _ENTRY_TABLE_TEMPLATE.format(methods="'STOPWATCH','QUICKADD'")
ENTRY_TABLE_V3 = _ENTRY_TABLE_TEMPLATE.format(methods="'STOPWATCH','QUICKADD','MANUAL'")

ENTRY_INDEXES_V1 = """
CREATE INDEX idx_entry_local_date ON entry(local_date);
CREATE INDEX idx_entry_started    ON entry(started_at_utc);
CREATE INDEX idx_entry_client     ON entry(client_id, local_date);
CREATE INDEX idx_entry_type       ON entry(type_id, local_date);
"""

ENTRY_INDEXES_V2 = """
CREATE INDEX idx_entry_totals ON entry(client_id, type_id, duration_seconds);
"""

OTHER_TABLES = """
CREATE TABLE running_timer (
    id                    INTEGER PRIMARY KEY CHECK (id = 1),
    started_at_utc        TEXT    NOT NULL,
    tz_name               TEXT    NOT NULL,
    accrued_seconds       INTEGER NOT NULL DEFAULT 0,
    paused_since_utc      TEXT,
    client_id             INTEGER REFERENCES client(id),
    type_id               INTEGER REFERENCES work_type(id),
    note                  TEXT,
    heartbeat_at_utc      TEXT    NOT NULL,
    heartbeat_accrued_sec INTEGER NOT NULL
);

CREATE TABLE setting (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE schema_migration (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""

_VIEW_TEMPLATE = """
CREATE VIEW v_session_log AS
SELECT  e.uuid,
        e.local_date                    AS date,
        e.started_at_utc, e.ended_at_utc, e.tz_name,
        e.duration_seconds              AS total_seconds,
        c.name                          AS client,
        t.name                          AS type,
        CASE e.record_method
            WHEN 'STOPWATCH' THEN 'Start-Stop'
{extra}            ELSE 'Add Time'
        END                             AS record_method,
        e.note, e.is_edited
FROM entry e
LEFT JOIN client    c ON c.id = e.client_id
LEFT JOIN work_type t ON t.id = e.type_id
ORDER BY e.started_at_utc;
"""

VIEW_V1 = _VIEW_TEMPLATE.format(extra="")
VIEW_V3 = _VIEW_TEMPLATE.format(extra="            WHEN 'MANUAL' THEN 'Manual'\n")

# What each migration builds on top of the previous version.
DDL_V1 = LABEL_TABLES + ENTRY_TABLE_V1 + ENTRY_INDEXES_V1 + OTHER_TABLES + VIEW_V1
DDL_V2_ADDITIONS = ENTRY_INDEXES_V2

# The current schema, as a fresh build would produce it.
CURRENT_DDL = (
    LABEL_TABLES + ENTRY_TABLE_V3 + ENTRY_INDEXES_V1 + ENTRY_INDEXES_V2 + OTHER_TABLES + VIEW_V3
)
