# Time Tracker 1.0.0

A tray-resident, local-only time tracker for people who bill or allocate their
time across clients. No account, no network, no telemetry — one SQLite file
you own.

## What you get

- **Start–Stop**: a labelled stopwatch, one click from the tray. Monotonic
  timing (DST and clock changes never touch a duration), a 30-second heartbeat
  with crash recovery, sleep/lock/idle detection with the four-way prompt.
- **Add Time**: a four-column matrix that logs a finished block in three clicks —
  additive time chips, single-select category and client, custom fields that
  become chips, keyboard-complete, Undo.
- **The log**: filter, search, sort, edit inline, delete/undo, totals per client
  and type, overlap and edit markers; responsive at 50 000 entries.
- **Export**: CSV (Excel-friendly) and XLSX with real summable durations,
  optional rounding (6/10/15/30 min, per entry or per day × client × type) that
  is stated in the file and never changes your data.
- **Settings**: start at login, theme (system/light/dark), first day of week,
  12/24 h, idle threshold, mandatory labels, label management, backup/restore,
  full data export.

## Downloads

| Platform | File | Notes |
|---|---|---|
| Windows 10/11 | `TimeTracker-1.0.0-setup.exe` | per-user installer, no admin rights; or the portable `.zip` |
| macOS 13+ | `TimeTracker-1.0.0.dmg` | unsigned — right-click › Open the first time |
| Linux | `TimeTracker-1.0.0-x86_64.AppImage` or `.tar.gz` | GNOME needs an AppIndicator extension for the tray; best-effort |

The binaries are **not code-signed** (see `docs/RELEASE-CHECKLIST.md` §8).
Windows SmartScreen will show "Windows protected your PC" → *More info* → *Run
anyway*. macOS Gatekeeper: right-click the app → *Open*.

## Data

Your data is one file: `%LOCALAPPDATA%\TimeTracker\timetracker.sqlite3`
(macOS: `~/Library/Application Support/TimeTracker`, Linux:
`~/.local/share/timetracker`). Format documented in `docs/DATA-FORMAT.md`.
Back up from Settings › Data; don't put the folder on a sync service.

## Known limitations

Pause/resume, global hotkeys, merge/pin/colour for labels, CSV import, rolling
backups and the weekly grid are on the v1.1 list. The macOS and Linux builds
are produced by CI and have not been hand-tested on hardware.

Measured on the CI runners at release (`TIMETRACKER_MEASURE_BOOT`, cold
start, 3 s idle): Windows 0.41 s / 69 MB, Linux 0.63 s / 96 MB, macOS (Apple
silicon) 1.98 s / 149 MB. macOS sits at the edge of the ≤ 2 s / ≤ 150 MB
budgets: the figure is a first launch on a shared runner and includes the
whole Qt framework set; a warm launch on real hardware has not been measured.
