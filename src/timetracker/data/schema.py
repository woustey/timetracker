"""DDL for the *current* schema version (PRD-02 §4.1).

This is documentation and a drift guard, not the upgrade path: databases are
always built by applying ``migrations/`` in order. ``tests/data/test_migrate.py``
asserts that the migrated schema equals this DDL.
"""

from __future__ import annotations

TARGET_VERSION = 1

DDL_V1 = """
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
    record_method    TEXT    NOT NULL CHECK (record_method IN ('STOPWATCH','QUICKADD')),
    is_edited        INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL,
    modified_at      TEXT    NOT NULL
);

CREATE INDEX idx_entry_local_date ON entry(local_date);
CREATE INDEX idx_entry_started    ON entry(started_at_utc);
CREATE INDEX idx_entry_client     ON entry(client_id, local_date);
CREATE INDEX idx_entry_type       ON entry(type_id, local_date);

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

CREATE VIEW v_session_log AS
SELECT  e.uuid,
        e.local_date                    AS date,
        e.started_at_utc, e.ended_at_utc, e.tz_name,
        e.duration_seconds              AS total_seconds,
        c.name                          AS client,
        t.name                          AS type,
        CASE e.record_method
            WHEN 'STOPWATCH' THEN 'Start-Stop'
            ELSE 'Add Time'
        END                             AS record_method,
        e.note, e.is_edited
FROM entry e
LEFT JOIN client    c ON c.id = e.client_id
LEFT JOIN work_type t ON t.id = e.type_id
ORDER BY e.started_at_utc;
"""

CURRENT_DDL = DDL_V1
