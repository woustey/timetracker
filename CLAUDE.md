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
- Sleep vs. monotonic clock differs per OS (Windows counts through sleep,
  Linux `CLOCK_MONOTONIC` does not). `PowerMonitor` reports both the wall and
  the monotonic away delta; `IdleSpan.counted_seconds` is what the timer
  already accrued. Idle outcomes are defined on the wall span: keep ⇒ accrued
  includes it, discard ⇒ accrued excludes it. Never "accrued −= idle" blindly.
- "Log separately" stops the timer at the idle start and writes the away span
  as its own STOPWATCH entry (same labels, note `Idle`), per PRD-02 §6.
- Wayland idle uses `PySide6.QtDBus` (ships with PySide6; not a network
  module). Linux providers raise without a desktop; the factory returns
  `Unavailable(reason)`.
- An unanswered idle prompt stays outstanding (FR-210): tray shows the
  attention badge and a tray click re-raises the dialog instead of the popover.
- Log filtering and sorting are SQL (`EntryRepo.export_rows`: filter/sort/limit
  first, join names onto the page; label sort via a `CASE` over ids), not a
  `QSortFilterProxyModel` — a Python proxy over 50 000 rows misses NFR-04. The
  model pages with `fetchMore`; totals come from one grouped scan
  (`EntryRepo.summary`, covering index `idx_entry_totals`, schema v2). The
  overlap pass (FR-508) runs on a zero-timer after the reset paints.
- Edit policy (FR-505): duration edit keeps start and moves end; start/date
  edit shifts both anchors; end edit moves only the end. `|end−start−duration|
  ≥ 120 s` shows ⚠, never auto-corrects.
- Record methods are three (schema v3, owner's request): `STOPWATCH`
  (Start-Stop), `QUICKADD` (Add Time matrix), `MANUAL` (the log window's Add
  entry… form). PRD-01 §7 lists two; the third is a deliberate extension.
- Rounded exports carry the *billed* values in the two Duration columns; the
  increment and scope are stated in the CSV footer / XLSX "Export info" sheet.
  Per-group uplift is booked on the group's last line. CSV goldens live in
  `tests/fixtures`; regenerate deliberately with `UPDATE_GOLDENS=1`.
- The log's date range is always visible ("from … to …"); editing a date
  switches the preset to Custom range. Adding an entry outside the range
  widens it and selects the row.
- M6 skipped the *should* items §13 lists: global hotkeys (FR-109), merge /
  pin / colour (FR-406–408), stop-confirmation and minimum-duration settings.
- Autostart (FR-108): Windows Run key, macOS LaunchAgent plist (SMAppService
  would need a fifth dependency), XDG `.desktop`. `launch_command()` picks the
  frozen exe, the GUI script, or `pythonw -m timetracker`. Offered once on
  first run (non-modal); the answer is remembered either way.
- Restore (FR-802) validates the file (`integrity_check`, schema not newer),
  snapshots the live DB first, copies over, then relaunches the process:
  SQLite cannot swap the file under an open connection.
- Theme: Fusion + light/dark palette + one QSS string; "system" follows
  `QStyleHints.colorScheme()` live. Time format is a UI-layer switch
  (`ui/formatting.py`) read at boot and on change.
- NFR-01/03 harness: `TIMETRACKER_MEASURE_BOOT=<idle s>` boots, idles, prints
  one JSON line and exits; `TIMETRACKER_ASSUME_TRAY=1` skips the tray check so
  it runs headless. `diagnostics.py` is stdlib only. Measured on this laptop:
  boot 0.68 s (real tray), RSS 75 MB, idle CPU 0 ticks / 20 s.
- `EntryRepo.summary` uses `NOT INDEXED` when a note search is present: the
  planner would otherwise walk the covering index and look up every row.
- Packaging (M7): `scripts/build_release.py` (Nuitka standalone; openpyxl and
  tzdata forced in because they are lazy/data; Qt stays dynamic for LGPL §4d),
  `scripts/build_dev.py` (PyInstaller onedir, never onefile), Inno Setup
  script in `installer/`, AppImage/DMG scripts, tag-triggered
  `.github/workflows/release.yml`. Icons are rendered files under
  `src/timetracker/resources/` (`scripts/make_icons.py`); the tray still paints
  at runtime. Binaries are unsigned; `docs/RELEASE-CHECKLIST.md` §8 says what
  to buy.
- First run (M7): one welcome dialog — clients (one per line → chips), start at
  login — then the popover opens itself. `app.autostart_offered` records it.
- Docs to keep current when behaviour changes: `README.md`,
  `docs/DATA-FORMAT.md` (NFR-10), `docs/RELEASE-CHECKLIST.md`,
  `docs/RELEASE-NOTES.md`, `docs/MILESTONES.md` (the build history), and the
  three manuals `docs/USER-MANUAL.md`, `docs/DEVELOPER-MANUAL.md`,
  `docs/PRODUCT-OWNER-MANUAL.md` (each ends with a Verified/Assumed list —
  keep it truthful).

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
