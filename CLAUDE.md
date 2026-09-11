# Time Tracker — project invariants

Tray-resident time tracker. Product requirements: `docs/PRD-time-tracker.md`
(PRD-01, source of FR-/NFR- ids). Build document: `docs/PRD-time-tracker-qt.md`
(PRD-02). Milestones are PRD-02 §13. These rules are settled; do not re-open them.

## Architecture

- `src/timetracker/core/` and `src/timetracker/data/` import **neither PySide6
  nor anything from `ui/`**. `tests/test_layering.py` enforces this and must stay
  green. `services/` may use Qt signals but no widgets. `ui/` knows Qt, no SQL.
- Every service takes a `Clock` (`core/clock.py`) in its constructor.
  Production uses `SystemClock`; tests use `FakeClock`. Never call
  `datetime.now()` / `time.monotonic()` directly outside `SystemClock`.

## Time and durations

- Durations are measured with a **monotonic clock** (FR-208):
  `clock.monotonic() - monotonic_start`, accumulated into `accrued_seconds`.
- `duration_seconds` on an entry is **authoritative** and is **never derived from
  the timestamps**. `started_at_utc` / `ended_at_utc` are chronology anchors only.
- No monotonic value is ever persisted; `running_timer` stores `accrued_seconds`
  plus a heartbeat copy (`heartbeat_accrued_sec`) that crash recovery uses.
- `TimerService` is the only writer of the `running_timer` row and the only
  creator of `STOPWATCH` entries.

## Rounding

- Rounding is applied **at export only** and **never mutates a stored record**
  (FR-605, P2). Re-exporting with another increment yields a different file from
  the same rows. Scope (per entry / per day×client×type group) is applied before
  rounding.

## Stack

- Python 3.12+, PySide6 (Qt Widgets — **not QML**), stdlib `sqlite3` (WAL),
  stdlib `zoneinfo` + `tzdata` on Windows.
- **Four runtime dependencies total**: PySide6, openpyxl, tzdata (win32 only),
  pyobjc-framework-Quartz (darwin only). Declared only once first used.
  **Ask before adding a fifth.** Dev tools (pytest, pytest-qt, ruff, mypy) are
  not runtime dependencies.
- No AI features, no network calls, no telemetry (NFR-05/06).
  `tests/test_no_network.py` enforces NFR-05.

## Process

- Implement only requirements marked **M** for the current milestone; skip S and C.
- Where the spec is ambiguous or wrong, say so and ask — don't silently pick.
  PRD-01 §15 lists the open questions.
- Each milestone: plan → go → implement → tests (PRD-02 §11) → commit with the
  milestone id in the subject (`M1: ...`) → report against §13 acceptance → stop.

## Decisions taken (with the owner)

- Repo is public; default branch `main`; plain `venv` + `pip`.
- PRD-01 Q1: an entry may be saved with `client_id`/`type_id` NULL. Stop is
  never blocked on a label (P5); the "mandatory labels" setting gates only the
  Add Time matrix's Add button (FR-310).
- Tray icons are painted at runtime with `QPainter` (no `.qrc` build step) until
  real artwork exists.
- NFR-05 test = static import scan of `src/` for network modules + a
  `sys.addaudithook` on `socket.*` during an offscreen app boot.
- FR-111 "keep running in background" = cancel the quit; the app stays in the
  tray. (The alternative — quit and recover later — silently loses everything
  after the last heartbeat.)
- FR-107 single instance uses an OS file lock (`instance_lock.py`) plus a
  `show.request` file watched by `QFileSystemWatcher`. No `QtNetwork`/
  `QLocalServer` — NFR-05 forbids it.
- `SystemClock` takes an injected IANA zone name; `app.py` passes
  `QTimeZone.systemTimeZoneId()` because the stdlib cannot name the zone on
  Windows.
- Label chip order: pinned → most recently used → creation order.
- Popover width: 380 px on the stopwatch page, 640 px on the matrix page. The
  last-used page is persisted (`popover.last_mode`) so the matrix is one click
  from the tray; without that the ≤ 4-click budget (G1, M3 acceptance) fails.
- Matrix keyboard digits resolve from the *physical* top-row key (native
  virtual key / scan code) so Shift+1..5 subtracts on AZERTY too.
- FR-403 near-duplicate offer: edit distance ≤ 2, only when the shorter name
  is ≥ 4 chars (PRD-01 Q6).
- Esc in the matrix dismisses the popover (FR-315) and keeps the pending
  total; the "‹ Timer" button switches pages.
- Anchoring arithmetic is done in UTC: adding a timedelta to a zone-aware
  local datetime is wall-clock arithmetic and drops an hour across DST.

## Launching on Windows

- Entry point is a `[project.gui-scripts]` script (`timetracker.exe`, built
  against pythonw). The Desktop shortcut points at it.
- The venv `pythonw.exe` redirector on this Python 3.13.0 install execs the
  console `python.exe`, so a console can still appear. `platform/win32.py`
  `detach_orphan_console()` frees a console that has no other client
  (`GetConsoleProcessList == 1`) at startup; a console shared with a shell
  (`python -m timetracker` for debugging) is kept.
- Never launch the app from the chat's Run button: that terminal owns the
  process tree and kills it when closed.

## Local commands

```
py -3.13 -m venv .venv && .venv\Scripts\pip install -e .[dev]
.venv\Scripts\python -m pytest
.venv\Scripts\ruff check . && .venv\Scripts\mypy
.venv\Scripts\python -m timetracker
```
