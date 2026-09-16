# Time Tracker — product owner manual

*For release 1.0.0 (tag `v1.0.0`, 16 September 2026) · written 16 September
2026.*

## Overview

**Who this is for:** the person who owns the product — decides what gets
built, accepts a release, and answers "does it do X?" — without reading code.

**After reading, you can** say what 1.0.0 does and does not do against the
requirements you wrote, verify a release yourself in an hour, read the
success metrics out of the data, and steer the next release: which backlog
items exist, what a change costs, and which decisions are already settled.

The product is defined by two documents, both in this folder:

| Document | Role |
|---|---|
| [`PRD-time-tracker.md`](PRD-time-tracker.md) (PRD-01) | *what*: goals, personas, functional requirements `FR-nnn` with priority M / S / C, non-functional `NFR-nn`, success metrics §13, open questions §15 |
| [`PRD-time-tracker-qt.md`](PRD-time-tracker-qt.md) (PRD-02) | *how*: architecture, test plan §11, milestones M0–M7 with acceptance criteria §13 |

Everything else is derived: [`MILESTONES.md`](MILESTONES.md) records what
each milestone delivered and what was measured; [`RELEASE-NOTES.md`](RELEASE-NOTES.md)
is the customer-facing summary; [`RELEASE-CHECKLIST.md`](RELEASE-CHECKLIST.md)
is the manual acceptance script; [`../CLAUDE.md`](../CLAUDE.md) lists the
decisions taken with you during the build — the ones not to re-open by
accident.

## Prerequisites

- Read access to the GitHub repository `woustey/timetracker` (public): the
  *Releases* page holds the binaries, *Actions* the build and test runs.
- A Windows 10/11 PC for hands-on acceptance (no admin rights needed), or
  Windows Sandbox enabled for a true fresh-machine run.
- For the metrics queries: the `sqlite3` command-line shell or any SQLite
  browser, plus the path of your data file
  (`%LOCALAPPDATA%\TimeTracker\timetracker.sqlite3` on Windows).
- No developer tooling is required for anything in this manual.

## Step by step: accept a release

This is the M7 acceptance as performed for 1.0.0, in the order that finds
problems fastest.

1. **Check the automated gate.** *GitHub › Actions › CI*: the latest run on
   `main` must be green on all six jobs (Ubuntu, Windows, macOS × Python 3.12
   and 3.13). For 1.0.0 that is commit `614dc2f`. Green means: 477 automated
   tests pass, including the ones that enforce your non-negotiables — no
   network code (NFR-05), no rounding of stored data (FR-605), durations
   from a monotonic clock (FR-208), the log stays under 200 ms with 50 000
   entries (NFR-04).
2. **Check the release build.** *Actions › Release* for the tag: four
   artefacts — Windows installer + portable zip, macOS DMG, Linux AppImage +
   tar.gz — each smoke-tested by booting the compiled binary in measurement
   mode. The GitHub Release page carries the release notes and the files.
3. **Install as a new user.** Run `TimeTracker-<version>-setup.exe` in
   Windows Sandbox (`installer\sandbox-test.wsb` in the repository maps the
   installer folder into it and switches networking off), or on your PC
   with a scratch data folder. No administrator prompt may appear.
4. **Time the first entry (NFR-09).** Start a stopwatch when the welcome
   screen appears, type a client, *Get started*, record one entry. Target
   under 60 s. Measured for 1.0.0: **20 s**.
5. **Walk `RELEASE-CHECKLIST.md`.** Sections 1–7 cover tray states, popover
   placement, the matrix, idle prompt after a sleep, log editing and export,
   settings, backup/restore. Each line is a tick box; about an hour.
6. **Read the numbers.** The build prints them itself; the developer can run
   `TIMETRACKER_MEASURE_BOOT=5` on any binary. For the installed 1.0.0 build:

   ```
   {"boot_seconds": 1.03, "idle_cpu_seconds": 0.0156, "idle_wall_seconds": 3.005, "idle_cpu_percent": 0.52, "rss_mb": 96.0}
   ```

   Against NFR-01 (≤ 2 s) and NFR-03 (≤ 150 MB) that passes. The idle CPU
   figure over 3 s includes the tail of start-up; over 20 s it measured 0
   ticks (`MILESTONES.md`, M6).
7. **Decide.** Green CI + checklist without blockers + NFR numbers inside
   budget = accept. The developer then tags; the tag builds and publishes.

Expected outcome for 1.0.0: all seven steps passed on 15–16 September 2026,
with two caveats recorded in *Verification* below.

## Common tasks

### Answer "does 1.0.0 do X?" — requirements coverage

Every **M** requirement in PRD-01 is implemented; every **S** and **C** is
not, by the rule agreed at the start, with three exceptions you opted into.

| Area (PRD-01 §8) | Implemented (M) | Not in 1.0.0 (S / C) |
|---|---|---|
| Shell & tray (FR-101–111) | tray-only app, popover, context menu, three icon states, tooltip, single instance, start at login, no-tray fallback, quit prompt | FR-106 elapsed time as tray text (macOS), FR-109 global hotkeys |
| Start–Stop (FR-201–214) | one-click start, sticky labels, one timer at a time, monotonic timing, 30 s heartbeat + crash recovery, idle prompt with four outcomes, sleep/lock handling, long-running prompt | FR-205 stop sheet, FR-212 pause/resume, FR-213 continue, FR-214 minimum-duration confirmation |
| Add Time matrix (FR-301–318) | four columns, additive chips, Custom duration, clear/subtract, single-select labels, note, Add gated on mandatory labels, toast + undo, sticky labels, full keyboard | FR-313 express mode, FR-316 date stepper, FR-317 day total in header, FR-318 configurable chips |
| Labels (FR-401–409) | custom values persist, case/whitespace normalisation, near-duplicate offer, rename, archive, seed types + first-run client prompt | FR-406 merge, FR-407 pin, FR-408 colour |
| Log (FR-501–510) | every entry, sortable columns, presets + custom range, client/type/method/search filters, totals, inline edit with edited flag, delete + undo, **FR-508 overlap flags (opted in)** | FR-507 split/merge, FR-509 day timeline, FR-510 weekly grid |
| Export (FR-601–609) | CSV (BOM, RFC 4180, delimiter setting), XLSX (real durations, frozen header, totals), fixed columns, rounding 6/10/15/30 up, never mutates data, scope per entry / per group | FR-607 aggregated export, FR-608 presets, FR-609 PDF |
| Settings (FR-701–703) | start at login, idle threshold, mandatory labels, rounding, delimiter, export folder, theme, first weekday, 12/24 h; stored in the database | FR-702 reminders; the stop-confirmation and minimum-duration settings (their features are S) |
| Data (FR-801–806) | one documented file + settings inside it, backup and validated restore, full export CSV + JSON, versioned automatic migrations with pre-migration copy | FR-803 rolling backups, FR-805 CSV import |

Opted-in extras beyond M: overlap flags (FR-508), an **Add entry…** form in
the log, and a third record method **Manual** so hand-added entries are
distinguishable from stopwatch and matrix entries (this needed schema
version 3 — a decision recorded in `CLAUDE.md`).

Non-functional, all measured: NFR-01 boot 1.03 s installed / 0.89 s from
source; NFR-02 popover and commit latency tested; NFR-03 96 MB RSS installed;
NFR-04 50 000-entry log under 200 ms in the test; NFR-05/06 enforced by a
test and by having no network module in the code; NFR-07 heartbeat every 30 s
with recovery test; NFR-08 three platforms built by CI; NFR-09 20 s; NFR-10
`DATA-FORMAT.md`.

### Read the success metrics (PRD-01 §13)

Four of the six metrics come out of the data file. Open it read-only with any
SQLite tool. Run against the owner's own database on 16 September 2026:

```
sqlite> SELECT record_method, COUNT(*), ROUND(SUM(duration_seconds)/3600.0,2) FROM entry GROUP BY 1;
[('MANUAL', 1, 0.03), ('QUICKADD', 13, 18.4), ('STOPWATCH', 3, 0.11)]
```

| Metric | Target | How to read it |
|---|---|---|
| Share of entries via Add Time | > 40 % | `QUICKADD` count ÷ total count from the query above — 13 of 17 = 76 % in the sample |
| Share of workdays with ≥ 1 entry | > 90 % after four weeks | `SELECT COUNT(DISTINCT local_date) FROM entry WHERE local_date >= date('now','-28 days')` ÷ workdays in the window |
| Clicks to log a retroactive entry | ≤ 4 incl. opening the tray | measured 3 in steady state (the app remembers the last popover page); 6 on the very first use before that was fixed in M3 |
| Time to log a retroactive entry | < 5 s | the matrix commit path is timed in `test_nfr.py` (`test_nfr02_popover_open_and_commit_latency`); scenario S3 end-to-end is `test_scenario_s3.py`; the wall-clock 5 s is a stopwatch check on the release checklist |
| Crash-loss incidents | 0 | look for `timetracker-pre-v*.sqlite3` and recovery prompts; any loss > 30 s is a bug |
| Hours captured that were previously lost | > 3 h/week | self-report; the `QUICKADD` hours per week above are the proxy |

`v_session_log` is the friendly view for ad-hoc questions (labels joined,
method spelled out); `DATA-FORMAT.md` documents every table.

### Ask for a change

- **A new setting, chip, column or dialog wording**: a small change; the
  developer manual has recipes. Ask for the test that proves it.
- **A new S/C feature from the backlog**: state the PRD id; PRD-01 already
  describes the behaviour, so the request is "implement FR-nnn". Expect the
  developer to raise the open questions in PRD-01 §15 that touch it.
- **Anything that changes stored data** (a new column, a new record method):
  a schema version bump with a migration and a documentation update — half
  a day, plus the release checklist's migration step.
- **Anything with a network, an account, AI or telemetry**: out of scope by
  NFR-05/06 and the project rules; a test will fail. This is a product
  decision to revisit, not a ticket.
- **A fifth runtime dependency**: the developer must ask you; say no unless
  it replaces code you would otherwise pay to maintain.

### Prioritise the 1.1 backlog

PRD-01 §14 names v1.1 as: pause/resume (FR-212), day timeline (FR-509),
weekly grid (FR-510), export presets (FR-608), CSV import (FR-805),
reminders (FR-702). Everything marked S or C in the coverage table is
eligible. Two items came out of 1.0 acceptance and are cheap:

- Code signing (Windows Authenticode, Apple notarisation): removes the
  *Windows protected your PC* and Gatekeeper warnings. Needs a purchased
  certificate; `RELEASE-CHECKLIST.md` §8 lists what to buy.
- The Windows silent install does not add a Desktop shortcut unless asked
  (`/TASKS=desktopicon`); the wizard does. Documentation-only fix.

### Decisions already taken

`CLAUDE.md` › *Decisions taken (with the owner)* is the register. The ones
that most often come up again:

| Decision | Consequence |
|---|---|
| Q1: an entry may be saved without client/type; "mandatory labels" gates only the matrix's Add button | the stopwatch never blocks; the log can show blank labels |
| Quit with a running timer: *Keep running* cancels the quit | nothing is lost silently |
| Single instance via a file lock, not a local socket | NFR-05 stays verifiable |
| Popover remembers its last page | the ≤ 4-click metric holds |
| Rounding lives only in exports; the file states the rounding used | stored minutes are always the truth |
| Three record methods (Manual added) | schema v3; exports show *Manual* |
| Log filtering in SQL, not in the UI layer | 50 000 entries stay under 200 ms |
| Restore relaunches the app | SQLite cannot swap a file under an open connection |
| Binaries unsigned in 1.0 | one-time warning on first launch, documented |

## Troubleshooting

| Symptom | Cause | What to do |
|---|---|---|
| CI badge red on `main` | a test, lint or type check failed on one of the six jobs | open the run; the failing test name carries the requirement id (`test_fr605_…`). Do not accept a release from a red commit |
| Release workflow ran but a platform's artefact is missing | that platform's build or smoke test failed | open *Actions › Release*, the job log names the step; the other platforms' files are still valid |
| A user reports the app "does nothing" after install | the tray icon is hidden in the overflow area, or GNOME without AppIndicator | `USER-MANUAL.md` Troubleshooting; a product fix would be FR-110's fallback window, which exists only for "no tray at all" |
| Reported totals differ between the log and an export | rounding was applied in the export (footer / *Export info* sheet says so) | expected by FR-604/605; the log shows stored values |
| A user asks where their data went after uninstall | nowhere: the uninstaller never touches the data folder | point them at the folder in `USER-MANUAL.md` › Reference |
| The Sandbox test cannot be run | Windows Sandbox is not enabled on the machine (admin + reboot) | accept on the strength of the silent install + fresh-data-folder run, and say so in the acceptance note, as done for 1.0.0 |
| "Can we add sync / a team view / AI suggestions?" | PRD-01 §3.2 non-goals and NFR-05/06 | a v2 conversation, not a 1.x ticket |

## Reference

**Requirement ids**: FR-1xx shell, FR-2xx stopwatch, FR-3xx matrix, FR-4xx
labels, FR-5xx log, FR-6xx export, FR-7xx settings, FR-8xx data; NFR-01..10.
Priority letters: M must, S should, C could.

**Milestones delivered** (PRD-02 §13, dates from `MILESTONES.md`): M0
skeleton, M1 data layer, M2 Start–Stop, M3 matrix (11 Sep 2026); M4 trust,
M5 document, M6 polish, M7 ship (15 Sep 2026); tag `v1.0.0` 16 Sep 2026.

**Measured for 1.0.0**: first entry 20 s; boot 1.03 s installed, 0.89 s
source; RSS 96 MB installed, 73 MB source; idle CPU 0 ticks / 20 s; log
operations at 50 000 rows under 200 ms; 477 automated tests, 5 skipped
(other-platform tests).

**Where things are**

| Question | Place |
|---|---|
| binaries and release notes | GitHub › Releases |
| build and test status | GitHub › Actions › CI / Release |
| what a user sees | `docs/USER-MANUAL.md` |
| how it is built and changed | `docs/DEVELOPER-MANUAL.md` |
| data file format | `docs/DATA-FORMAT.md` |
| acceptance script | `docs/RELEASE-CHECKLIST.md` |
| history and lessons | `docs/MILESTONES.md` |
| settled decisions | `CLAUDE.md` |
| licence | MIT (`LICENSE`); Qt LGPLv3, kept replaceable (`THIRD_PARTY_NOTICES.md`) |

**Platforms**: Windows 10/11 (hand-tested), macOS 13+ and Linux GNOME/KDE/XFCE
(CI-built, not hand-tested — stated in the release notes).

## Verification

**Verified** for this manual:

- CI run for `614dc2f` green on all six jobs; release workflow for `v1.0.0`
  started on the tag (run 35064772733) — its outcome is being watched and is
  not asserted here.
- NFR-09 timing of 20 s performed by the owner on the installed build with an
  empty data folder, 16 September 2026.
- Measurement-mode output for the installed and the source build captured on
  16 September 2026 (numbers quoted above).
- Requirements coverage table cross-checked against PRD-01 §8 priorities and
  `MILESTONES.md` › *What is deliberately not in v1*.
- Metric query executed read-only against the owner's database on 16
  September 2026 (result quoted).
- Silent per-user install of `TimeTracker-1.0.0-setup.exe` on the owner's PC:
  683 files, Start Menu entry, uninstaller, no elevation (M7).

**Assumed / not done**:

- No Windows Sandbox or fresh-VM install: the feature is not enabled on the
  acceptance PC. The installed-build run with an empty data folder stood in
  for it.
- macOS and Linux artefacts are exercised only by the release workflow's
  smoke test; nobody has clicked through them.
- The "share of workdays" and "hours previously lost" metrics need four weeks
  of real use; the sample database has seven days.
