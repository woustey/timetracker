# Time Tracker

A tray-resident, local-only time tracker for people who bill or allocate their
time across several clients. Two ways to record time: a labelled **Start–Stop**
stopwatch, and an **Add Time** matrix that logs a finished block in three
clicks. Everything lives in one SQLite file on your machine. No account, no
network, no telemetry.

- Product requirements: [`docs/PRD-time-tracker.md`](docs/PRD-time-tracker.md)
- Technical design and milestones: [`docs/PRD-time-tracker-qt.md`](docs/PRD-time-tracker-qt.md)
- What was built, milestone by milestone: [`docs/MILESTONES.md`](docs/MILESTONES.md)
- Your data, explained: [`docs/DATA-FORMAT.md`](docs/DATA-FORMAT.md)

## Install

Download from the [Releases](../../releases) page.

| Platform | How |
|---|---|
| **Windows 10/11** | Run `TimeTracker-<version>-setup.exe` (per-user, no admin rights). Or unzip the portable build anywhere and run `timetracker.exe`. |
| **macOS 13+** | Open the `.dmg`, drag *Time Tracker* to Applications. The first time, **right-click › Open** (the build is not notarized). |
| **Linux** | `chmod +x TimeTracker-*.AppImage && ./TimeTracker-*.AppImage`, or unpack the `.tar.gz` and run `timetracker.dist/timetracker`. GNOME needs an AppIndicator extension to show tray icons; KDE, XFCE and LXQt work out of the box. |

The binaries are **not code-signed**. Windows SmartScreen will say "Windows
protected your PC" — click *More info* → *Run anyway*. That warning goes away
only with a paid certificate; see `docs/RELEASE-CHECKLIST.md`.

## The first minute

1. The app lives in the **system tray** (menu bar on macOS) as a clock icon.
   On first launch a welcome screen asks for your first few clients and whether
   to start at login; then the popover opens.
2. **Left-click** the icon → the popover. Pick a client and category, **Start**.
   Later, **Stop** writes the entry.
3. **Add Time** (button in the popover, or right-click › *Add Time…*): click
   `+6min`/`+15min`/`+30min`/`+45min` as often as needed, a category, a client,
   **Add**. Labels stay selected, so the next block is two clicks. Keys:
   `1–5` time, `Q W E R T` category, `A S D F G` client, `Tab` note, `Enter` add,
   `Ctrl+Z` undo, `Esc` close.
4. **Right-click** the icon for *Open log…* (filter, edit, export) and
   *Settings…*.

If you step away, sleep the laptop or lock the screen while a timer runs, you
get a prompt on return: keep the time, discard it, discard and stop, or log it
separately. If the app is killed, the next launch offers to recover the timer
up to the last 30-second heartbeat.

## Your data

One file, yours: `%LOCALAPPDATA%\TimeTracker\timetracker.sqlite3` on Windows,
`~/Library/Application Support/TimeTracker` on macOS,
`~/.local/share/timetracker` on Linux (`TIMETRACKER_DATA_DIR` overrides).
Durations are stored to the second; rounding happens only in exports and is
written into the export. Back up and restore from *Settings › Data*. The schema
is documented in [`docs/DATA-FORMAT.md`](docs/DATA-FORMAT.md) — `sqlite3` reads
it without the app. Don't put the folder on OneDrive/Dropbox.

## Running from source

Python 3.12+.

```
python -m venv .venv
.venv/Scripts/pip install -e .[dev]        # Windows
# .venv/bin/pip install -e .[dev]          # macOS / Linux
```

Launch (no console window):

```
.venv/Scripts/timetracker.exe              # Windows — a GUI script, built against pythonw
.venv/Scripts/pythonw.exe -m timetracker   # Windows — equivalent
# .venv/bin/timetracker                    # macOS / Linux
```

`python -m timetracker` also works but keeps a console attached; closing that
console kills the tray app, so use it for debugging only. Uncaught exceptions
go to `timetracker.log` in the data folder.

## Tests, checks, builds

```
.venv/Scripts/python -m pytest             # 470+ tests, headless Qt (offscreen)
.venv/Scripts/ruff check . && .venv/Scripts/mypy
python scripts/make_icons.py               # regenerate icon files from the painted clock
python scripts/build_dev.py                # PyInstaller --onedir (seconds)   → dist/dev/
python scripts/build_release.py            # Nuitka --standalone (minutes)   → dist/release/
```

The release workflow (`.github/workflows/release.yml`) runs on a `v*` tag and
produces the Windows installer + portable zip, the macOS DMG and the Linux
AppImage + tar.gz, smoke-testing each binary first. Measuring start-up and
idle cost of any build: `TIMETRACKER_MEASURE_BOOT=5 timetracker.exe` prints a
JSON line (boot seconds, RSS, idle CPU %) and exits.

## Platform notes

- **Windows**: the tray shows elapsed time in the tooltip only (FR-106 is a
  *should*). Sleep is detected instantly; lock is detected via the idle
  threshold (10 min by default).
- **macOS**: unsigned, so Gatekeeper warns once. Idle detection uses the Quartz
  HID event source — no Accessibility permission needed.
- **Linux**: tray support depends on the desktop (see above). Idle detection
  works on X11 and on GNOME/KDE Wayland; elsewhere Settings shows why it is
  unavailable, and sleep/wake detection still works.

## Licence

MIT. Qt/PySide6 is LGPLv3 and ships as replaceable dynamic libraries — see
`THIRD_PARTY_NOTICES.md`.
