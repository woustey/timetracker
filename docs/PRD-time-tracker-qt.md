# Time Tracker — Technical PRD & Implementation Plan (Qt 6 / PySide6)

| | |
|---|---|
| **Document** | PRD-02 · Technical design and build plan |
| **Version** | 1.0 |
| **Date** | 11 September 2026 |
| **Owner** | Wouter |
| **Status** | Draft for review |
| **Depends on** | `PRD-time-tracker.md` (PRD-01) — product requirements. FR-/NFR- identifiers below refer to that document. |

---

## 1. Purpose

PRD-01 defines *what* the product does without committing to a stack. This document commits: a cross-platform desktop application built on **Qt 6 via PySide6**, with **SQLite** as the store, packaged for Windows, macOS and Linux. It specifies the architecture, the schema, the platform abstractions, the packaging route and a milestone plan detailed enough to hand to an implementation agent or to work through solo.

---

## 2. Stack decision

### 2.1 Chosen stack

| Layer | Choice |
|---|---|
| Language | Python 3.12+ |
| UI toolkit | PySide6 (Qt 6.7 LTS or later), **Qt Widgets** |
| Store | SQLite via the stdlib `sqlite3` module, WAL journal |
| XLSX export | `openpyxl` |
| Timezones | stdlib `zoneinfo` + `tzdata` on Windows |
| Packaging | Nuitka (release), PyInstaller `--onedir` (development) |
| Tests | `pytest`, `pytest-qt` |

Total third-party dependency count: four. This is deliberate — a tray utility that must start in under two seconds (NFR-01) and run for years without maintenance cannot afford a large dependency graph.

### 2.2 Rationale

**Why Qt at all.** The product is defined by its tray presence (FR-101–FR-111). `QSystemTrayIcon` is the most mature cross-platform tray abstraction available: it covers Windows, macOS and Linux desktops implementing either the D-Bus StatusNotifierItem protocol (KDE, GNOME with extension, XFCE, LXQt) or the freedesktop XEmbed specification. Nothing in the Python or web-shell ecosystem matches it.

**Why PySide6 rather than PyQt6.** Licensing. PySide6 is LGPLv3; PyQt6 is GPLv3 or a commercial licence. If this product is ever distributed commercially or in closed source, PyQt6 forces a paid licence, and switching late is a broad refactor. PySide6 under LGPL permits closed-source distribution provided Qt is dynamically linked and replaceable — a constraint that interacts with packaging (see §12.4) and must be checked before any commercial release.

**Why PySide6 rather than Qt C++.** Development velocity for a solo build, straightforward access to platform APIs through `ctypes` and `pyobjc`, trivially testable business logic. The cost is startup time and bundle size, both of which Nuitka substantially mitigates (§12).

**Why not Electron or Tauri.** The Add Time matrix (§9.3 of PRD-01) is genuinely easier in HTML. Everything else — native tray menus, popovers anchored to the tray icon, platform idle APIs, global hotkeys, autostart, sub-2-second cold start, sub-150 MB idle RSS (NFR-01, NFR-03) — is harder. For an app that is 95 % chrome and 5 % grid, the trade is wrong.

**Why Qt Widgets rather than QML.** The UI is menus, popovers, dialogs, a chip grid and a data table. Widgets gives native menu integration, a mature model/view stack for the log window (`QAbstractTableModel` + `QSortFilterProxyModel` handles NFR-04's 50 000 rows without effort) and simpler accessibility. QML earns its place with animation-heavy, touch-first or embedded UIs; this is neither.

**Why stdlib `sqlite3` rather than `QtSql`.** Keeping the data layer in plain Python means the entire domain — durations, rounding, anchoring, migrations — is testable with `pytest` and no `QApplication`. `QtSql`'s payoff is `QSqlTableModel`, which would couple the log model directly to the database and make the filtering rules in FR-503 harder, not easier. A hand-written `QAbstractTableModel` over repository objects is the better shape here.

### 2.3 Rejected with reasons

| Option | Rejected because |
|---|---|
| Tauri + Rust | Best-in-class footprint, but tray, idle detection and global hotkeys all need per-platform Rust work, and the learning curve is spent on the 95 %, not the 5 %. Revisit only if footprint becomes a hard constraint. |
| .NET / WinUI | Excellent on Windows, wrong for cross-platform tray work. |
| Flutter desktop | Tray and menu-bar support is plugin-mediated and uneven. |
| Postgres / any server DB | Violates P1 (local-first) and adds an install dependency. |
| Plain CSV as the store | The brief asks for an exportable document, not a document-as-database. Concurrent edit, filtering, and referential integrity for labels all argue for SQLite, with CSV as an export target (FR-601). |

---

## 3. Architecture

### 3.1 Layers

```
┌──────────────────────────────────────────────────────┐
│  ui/          Widgets. Knows Qt. Knows no SQL.       │
│               Tray, popover, matrix, log, settings   │
├──────────────────────────────────────────────────────┤
│  services/    Application logic. Knows Qt signals    │
│               but no widgets. TimerService,          │
│               IdleMonitor, LabelService, Exporter    │
├──────────────────────────────────────────────────────┤
│  core/        Pure Python. No Qt, no SQL.            │
│               Domain types, duration maths,          │
│               rounding, anchoring, validation        │
├──────────────────────────────────────────────────────┤
│  data/        SQLite. Schema, migrations,            │
│               repositories. No Qt.                   │
├──────────────────────────────────────────────────────┤
│  platform/    OS specifics behind one interface each │
│               idle, autostart, hotkeys, power        │
└──────────────────────────────────────────────────────┘
```

The rule that makes this worth enforcing: `core/` and `data/` import neither PySide6 nor anything from `ui/`. That single constraint is what keeps the duration and rounding logic — the part where a bug costs the user money — testable in milliseconds without a GUI.

### 3.2 Repository layout

```
timetracker/
├── pyproject.toml
├── README.md
├── src/timetracker/
│   ├── __main__.py            # entry point, single-instance guard, bootstrap
│   ├── app.py                 # QApplication subclass, wiring, lifecycle
│   ├── core/
│   │   ├── models.py          # Entry, Client, WorkType, RunningTimer (dataclasses)
│   │   ├── clock.py           # Clock protocol: now_utc(), monotonic()
│   │   ├── duration.py        # parsing ("1h15", "0.75h", "90"), formatting
│   │   ├── rounding.py        # increment rounding, per-entry vs per-group
│   │   ├── anchoring.py       # Add Time -> start/end assignment (PRD-01 §9.3.4)
│   │   └── errors.py
│   ├── data/
│   │   ├── db.py              # connection factory, pragmas, transaction helper
│   │   ├── schema.py          # DDL for the current version
│   │   ├── migrations/        # 0001_initial.py, 0002_*.py ...
│   │   ├── entry_repo.py
│   │   ├── label_repo.py
│   │   ├── timer_repo.py      # running-timer singleton + heartbeat
│   │   └── settings_repo.py
│   ├── services/
│   │   ├── timer_service.py
│   │   ├── idle_monitor.py
│   │   ├── power_monitor.py   # sleep/wake via tick-drift
│   │   ├── label_service.py
│   │   ├── entry_service.py
│   │   ├── export_service.py
│   │   └── settings_service.py
│   ├── ui/
│   │   ├── tray.py
│   │   ├── popover.py
│   │   ├── quickadd/          # matrix: chip.py, column.py, matrix.py
│   │   ├── log/               # window.py, model.py, proxy.py, delegates.py
│   │   ├── dialogs/           # idle_prompt.py, stop_sheet.py, recovery.py
│   │   ├── settings_dialog.py
│   │   └── theme.py
│   ├── platform/
│   │   ├── base.py            # Protocols: IdleProvider, AutostartProvider, HotkeyProvider
│   │   ├── win32.py
│   │   ├── macos.py
│   │   ├── linux.py
│   │   └── factory.py         # returns the right implementation, or a no-op with a reason
│   └── resources/             # icons (.svg + rendered .png sets), .qrc
└── tests/
    ├── core/  data/  services/  ui/
    └── fixtures/
```

---

## 4. Data layer

### 4.1 Schema (v1)

```sql
PRAGMA journal_mode = WAL;      -- survives crash, allows concurrent read during export
PRAGMA synchronous = NORMAL;    -- WAL + NORMAL is crash-safe; FULL is unnecessary here
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE client (
    id           INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL,              -- display casing as first entered
    name_norm    TEXT    NOT NULL UNIQUE,       -- casefolded, whitespace-collapsed (FR-402)
    colour       TEXT,                          -- '#RRGGBB' or NULL
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
    uuid             TEXT    NOT NULL UNIQUE,   -- stable across export/import
    started_at_utc   TEXT    NOT NULL,          -- 'YYYY-MM-DDTHH:MM:SSZ'
    ended_at_utc     TEXT    NOT NULL,
    tz_name          TEXT    NOT NULL,          -- IANA, e.g. 'Europe/Brussels'
    local_date       TEXT    NOT NULL,          -- 'YYYY-MM-DD' in tz_name; denormalised
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

-- Singleton row holding the timer that is running right now.
CREATE TABLE running_timer (
    id                    INTEGER PRIMARY KEY CHECK (id = 1),
    started_at_utc        TEXT    NOT NULL,
    tz_name               TEXT    NOT NULL,
    accrued_seconds       INTEGER NOT NULL DEFAULT 0,  -- excludes paused time
    paused_since_utc      TEXT,                        -- non-NULL while paused
    client_id             INTEGER REFERENCES client(id),
    type_id               INTEGER REFERENCES work_type(id),
    note                  TEXT,
    heartbeat_at_utc      TEXT    NOT NULL,            -- FR-207
    heartbeat_accrued_sec INTEGER NOT NULL
);

CREATE TABLE setting (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL          -- JSON-encoded
);

CREATE TABLE schema_migration (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- The "session document" of the brief, as a view.
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
```

### 4.2 Schema notes

**`duration_seconds` is authoritative, not derived.** Deriving duration from `ended_at_utc − started_at_utc` at read time would reintroduce every clock-change and DST bug that FR-208 exists to prevent, and would make a paused entry (FR-212) unrepresentable. The timestamps are *anchors* for chronology and display; the duration is the measured fact. A consistency check (`|end − start − duration − paused| < 120 s`) runs in the log window and flags, but never silently corrects, discrepancies.

**`local_date` is denormalised on purpose.** Every grouping the product needs — daily totals, the day timeline, per-day rounding scope (FR-606) — is a grouping by *local* calendar day. Computing that from a UTC instant plus a timezone name in SQL is not practical; storing it makes the common query an index scan. It is recomputed whenever `started_at_utc` or `tz_name` changes.

**`tz_name` per entry, not per database.** A user who tracks time in Brussels and in Singapore in the same month needs each entry rendered in the zone where it happened. Storing the IANA name rather than a numeric offset also keeps historical entries correct across DST rule changes.

**No monotonic value is persisted.** A monotonic clock reading is meaningless across process restarts, so `running_timer` persists `accrued_seconds` (advanced by the in-process monotonic clock) plus a heartbeat copy. Crash recovery uses `heartbeat_accrued_sec`, which is the last value known to be durable.

**`ON DELETE RESTRICT`** enforces FR-405 at the storage layer: a label with entries cannot be deleted, only archived or merged.

### 4.3 Migrations

Versioned, forward-only, one module per version, each exposing `version: int` and `def upgrade(conn) -> None`. On launch:

1. Read `PRAGMA user_version`.
2. If it is behind the code's target, copy the database file to `timetracker-pre-v{n}.sqlite3` (FR-806) before touching anything.
3. Apply each pending migration inside a single transaction, writing a `schema_migration` row and bumping `user_version`.
4. If the database version is *ahead* of the code (the user downgraded), refuse to open and say so plainly rather than corrupting data.

Every migration gets a test that builds the schema at version *n−1*, inserts representative rows, upgrades, and asserts the data survived.

### 4.4 Connections and concurrency

- One `sqlite3.Connection` per thread; `check_same_thread=True` left at its default so misuse fails loudly.
- The UI thread owns the primary read/write connection. Entry writes are single-row inserts taking well under a millisecond — no worker needed, and moving them off-thread would only add a failure mode.
- Export (§9) and full-data operations run on a `QThreadPool` worker with their own read-only connection. WAL makes readers concurrent with the writer, so an export of 50 000 rows never blocks the timer.
- `row_factory = sqlite3.Row`; repositories convert to dataclasses at the boundary so that no `sqlite3.Row` escapes `data/`.

---

## 5. Core domain

### 5.1 Clock injection

```python
class Clock(Protocol):
    def now_utc(self) -> datetime: ...     # timezone-aware, UTC
    def monotonic(self) -> float: ...      # seconds, never decreasing
    def tz_name(self) -> str: ...          # current IANA zone
```

`SystemClock` in production; `FakeClock` in tests. Every service takes a `Clock` in its constructor. This is what makes "start a timer, advance eleven hours across a DST boundary, stop it, assert the duration" a fast unit test rather than a manual ritual.

### 5.2 Duration measurement (FR-208)

Elapsed time is `clock.monotonic() - monotonic_start`, accumulated into `accrued_seconds`. Wall-clock timestamps are recorded once at start and once at stop, for chronology only. The consequence: an NTP step, a manual clock change or a DST transition mid-timer changes the displayed start time interpretation but never the duration.

### 5.3 Rounding (FR-604–FR-606)

```python
def round_up(seconds: int, increment_minutes: int) -> int:
    """Round up to the next whole increment. Zero stays zero."""
    if increment_minutes <= 0 or seconds <= 0:
        return max(seconds, 0)
    step = increment_minutes * 60
    return ((seconds + step - 1) // step) * step
```

Scope is applied *before* rounding: in `PER_GROUP` mode, entries are summed by (local_date, client_id, type_id) and the sum is rounded once; in `PER_ENTRY` mode each entry is rounded individually. Both paths are pure functions over lists of entries, tested against the worked example in PRD-01 Appendix B.

### 5.4 Add Time anchoring (PRD-01 §9.3.4)

```python
def anchor(duration_s: int, target_date: date, existing: list[Entry],
           workday_start: time, clock: Clock) -> tuple[datetime, datetime]:
    """Assign start/end to a retroactively added entry."""
```

- `target_date == today` → `end = now` truncated to the minute, `start = end - duration`.
- otherwise → `start = max(end of last entry on target_date, workday_start)`, `end = start + duration`.
- If `end` would cross midnight, clamp to 23:59:59 and set a `needs_review` flag on the returned entry.

Pure, no I/O, exhaustively testable.

### 5.5 Duration parsing (FR-304)

Accepted inputs, all case-insensitive, whitespace-tolerant: `45` → 45 min · `1:30` → 90 min · `1h15` / `1h 15m` → 75 min · `0.75h` → 45 min · `90m` → 90 min · `1,5h` → 90 min (comma decimal separator, for a Belgian/European keyboard). Anything unparseable leaves the field in an error state and does not change the pending total.

---

## 6. Services

| Service | Responsibility | Key signals emitted |
|---|---|---|
| `TimerService` | The running-timer state machine: idle → running → (paused) → stopped. Owns the 1 s `QTimer` tick and the 30 s heartbeat `QTimer`. | `started(RunningTimer)`, `ticked(int seconds)`, `paused()`, `resumed()`, `stopped(Entry)`, `labels_changed()` |
| `IdleMonitor` | Polls the platform idle provider every 15 s. Raises the four-way prompt when the threshold is crossed; tracks whether a prompt is outstanding. | `idle_detected(int seconds, datetime since)`, `activity_resumed()` |
| `PowerMonitor` | Detects suspend/resume by tick drift: a 1 s `QTimer` whose observed wall-clock delta exceeds ~5 s implies the machine was suspended or the process was frozen. | `resumed_from_suspend(int away_seconds)` |
| `EntryService` | Create / edit / delete / split / merge entries; overlap detection; undo stack (FR-311, FR-506). | `entries_changed(list[uuid])` |
| `LabelService` | Label CRUD, normalisation, near-duplicate detection (FR-403), archive, merge, MRU ordering. | `labels_changed(dimension)` |
| `ExportService` | Builds the filtered, grouped, rounded row set and writes CSV or XLSX on a worker thread. | `export_progress(int pct)`, `export_finished(Path)`, `export_failed(str)` |
| `SettingsService` | Typed accessors over the `setting` table, with defaults and change notification. | `setting_changed(key)` |

**State machine — running timer**

```
        start()                  pause()                resume()
IDLE ───────────► RUNNING ◄──────────────► PAUSED ────────────┘
  ▲                 │  │
  │      stop()     │  └── heartbeat every 30 s → running_timer row
  └─────────────────┘
                    │  idle threshold crossed → IdlePrompt
                    │     ├─ keep        → no change
                    │     ├─ discard     → accrued -= idle_seconds
                    │     ├─ discard+stop→ accrued -= idle_seconds; stop()
                    │     └─ split       → stop() at idle start; create idle Entry
```

`TimerService` is the only component permitted to write the `running_timer` row, and the only one that may create a `STOPWATCH` entry. Recovery on launch: if a `running_timer` row exists and no other instance holds the lock, present the recovery dialog offering an entry of `heartbeat_accrued_sec` seconds ending at `heartbeat_at_utc`.

---

## 7. Platform abstraction

Three protocols in `platform/base.py`. `platform/factory.py` returns a working implementation or an explicit `Unavailable(reason)` — never a silently broken stub, so the settings UI can say *why* a feature is greyed out (P7).

### 7.1 Idle detection (FR-209)

| OS | Mechanism |
|---|---|
| Windows | `ctypes` → `user32.GetLastInputInfo` combined with `kernel32.GetTickCount64`. No permissions required. |
| macOS | `CGEventSourceSecondsSinceLastEventType(kCGEventSourceStateHIDSystemState, kCGAnyInputEventType)` via `pyobjc-framework-Quartz`. No Accessibility permission required for this call. |
| Linux / X11 | `XScreenSaverQueryInfo` from `libXss` via `ctypes`. |
| Linux / Wayland | D-Bus: `org.gnome.Mutter.IdleMonitor.GetIdletime` on GNOME, `org.freedesktop.ScreenSaver.GetSessionIdleTime` on KDE. Neither is universal. |
| Fallback | Idle detection is disabled and the setting shows "not available on this desktop session". Sleep/wake detection (§6 `PowerMonitor`) still works everywhere, so the worst common case — laptop lid closed with a timer running — remains covered. |

### 7.2 Autostart (FR-108)

| OS | Mechanism |
|---|---|
| Windows | A value under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`. Per-user, no elevation. |
| macOS | `SMAppService.mainAppService.register()` on macOS 13+; a `~/Library/LaunchAgents` plist as fallback. |
| Linux | A `.desktop` file in `~/.config/autostart/`. |

### 7.3 Global hotkeys (FR-109, *should-have*)

| OS | Mechanism |
|---|---|
| Windows | `RegisterHotKey` via `ctypes`, with a `QAbstractNativeEventFilter` catching `WM_HOTKEY`. |
| macOS | Carbon `RegisterEventHotKey` via `pyobjc`. Notably this does *not* require Accessibility permission, unlike global event monitoring. |
| Linux / X11 | `XGrabKey` via `python-xlib`. |
| Linux / Wayland | Not possible without compositor cooperation. Use the XDG desktop portal `GlobalShortcuts` interface where the portal version supports it; otherwise disable with an explanation. |

This is the least portable feature in the product, which is exactly why PRD-01 grades it *should* rather than *must*. Implement Windows first, macOS second, Linux behind a capability check.

---

## 8. UI implementation notes

### 8.1 Tray and popover

- `QSystemTrayIcon` with `isSystemTrayAvailable()` checked at startup (FR-110); on false, launch windowed mode with an explanation.
- `QApplication.setQuitOnLastWindowClosed(False)` — otherwise closing the log window kills a tray app, a classic and easily-missed bug.
- The popover is a frameless `QWidget` with `Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint`, positioned from `QSystemTrayIcon.geometry()` and clamped to `QScreen.availableGeometry()` so it never opens off-screen on a multi-monitor or rotated-taskbar setup. `Qt.Popup` gives dismiss-on-click-outside for free.
- On macOS the icon is set as a template image so it inverts correctly with the menu bar; on Windows, 16 px and on X11 22 px source sizes are provided in the resource bundle.
- Right-click menu is a real `QMenu` set via `setContextMenu()` — native, not a custom widget. On macOS, a context menu suppresses the double-click activation reason; the design must not depend on double-click.
- Keep a strong Python reference to the `QSystemTrayIcon`. A tray icon held only by a local variable is garbage-collected and vanishes — the single most common PySide6 tray bug.
- `activated(reason)` handling: `Trigger` → popover, `Context` → handled natively, `MiddleClick` → toggle timer. GNOME Shell does not deliver all activation reasons without extensions, so no action may be reachable *only* via a non-Trigger reason.

### 8.2 The Add Time matrix

- A `QGridLayout`, four columns, with a header row of `QLabel`s styled per the mockup and a `Custom…` cell at the foot of columns 1–3.
- `Chip` is a `QToolButton` subclass with `checkable` set for the Type and Client columns and a custom paint for the selected fill, a checkmark glyph and a contribution-count badge on Time chips.
- `QButtonGroup` with `exclusive=True` per label column gives radio semantics (FR-306/307) with no bookkeeping.
- Time chips are *not* in a button group: they emit `duration_added(seconds)` (or negative on Shift-click), and the composer's `pending_seconds` is the single source of truth, displayed in the header and click-to-edit.
- `Custom…` swaps the cell's widget for a `QLineEdit` inside a `QStackedWidget`; `returnPressed` commits, `editingFinished` without text reverts.
- Keyboard accelerators (PRD-01 §9.3.5) are `QShortcut`s scoped to the matrix widget (`Qt.WidgetWithChildrenShortcut`), so they never leak to the log window.
- The commit toast is a child widget with a `QGraphicsOpacityEffect` and a `QPropertyAnimation`, carrying an Undo button wired to `EntryService.undo_last()` — not a `QMessageBox`, which would block (P5).

### 8.3 Log window

- `EntryTableModel(QAbstractTableModel)` over a list of `Entry` dataclasses, backed by paged repository queries.
- `QSortFilterProxyModel` subclass for the date-range, client, type, method and text filters (FR-503).
- `QTableView` with `setUniformRowHeights(True)` and no per-row widgets — this is what keeps NFR-04 (50 000 rows, sub-200 ms) achievable.
- Totals in the footer are computed by SQL aggregate over the *filter predicate*, not by summing the loaded page.
- Inline editing through `QStyledItemDelegate` subclasses: a duration editor accepting the §5.5 grammar, and combo editors for the label columns.
- Edited and overlapping rows are marked by a delegate-painted glyph plus an accessible description — colour is never the sole signal (PRD-01 §9.5).

### 8.4 Theming

A single `theme.py` producing a QSS string from a palette derived from `QGuiApplication.styleHints().colorScheme()`, so light/dark follows the system by default with a manual override in settings. No third-party theme package.

---

## 9. Export implementation

- **CSV** — `csv.writer` with `newline=''`, encoded `utf-8-sig`. The BOM is what makes Excel on Windows open a UTF-8 CSV correctly, and its absence is the single most common "my accented client names are mangled" complaint. Delimiter defaults to the locale's list separator (`;` in a Belgian/European Excel), overridable in settings.
- **XLSX** — `openpyxl`. Durations are written as real values, not strings: decimal hours as a float in one column, and an Excel duration serial (`seconds / 86400`) with number format `[h]:mm` in another, so the recipient can sum them. Header row frozen and auto-filtered, a totals row using `SUBTOTAL(9, …)` so it respects filtering, and a metadata sheet recording the filter, the rounding increment and the rounding scope (FR-604).
- Both run on a `QThreadPool` worker with a read-only connection, reporting progress and never blocking the tray.
- Writing to a path currently open in Excel raises `PermissionError` on Windows; catch it and offer an alternative filename rather than failing opaquely (PRD-01 §10).
- Golden-file tests: a fixed fixture database exported and byte-compared against a checked-in expected CSV, which catches accidental column, ordering or formatting changes.

---

## 10. Error handling, logging and diagnostics

- A global `sys.excepthook` and a `qInstallMessageHandler` route everything to a rotating log file (5 files × 1 MB) under the platform's standard app-data directory. Nothing is ever transmitted (NFR-06).
- An unhandled exception shows a non-fatal dialog with a "copy details" button and, critically, **does not stop the running timer** — the timer state lives in the database, not in the widget tree.
- A "reveal data folder" and "export diagnostics" action in settings, so support is a file the user chooses to send, not telemetry.

---

## 11. Testing strategy

| Level | Scope | Tooling |
|---|---|---|
| Unit — `core/` | Duration parsing and formatting, rounding (both scopes, against PRD-01 Appendix B), anchoring including the midnight-clamp case, DST-crossing durations via `FakeClock`. | `pytest` |
| Unit — `data/` | Repository CRUD against `:memory:`; every migration applied to a populated prior-version schema; constraint enforcement (`ON DELETE RESTRICT`, the `record_method` check). | `pytest` |
| Service | Timer state machine under a fake clock, including crash recovery from a synthesised heartbeat row; idle-prompt outcomes; overlap detection; undo. | `pytest` + fakes for platform providers |
| UI | Matrix interactions: additive time, Shift-subtract, exclusivity, custom-field promotion to a chip, Add enablement rules, keyboard map. Log filtering and sorting. | `pytest-qt` |
| Golden file | CSV and XLSX export byte/structure comparison. | `pytest` |
| Property | `round_up` is monotonic and never returns less than its input; anchoring never produces a negative duration or an end before its start. | `hypothesis` (optional) |
| Manual / platform | Tray behaviour, popover positioning on multi-monitor, autostart, sleep/wake, idle on each target desktop. A written checklist per release — this part cannot be automated cheaply. | Checklist |
| Guard | A test asserting no module under `core/` or `data/` imports PySide6, and a test asserting the process opens no sockets (NFR-05). | `pytest` |

CI: GitHub Actions matrix over Windows, macOS and Ubuntu; `ruff` and `mypy --strict` on `core/` and `data/`; headless Qt tests with the `offscreen` platform plugin.

---

## 12. Packaging and distribution

### 12.1 Build tooling

| Use | Tool | Why |
|---|---|---|
| Development iteration | PyInstaller `--onedir` | Builds in seconds. Avoid `--onefile`: it unpacks to a temporary directory on every launch, which costs roughly 1.8 s of startup against Nuitka's ~0.08 s for a comparable program — unacceptable for a tray app expected to appear instantly (NFR-01). |
| Release | Nuitka `--standalone` | Compiles to C, producing a materially smaller bundle (roughly 10–30 MB against PyInstaller's 25–60 MB for a simple app) with far faster startup. Build time is minutes rather than seconds, which is fine for a release step. |

### 12.2 Installers

| OS | Artefact |
|---|---|
| Windows | Inno Setup installer, per-user install (no elevation), Start Menu shortcut, optional "start at login" checkbox writing the Run key. |
| macOS | `.app` bundle in a DMG, `LSUIElement=true` in `Info.plist` so no Dock icon appears, hardened runtime, code-signed and notarised. |
| Linux | AppImage as the primary artefact; a Flatpak manifest as a later addition. |

### 12.3 Signing

Windows SmartScreen and macOS Gatekeeper both treat unsigned binaries badly, and PyInstaller output in particular draws antivirus false positives. Budget for an Authenticode certificate and an Apple Developer ID before any distribution beyond the author's own machines. For a personal build this is deferrable; for anything shared it is not.

### 12.4 Licence compliance

PySide6 is LGPLv3. Distributing a closed-source application under LGPL requires that the user can replace the Qt libraries — satisfied by dynamic linking, which `--standalone` bundling preserves but which must be verified for whatever Nuitka configuration is finally used, along with shipping the LGPL text and the Qt source offer. If the application stays open-source or personal, this is moot. **Decide before the first external release, not after.**

---

## 13. Milestones

Each milestone ends in something runnable. Acceptance criteria are the gate.

| # | Milestone | Contents | Acceptance |
|---|---|---|---|
| **M0** | Skeleton | Repo, `pyproject.toml`, ruff/mypy/pytest, CI matrix, tray icon that shows a menu and quits cleanly. | CI green on three platforms; the tray icon appears and persists (no GC bug). |
| **M1** | Data layer | Schema, migration runner, repositories, `Clock`, dataclasses. No UI. | Full repository test suite green; migration from empty to v1 idempotent. |
| **M2** | Start–Stop | `TimerService`, popover idle/running states, entry creation, heartbeat, recovery dialog. | `kill -9` mid-timer, relaunch, recover an entry within 30 s of truth. |
| **M3** | The matrix | Chip widget, four-column composer, additive time, exclusivity, custom fields promoting to chips, toast + undo, keyboard map. | Log a 30-minute entry in ≤ 4 clicks and < 5 s, measured. Full `pytest-qt` suite green. |
| **M4** | Trust | Idle detection on all three platforms (with graceful unavailability), `PowerMonitor`, monotonic durations, DST test, long-running prompt. | Sleep the laptop for 30 min with a timer running; the prompt appears on wake with the correct away duration. |
| **M5** | The document | Log window: model, proxy filters, search, inline edit, delete, totals, overlap flags. CSV + XLSX export with rounding and both scopes. | PRD-01 scenario S3 end to end; golden-file tests green; log window responsive at 50 000 synthetic rows. |
| **M6** | Polish | Settings dialog, autostart, global hotkeys (Windows + macOS), theming, accessibility pass, label rename/archive/merge, backup/restore. | Accessibility: full keyboard traversal, screen-reader names on chips. NFR-01/02/03 measured and met. |
| **M7** | Ship | Nuitka release builds, installers, signing (if distributing), README and data-format documentation, first-run experience. | Clean install on a fresh VM per platform; first entry recorded within 60 s without documentation (NFR-09). |

Suggested split for solo evening-and-weekend work: M0–M2 is the first useful build and is worth reaching before anything else is polished. M3 is the differentiating feature and deserves the most design attention. M4 is unglamorous and is where trust in the tool is actually won.

---

## 14. Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Tray behaviour is inconsistent across Linux desktops; GNOME needs an extension for a full StatusNotifierItem experience and does not deliver all activation reasons. | High | Medium | Never make an action reachable only via a non-`Trigger` activation. Windowed fallback (FR-110). Treat Linux as best-effort and say so in the README. |
| R2 | Global hotkeys are not portable to Wayland. | High | Low | Graded *should*. Capability-checked, with an honest "unavailable in this session" message. |
| R3 | PyInstaller/Nuitka output flagged by antivirus; Windows SmartScreen warnings. | Medium | Medium | Code-sign for any distribution; prefer Nuitka; submit false-positive reports to vendors. |
| R4 | LGPL obligations conflict with a future closed-source release. | Low | High | §12.4 — resolve before the first external release. |
| R5 | Idle detection unavailable on some Wayland sessions, silently degrading the product's trustworthiness. | Medium | Medium | Explicit `Unavailable(reason)` surfaced in settings; `PowerMonitor` covers the sleep case everywhere. |
| R6 | Python startup time creeps past the 2 s target as dependencies accumulate. | Medium | Medium | Keep the dependency count at four; lazy-import `openpyxl` only at export; measure cold start in CI as a regression test. |
| R7 | SQLite file placed on OneDrive/Dropbox by a user who wants it "backed up", producing lock contention and corruption. | Medium | High | Default to the platform app-data directory; detect a known-sync path and warn; document that backup means FR-802, not folder sync. |
| R8 | The matrix's additive-time semantics confuse users who expect a single-select duration. | Medium | Medium | The pending total is displayed large and permanently; chips show a contribution badge; the first-run tour covers it in one sentence. Validate in the M3 usability check. |
| R9 | Scope creep into project hierarchies, rates and invoicing before v1 ships. | High | High | PRD-01 §3.2 is the contract. Re-open only after v1.0 with usage data. |

---

## 15. Dependencies

| Package | Licence | Purpose | Notes |
|---|---|---|---|
| PySide6 | LGPLv3 | UI toolkit | See §12.4 |
| openpyxl | MIT | XLSX export | Lazy-imported |
| tzdata | Apache 2.0 | IANA timezone database | Windows only; POSIX systems use the system database |
| pyobjc-framework-Quartz | MIT | macOS idle + hotkeys | macOS only |
| python-xlib | LGPL | X11 hotkeys | Linux only, optional |

Development only: `pytest`, `pytest-qt`, `ruff`, `mypy`, `nuitka`, `pyinstaller`, optionally `hypothesis`.

---

## Sources

- [Qt 6 — QSystemTrayIcon class reference (platform notes, activation reasons, GNOME Shell caveat)](https://doc.qt.io/qt-6/qsystemtrayicon.html)
- [Qt for Python — QSystemTrayIcon (PySide6)](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSystemTrayIcon.html)
- [PythonGUIs — Fixing system tray icons not showing on Windows with PyQt6/PySide6](https://www.pythonguis.com/faq/system-tray-examples-not-showing-up-on-windows-10/)
- [Microsoft Learn — GetLastInputInfo function](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getlastinputinfo)
- [Nuitka vs PyInstaller vs cx_Freeze — packaging comparison (2026)](https://blog.thoughtparameters.com/post/nuitka_vs_pyinstaller_python_packaging/)
- [pyqtkeybind — global hotkey bindings for Qt apps on Windows and Linux](https://github.com/codito/pyqtkeybind)
- [PythonGUIs — Packaging PySide6 applications for Windows](https://www.pythonguis.com/tutorials/packaging-pyside6-applications-windows-pyinstaller-installforge/)
