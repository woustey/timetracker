# Time Tracker — build summary, M0 → M7

What was built, milestone by milestone, against PRD-02 §13; the decisions
taken along the way; and what was deliberately left out. Written for whoever
picks this up next (including a future you). The invariants that must not be
re-litigated are in `CLAUDE.md`; the schema is in `docs/DATA-FORMAT.md`.

**Where it landed:** 476 tests, ~8 500 lines of application code and ~5 400 of
tests, four runtime dependencies (PySide6, openpyxl, tzdata on Windows,
pyobjc-framework-Quartz on macOS), zero network calls, schema v3, CI green on
Windows/macOS/Ubuntu × Python 3.12/3.13. Built 11–15 September 2026.

| Milestone | Acceptance (PRD-02 §13) | Result |
|---|---|---|
| M0 Skeleton | CI green on three platforms; tray icon appears and persists | ✅ |
| M1 Data layer | repository suite green; migration empty→v1 idempotent | ✅ |
| M2 Start–Stop | kill -9 mid-timer, relaunch, recover within 30 s of truth | ✅ 12 s short of truth (one heartbeat) |
| M3 Matrix | 30-min entry in ≤ 4 clicks and < 5 s, measured | ✅ 3 clicks steady state |
| M4 Trust | sleep with a timer running; prompt on wake with the right duration | ✅ 11 min 06 s nap reported exactly |
| M5 Document | scenario S3 end to end; golden files; 50 000 rows responsive | ✅ every op < 200 ms |
| M6 Polish | keyboard traversal; screen-reader names; NFR-01/02/03 measured | ✅ boot 0.7 s, 75 MB, idle CPU ≈ 0 |
| M7 Ship | clean install on a fresh VM; first entry < 60 s undocumented | see release notes |

---

## M0 — Skeleton (11 Sep)

**Built:** `pyproject.toml` (ruff, mypy `--strict` on `core/` and `data/`,
pytest + pytest-qt), a three-OS × two-Python CI matrix with headless Qt, a
`QApplication` subclass that refuses to start without a system tray (FR-110,
minimal), a `QSystemTrayIcon` with three painted state icons and a native
*Quit* menu, and the two guard tests that hold the architecture together:
`test_layering.py` (nothing under `core/`/`data/` imports PySide6 or `ui/`) and
`test_no_network.py` (static import scan + a `sys.addaudithook` on `socket.*`
during an offscreen boot — NFR-05).

**Decisions:** public repo, `main`, plain venv + pip; icons painted at runtime
with `QPainter` (no `.qrc` build step); the idle icon got a white face after
the grey-on-grey first look.

## M1 — Data layer (11 Sep)

**Built:** the `Clock` protocol with `SystemClock` (injectable IANA zone — the
stdlib cannot name the zone on Windows, Qt can) and `FakeClock` (advances wall
and monotonic time separately, which is how DST/NTP steps are simulated);
frozen dataclasses; ISO-UTC helpers and `local_date_for`; the v1 DDL; a
discovered, contiguous, fully transactional migration runner with pre-migration
backups and refuse-if-newer; `LabelRepo` (both dimensions in one class, FR-402
normalisation, seed types, `ON DELETE RESTRICT`), `EntryRepo`, `TimerRepo`
(the heartbeat singleton), `SettingsRepo`; per-OS data paths. A drift guard
asserts that applying every migration equals the hand-written current DDL.

**Decisions:** one `Label` dataclass + `Dimension` enum; no backup for a
brand-new empty database; seed types only when the table is empty so
archiving "Phone" sticks; `duration_seconds` stored exactly as supplied and
never derived from timestamps (a test inserts a 2-hour span with a 600 s
duration and totals 600).

## M2 — Start–Stop (11 Sep)

**Built:** `TimerService` (monotonic elapsed, 1 s tick, 30 s heartbeat,
start/stop/discard, FR-203 restart-saves-first, FR-202 MRU defaults, labels and
note editable while running, recovery offer from a leftover row), `LabelService`,
the frameless popover anchored to the tray and clamped to the screen with
idle/running pages and editable label combos that create labels on commit
(FR-401), the recovery dialog, the FR-111 quit prompt, tray states and
tooltips, and a single-instance guard (FR-107) built on an OS file lock plus a
`show.request` file watched by `QFileSystemWatcher` — because `QLocalServer`
lives in `QtNetwork`, which NFR-05 forbids.

**Acceptance:** timer started 14:17:53, `Stop-Process -Force` at 14:19:05,
relaunch → recovery offered 60 s (last heartbeat 14:18:53), 12 s short of the
72 s truth. Also automated with a real file DB and a 1 s heartbeat.

**Decisions:** FR-111 "keep running in background" = cancel the quit (the
alternative silently loses everything after the last heartbeat); PRD-01 Q1:
Stop is never blocked on a label, the mandatory-labels setting gates only the
matrix's Add button.

## M3 — The matrix (11 Sep)

**Built:** `parse_duration` (the §5.5 grammar incl. `1,5h`), `anchor()` (§5.4
with midnight clamp — and a real bug found by the DST test: zone-aware
`timedelta` arithmetic is wall-clock arithmetic, so all spans are now computed
in UTC), Levenshtein near-duplicate offers (FR-403), `SettingsService`,
`EntryService.add_quick/undo_last`; the chip widget (checkable label chips with
a painted checkmark, time chips with a contribution badge and Shift-click
subtract), the four-column composer with Custom… cells promoting to chips, a
click-to-edit pending total, Add gating with a tooltip naming the unmet
condition, sticky labels, a 500-character note cap, the §9.3.5 keyboard map,
and a non-modal toast with Undo. The popover gained a matrix page (640 px) and
remembers its last page across launches.

**Acceptance:** first measurement was 6 clicks — the popover always opened on
the stopwatch page. Persisting the last-used page brought the steady state to
tray → `+30min` → `Add` = 3 clicks; re-measured ≤ 4 by the owner.

**Decisions:** digit keys resolve from the *physical* top-row key (native
virtual key / scan code) so `Shift+1` subtracts on AZERTY too; FR-403 fires only
when the shorter name is ≥ 4 characters; Esc dismisses and keeps the pending
total.

**Also:** the launcher problem. The venv's `pythonw.exe` redirector on the
owner's Python 3.13.0 execs the console `python.exe`, so a GUI launch still
opened a terminal. Fixed by `detach_orphan_console()` (frees a console whose
only client is this process, keeps one shared with a shell), a
`[project.gui-scripts]` entry point, a Desktop shortcut, and a crash log that
also captures stderr when there is no console.

## M4 — Trust (15 Sep)

**Built:** `IdleProvider` implementations — Windows (`GetLastInputInfo`), macOS
(Quartz HID), Linux X11 (`libXss` via ctypes) and Wayland (`QtDBus` → Mutter
IdleMonitor / freedesktop ScreenSaver) — behind a factory that returns
`Unavailable(reason)` rather than a broken stub; `PowerMonitor` (suspend by
tick drift, clock-set-back logged); `IdleMonitor` (15 s polling while running,
one outstanding `IdleSpan` that grows while away and freezes on input, suspend
feeding the same span); the four-way prompt (Toggl's dialogue); the 12-hour
"still running?" prompt; tray attention state with the prompt re-raised by a
tray click (FR-210).

**The subtle part:** the monotonic clock counts through sleep on Windows but not
on Linux, so PRD-02 §6's literal `accrued −= idle` would double-subtract on
Linux. `PowerMonitor` reports both the wall and monotonic away deltas, and the
outcomes are defined on what the user sees: *keep* ⇒ accrued includes the
whole span, *discard* ⇒ excludes it. Tests cover both platforms' behaviour.

**Acceptance:** an 11 min 06 s sleep reported as 666 s on wake; the owner chose
*Discard it* (and confirmed, after a moment's confusion between the two
"Discard…" buttons, that the app had done exactly that).

## M5 — The document (15 Sep)

**Built:** rounding (`round_up`, per-entry / per-group scopes, verified against
PRD-01 Appendix B), consistency and overlap flags; SQL-backed
filter/sort/paging with label names joined onto the page only and label sorting
via a `CASE` over ids; a one-scan `summary` for totals with a covering index
(schema v2); window-function overlap detection deferred to after the reset
paints; `EntryService` edits with a stated policy, `move_to_date`, `add_manual`,
a session undo stack for deletes; `ExportService` — CSV (UTF-8 BOM, RFC 4180,
locale delimiter, rounding footer) and XLSX (frozen header, autofilter, real
duration serials, `SUBTOTAL`, an *Export info* sheet) on a worker with its own
read-only connection; the log window (presets with an always-visible date range,
filters, search, sortable header, inline delegates, flags column with accessible
descriptions, Add entry… form, Delete/Undo, Export with rounding options,
footer totals).

**Acceptance:** scenario S3 walked by the owner and automated; four golden CSVs
byte-compared on three OSes; 50 000 synthetic rows — filter 47 ms, sort ~60 ms,
page 55 ms, search 130 ms.

**Decisions:** the proxy-model design in PRD-02 §8.3 was replaced by SQL for
NFR-04's sake; edit policy (duration moves the end; start/date shift both
anchors; end moves only the end; ⚠ on a ≥ 120 s disagreement, never
auto-corrected); a third record method **Manual** for the log form (schema v3,
table rebuild) at the owner's request; rounded exports carry billed values.
Field reports fixed: editable label combos in the Add form, entries added
outside the visible range now widen it and get selected, the range UI made
explicit.

## M6 — Polish (15 Sep)

**Built:** autostart providers (Windows Run key, macOS LaunchAgent plist, XDG
`.desktop`), `launch_command()`; label rename/archive/delete-if-unused;
`BackupService` (online-backup snapshots, validated restore with a pre-restore
copy and a relaunch, full export to JSON/CSV — FR-804); the settings dialog
(General · Timer · Export · Labels · Data) writing through immediately, with the
idle row showing the provider or why it is unavailable; theming (Fusion +
light/dark palette + one QSS, system follows the OS live); 12 h/24 h and
first-day-of-week; a first-run start-at-login offer; a stdlib diagnostics module
and a measurement mode.

**Acceptance:** a test walks the Tab chain of every surface and asserts every
interactive widget is reachable and named, and that chips expose `checked`
(one gap found: the log table lacked a name). Measured: boot 0.68 s with the
real tray (0.42 s offscreen), RSS 75 MB, idle CPU zero accounted ticks in 20 s,
popover 5 ms first / 1 ms after, commit→toast 1 ms.

**Skipped as *should*:** global hotkeys (FR-109), merge/pin/colour (FR-406–408),
stop-confirmation and minimum-duration settings.

## M7 — Ship (15 Sep)

**Built:** real icon files rendered from the painted clock (PNG set + a
hand-written PNG-in-ICO; `.icns` in CI); Nuitka `--standalone` release build
(no console, version info, Qt dynamically linked for LGPL §4d) and a PyInstaller
`--onedir` dev build; an Inno Setup per-user installer with Start Menu /
Desktop / start-at-login options that never touches the data folder; AppImage
and DMG scripts; a tag-triggered release workflow that builds all three, smoke
tests each binary in measurement mode, and publishes a GitHub Release; the
first-run flow merged into one welcome screen (clients → chips, start at login,
then the popover opens itself); README, `DATA-FORMAT.md` (NFR-10),
`RELEASE-CHECKLIST.md` (§11 manual checks, §12.3 signing, §12.4 LGPL), licence
and third-party notices, and this summary.

**Not done:** code signing (no certificates — SmartScreen/Gatekeeper will warn;
documented); hands-on testing of the macOS and Linux artefacts (built on CI
runners only; Linux is best-effort per R1).

**Release (16 Sep):** the first `v1.0.0` tag built Windows and failed macOS and
Linux; three fixes followed (`0cbdaf4` tzdata is win32-only, `f98901d` binary
renamed `timetracker.bin` off Windows so it no longer collides with the
`timetracker/` data directory, `1da5ae0` executable bits on the packaging
scripts and the `.app` picked over the intermediate `.dist`), each verified by
a `workflow_dispatch` dry run on `main` before the tag was moved to `1da5ae0`.
Published with five assets; CI-runner measurements: Windows 0.41 s / 69 MB,
Linux 0.63 s / 96 MB, macOS 1.98 s / 149 MB. Three manuals (user, developer,
product owner; Markdown + self-contained HTML) were added the same day.

**Post-release tidy-ups (16 Sep):** `launch_command()` resolves the executable
to its long path (`os.path.realpath`), so the Windows Run key no longer shows
the 8.3 name the installer launched the app with; the Nuitka build compiles the
package in `-m` mode (`--python-flag=-m` + the package directory) and only
forces in `timetracker.data.migrations` (loaded by name) — the "specify its
containing directory" and the 600-odd duplicate-tzdata warnings are gone. The
session handoff document lives in `docs/HANDOFF.md`.

---

## v1.1 — the PRD-01 §14 backlog (16 Sep)

Started after 1.0.0 shipped; the owner asked for all six §14 items in one
run, order chosen by the assistant: FR-212 → FR-702 → FR-608 → FR-805 →
FR-509 → FR-510.

**FR-212 pause/resume:** `TimerState.PAUSED`, `pause()` / `resume()` on
`TimerService`, schema v4 (`running_timer.paused_seconds`, rebuilt so the
drift guard holds), a fourth tray icon state, *Pause*/*Resume* in the popover
and the tray menu, recovery of a timer that died paused. The pause length is
the wall-clock gap (a chronology fact), never the monotonic delta — sleeping
through a pause on Linux would otherwise lose it. Tests: service (6), idle
monitor (2), migration (1), tray (2), popover (1).

**FR-702 reminders:** `ReminderService` (60 s check under the `Clock`; the
quiet period starts at the later of the last activity — timer state change,
entry change, launch, switching the setting on — and today's working-window
start; repeats every N minutes), five `reminders.*` settings, a *Remind me*
group on the Timer tab, `TrayIcon.show_message` + `message_clicked` →
popover. Balloon delivery is platform-dependent and not verified by tests
(`last_message` is). Tests: service (6), settings dialog (1), tray (1).

**FR-608 export presets:** `core/export_presets.py` (`ExportPreset`,
`PresetList`: validation, JSON, lenient load, case-insensitive names), stored
as one list under `export.presets`; the Export dialog grew the FR-603 column
tick-boxes, a folder row and *Save as preset…*; the log's *Export* menu lists
presets and `LogWindow.run_preset()` writes the current view without a dialog
to `folder/timetracker_<from>_<to>.<fmt>` (`-2`, `-3` … if taken); *Settings ›
Export* lists and deletes them. "Grouping" in the PRD's wording was read as
the rounding scope (FR-607 aggregated export stays out). Tests: core (4
functions, 9 cases), settings (1), log window (2).

**FR-805 CSV import:** `core/csv_import.py` (delimiter/header sniffing,
header-word mapping guesses, per-row parsing to `ParsedRow` or `RowError`,
ISO/DMY/MDY dates with an auto mode that switches to MDY only when a "day"
exceeds 12, 24 h and 12 h times, durations via `parse_duration` plus decimal
hours, rows without a start placed back to back from the workday start),
`ImportService` (labels resolved through `LabelService.get_or_create`, duplicate
guard `EntryRepo.exists_like`, commit through `EntryService.add_many` /
`EntryRepo.insert_many` in one transaction), `ImportCsvDialog` (mapping combos,
live preview, summary, skip-duplicates), *Import CSV…* on the log toolbar with
the range widened onto the import. Imported rows are `MANUAL`; a fourth record
method would have cost a schema rebuild for no user-visible gain. Deriving
`duration = end − start` is allowed here and only here: it is the source
tool's data, stored as the fact from then on. Tests: core (5), service (2),
log window (1).

**FR-509 day timeline:** `core/timeline.py` (`layout_day`: anchors clipped to
the local day, zero-length entries widened to a minute, greedy lane
assignment per overlapping cluster, gaps as the holes in the union of spans,
tracked vs. covered totals), `ui/views/day_view.py` (`DayCanvas` paints from
the palette — light and dark checked offscreen — with a per-client hue,
hatched gaps, a now line, hover and double-click; `DayView` adds the stepper
and totals) and `ui/views/window.py` (a tab per view, opened from the log's
*Day view* action on the selected row's day; double-click → `LogWindow.reveal`).
PRD-01 Q3 did not block: M3's anchoring already gives Add Time entries a
time-of-day. Tests: core (3), UI (4).

**FR-510 weekly grid:** `EntryRepo.totals_by_client_and_day` (one `GROUP BY
client_id, local_date` scan over the week), `core/weekgrid.py` (`week_days`
per the first-weekday setting, `build_week_grid` with rows by total and the
unlabelled row last, marginal totals), `ui/views/week_view.py` (`QTableWidget`,
bold today column, stepper, double-click → Day view). Tests: core (2), repo
(1), UI (1).

All six §14 items landed on 16 Sep; the manuals, DATA-FORMAT, release notes
and CLAUDE.md were updated with each. Not done in this pass: a version bump
and a release (owner's call), the product-owner manual's coverage table
(still describes 1.0.0), hands-on testing of the new UI on a real desktop
(offscreen renders of the Day and Week views were inspected).

---

## What is deliberately not in v1

Everything PRD-01 marks *S* or *C*: pause/resume, continue-from-entry, stop
sheet, minimum-duration confirmation, express mode, date stepper and day total
in the matrix, chip configuration, merge/pin/colour, split/merge entries, day
timeline, weekly grid, aggregated export, export presets, PDF, reminders,
rolling backups, CSV import, global hotkeys, tray text on macOS. And everything
in PRD-01 §3.2: teams, sync, invoicing, automatic capture, mobile, integrations.

## Lessons worth keeping

- The two guard tests (layering, no-network) cost an hour and paid for
  themselves every milestone — architecture stays honest without anyone
  remembering to check.
- Every clock-shaped bug was caught by `FakeClock`, never by a human: DST in
  anchoring, sleep vs. monotonic on Linux, the 32-bit tick wrap in
  `GetLastInputInfo`.
- Acceptance criteria phrased as *measurements* ("≤ 4 clicks", "< 200 ms",
  "within 30 s") turned into tests that then found real problems (the 6-click
  landing page, the 136 ms grouped scan).
- The owner's own hands found what tests could not: the console window, the
  unreadable grey icon, "cannot add ASICS", the unclear "Custom…" range.
- A platform you only build on CI is a platform you have not built. Every
  macOS/Linux packaging bug was invisible on Windows; the release workflow's
  `workflow_dispatch` dry run is now step 0 of the checklist, before any tag.
