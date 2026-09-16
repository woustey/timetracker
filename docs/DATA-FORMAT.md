# Time Tracker — data format

*NFR-10: the schema and file format are documented so the data is usable
without the application.* This page describes schema **v4** (the current one).

## Where the data lives

| OS | Folder |
|---|---|
| Windows | `%LOCALAPPDATA%\TimeTracker` |
| macOS | `~/Library/Application Support/TimeTracker` |
| Linux | `$XDG_DATA_HOME/timetracker` (default `~/.local/share/timetracker`) |

`TIMETRACKER_DATA_DIR` overrides the folder. Inside it:

| File | What |
|---|---|
| `timetracker.sqlite3` | the database — one file, everything |
| `timetracker.sqlite3-wal`, `-shm` | SQLite write-ahead log; present while the app runs, merged on close |
| `timetracker-pre-vN.sqlite3` | automatic copy taken before a schema migration from version *N* |
| `timetracker-backup-YYYYMMDD-HHMMSS.sqlite3` | backups you take from Settings › Data |
| `timetracker-pre-restore-…sqlite3` | the copy taken before a restore |
| `timetracker.log` (+ `.1`…`.5`) | rotating log; nothing in it is ever transmitted |
| `instance.lock`, `show.request` | single-instance guard; harmless to delete when the app is not running |

Do **not** put the folder on OneDrive/Dropbox/iCloud: file-sync clients and SQLite's
WAL do not mix. Use *Back up now* (or copy the file while the app is closed).

## Opening it yourself

Any SQLite client works. With the command-line shell:

```bash
sqlite3 timetracker.sqlite3
sqlite> .mode column
sqlite> SELECT date, client, type, total_seconds/60.0 AS minutes, record_method, note
   ...> FROM v_session_log ORDER BY started_at_utc DESC LIMIT 20;
```

`v_session_log` is the friendly view: one row per entry with label names joined
and the record method spelled out. Prefer it for reading; write only through the
app (or through the tables below if you know what you are doing — the app
validates, SQLite only checks constraints).

## Tables

### `entry` — one recorded block of time

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | row id, stable across edits |
| `uuid` | text, unique | stable identity across export/import |
| `started_at_utc` | text | `YYYY-MM-DDTHH:MM:SSZ`, UTC |
| `ended_at_utc` | text | same format |
| `tz_name` | text | IANA zone the entry was recorded in, e.g. `Europe/Brussels` |
| `local_date` | text | `YYYY-MM-DD` in `tz_name` — the calendar day the entry belongs to |
| `duration_seconds` | integer ≥ 0 | **the measured duration — authoritative** |
| `paused_seconds` | integer ≥ 0 | total of the pauses inside a `STOPWATCH` entry (FR-212, since 1.1); wall-clock gap, not billed. `ended − started ≈ duration + paused` |
| `client_id` | integer, nullable | → `client.id` |
| `type_id` | integer, nullable | → `work_type.id` |
| `note` | text, nullable | ≤ 500 characters |
| `record_method` | text | `STOPWATCH` (timer), `QUICKADD` (Add Time matrix), `MANUAL` (log window form, and rows imported from CSV since 1.1) |
| `is_edited` | 0/1 | set when any field was changed after creation |
| `created_at`, `modified_at` | text | UTC timestamps |

**Read this twice:** `duration_seconds` is the fact. `started_at_utc` and
`ended_at_utc` are *anchors* for chronology. The timer measures with a
monotonic clock, so a DST change or a clock correction mid-timer never alters
the duration, and for Add Time entries the timestamps are assigned, not
observed. Do not compute durations as `end − start`; the app flags rows where
the two disagree by more than two minutes, it never "fixes" them.

Times in the app are shown in each entry's own `tz_name`, so an entry recorded
in Singapore keeps reading correctly after you fly home.

### `client`, `work_type` — the two label dimensions

| Column | Meaning |
|---|---|
| `name` | display name, first-entered casing |
| `name_norm` | casefolded, whitespace-collapsed; unique — `"nike"`, `"Nike "` and `"Nike"` are one label |
| `is_archived` | hidden from chips and combos, kept on historical entries |
| `is_pinned`, `colour` | reserved (not used in v1) |
| `created_at`, `last_used_at` | UTC |

Entries reference labels by id, so renaming a label renames it everywhere.
A label with entries cannot be deleted (`ON DELETE RESTRICT`) — archive it.

### `running_timer` — the timer that is running right now (one row, `id = 1`)

Persisted every 30 s (`heartbeat_at_utc`, `heartbeat_accrued_sec`). If the app
is killed, the next launch offers to recover an entry up to the last heartbeat.
`paused_since_utc` is set while the timer is paused; `paused_seconds` (v4) totals
the pauses already completed. A timer recovered while paused ends at the
pause start. Never edit this table.

### `setting` — key/value, JSON-encoded values

Everything in Settings, plus a few remembered UI states (`popover.last_mode`,
`app.autostart_offered`). Reminder settings (1.1) are `reminders.enabled`,
`reminders.minutes`, `reminders.days` (JSON list, 0 = Monday), `reminders.start`
and `reminders.end` (`HH:MM`, local). Export presets (1.1, FR-608) are one JSON
list under `export.presets`: `{name, fmt, columns, rounding_minutes, scope,
folder}` each; a malformed element is skipped, never fatal. Delete a row to get
the default back.

### `schema_migration`

One row per applied migration. `PRAGMA user_version` holds the current version
(4). The app refuses to open a database written by a newer version rather than
risk corrupting it.

## Indexes

`local_date`, `started_at_utc`, `(client_id, local_date)`, `(type_id, local_date)`,
and `(client_id, type_id, duration_seconds)` (covering; totals). The log window
filters and sorts in SQL against these — 50 000 rows stay under 200 ms.

## Export formats

**Log export** (Log window › Export): the filtered rows with columns
`Date, Start, End, Duration (decimal hours), Duration (h:mm), Client, Type, Record method, Note`.
Times are local to each entry. If rounding was chosen, the two Duration columns
carry the *billed* values and the footer (CSV) or the *Export info* sheet (XLSX)
states the increment and scope — the database is never changed by an export.

- CSV: UTF-8 with BOM, RFC 4180 quoting, CRLF, delimiter from your locale
  (`;` where the decimal mark is `,`) or Settings.
- XLSX: header frozen and filterable, decimal hours as numbers, `h:mm` as real
  Excel durations (`[h]:mm`) that sum, a `SUBTOTAL(9, …)` totals row.

**Full export** (Settings › Data › Export all data): every entry and every label.
`.json` includes settings; `.csv` is the raw `entry` rows with label names.

## Backups and restore

*Back up now* writes a consistent snapshot with SQLite's online-backup API
(safe while the app runs). *Restore* validates the file (integrity check, schema
not newer than the app), keeps a copy of the current data, swaps the file and
restarts the app.
