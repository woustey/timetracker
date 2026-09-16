# Time Tracker — developer manual

*For the 1.0.0 code base (tag `v1.0.0`) · written 16 September 2026 ·
commands shown were run on Windows 11 with Python 3.13.0; the macOS/Linux
form is given where it differs.*

## Overview

**Who this is for:** a developer who knows Python and git, has not seen this
repository before, and has to change it — fix a bug, add a setting, add a
column, cut a release.

**After reading, you can** set up the repository, run the checks that gate a
commit, place a change in the right layer without breaking the invariants the
tests enforce, and build the distributable binaries.

The app is a tray-resident time tracker: PySide6 (Qt Widgets, no QML) on top
of stdlib `sqlite3`. Everything the code does is specified in two documents
that the code cites by id:

- [`PRD-time-tracker.md`](PRD-time-tracker.md) (PRD-01): product
  requirements, `FR-nnn` / `NFR-nn` ids, open questions in §15.
- [`PRD-time-tracker-qt.md`](PRD-time-tracker-qt.md) (PRD-02): technical
  design, test plan §11, milestones §13.

[`../CLAUDE.md`](../CLAUDE.md) is the short list of invariants and decisions
taken with the owner. Read it before changing anything; it is the contract
the tests enforce. [`MILESTONES.md`](MILESTONES.md) is the build history and
explains *why* several things look the way they do.

## Prerequisites

| Tool | Version used | Check with |
|---|---|---|
| Python | 3.13.0 (3.12 is the minimum and is in CI) | `py -3.13 --version` |
| git | any recent | `git --version` |
| PySide6 | 6.11.2 (installed by pip) | `.venv\Scripts\python -c "import PySide6; print(PySide6.__version__)"` |
| openpyxl | 3.1.5 (installed by pip) | same pattern |
| Inno Setup 6 | only to build the Windows installer | `winget install JRSoftware.InnoSetup` |

Runtime dependencies are **four**: PySide6, openpyxl, tzdata (Windows only),
pyobjc-framework-Quartz (macOS only). Adding a fifth is an owner decision —
ask first. Dev tools (pytest, pytest-qt, ruff, mypy) live in the `dev` extra;
Nuitka and PyInstaller in the `build` extra.

## Step by step: from clone to a merged change

1. **Clone and create the environment.**

   ```powershell
   git clone https://github.com/woustey/timetracker.git
   cd timetracker
   py -3.13 -m venv .venv
   .venv\Scripts\pip install -e .[dev]
   ```

   Output: pip lists PySide6, openpyxl, tzdata, pytest, pytest-qt, ruff, mypy
   and their dependencies, ending in `Successfully installed …`. On
   macOS/Linux use `python3 -m venv .venv && .venv/bin/pip install -e .[dev]`.

2. **Run the full check set.** All three must be clean before a commit.

   ```powershell
   .venv\Scripts\python -m pytest -q
   ```

   Output:

   ```
   ..........................................ss..ss........................ [ 89%]
   ..................................................                       [100%]
   477 passed, 5 skipped in 27.39s
   ```

   The 5 skips are platform-specific tests (macOS/Linux providers) that do not
   run on Windows. Qt runs offscreen (`QT_QPA_PLATFORM=offscreen` is set in
   `conftest.py`), so no windows appear.

   ```powershell
   .venv\Scripts\ruff check .
   ```

   Output: `All checks passed!`

   ```powershell
   .venv\Scripts\mypy
   ```

   Output: `Success: no issues found in 23 source files` — mypy is strict on
   `core/` and `data/` only (see `[tool.mypy]` in `pyproject.toml`).

3. **Run the app from source** to see your change. Use the GUI script, not
   the chat/IDE "run" button: a console that owns the process tree kills the
   tray app when it closes.

   ```powershell
   .venv\Scripts\timetracker.exe
   ```

   Output: nothing on the console; the clock icon appears in the tray within a
   second. `python -m timetracker` also works and keeps a console attached for
   `print` debugging. Point it at a throw-away data folder so you do not touch
   your own entries:

   ```powershell
   $env:TIMETRACKER_DATA_DIR = "$env:TEMP\tt-dev"; .venv\Scripts\timetracker.exe
   ```

   Output: the folder is created with `timetracker.sqlite3`,
   `timetracker.log`, `instance.lock`, and the first-run welcome dialog opens
   because the settings table is empty.

4. **Find the layer for your change.** The package is layered and a test
   enforces the direction of imports:

   | Package | Knows about | Must not import |
   |---|---|---|
   | `core/` | pure Python: clock protocol, models, duration grammar, rounding, anchoring, label matching | PySide6, `ui/` |
   | `data/` | `sqlite3`: schema, migrations, repositories, paths | PySide6, `ui/` |
   | `services/` | repositories + `Clock`; Qt signals allowed (`QObject`) | widgets |
   | `ui/` | Qt Widgets; talks to services only | SQL |
   | `platform/` | OS APIs: idle input, autostart, console detach | — |
   | `app.py` | wires everything at boot | — |

   A rule of thumb: if the change is about *what a number is* (a duration, a
   rounding, a date boundary) it belongs in `core/` with a pure test; if it is
   about *how it is stored or queried*, `data/`; if it coordinates a workflow
   (start a timer, export a file), `services/`; only pixels go in `ui/`.

5. **Write the test in the matching folder** (`tests/core`, `tests/data`,
   `tests/services`, `tests/ui`). Fixtures from `tests/conftest.py`:
   `clock` (a `FakeClock` you advance by hand), `conn` (an in-memory,
   migrated database), `clients` / `types` / `entries` / `timers` / `settings`
   (repositories on that connection), `booted_app` (a full `App` on a
   temporary data folder for end-to-end UI tests, with `qtbot` from
   pytest-qt). Never call `datetime.now()` or `time.monotonic()` in code or
   tests — go through the `Clock`.

   Run just your file while iterating:

   ```powershell
   .venv\Scripts\python -m pytest tests/core/test_rounding.py -q
   ```

   Output: `62 passed in 0.08s`

6. **Commit.** The subject names the milestone or area first, then what
   changed (`M5: …`, or after 1.0 a short area tag such as `export: …`). CI
   (`.github/workflows/ci.yml`) runs ruff, mypy and pytest on Ubuntu, Windows
   and macOS × Python 3.12 and 3.13 for every push to `main`; the branch is
   green as of `614dc2f`.

## Common tasks

### Add a setting

1. `services/settings_service.py`: add a `KEY_…` constant and its default in
   `DEFAULTS`. Keys are dotted strings (`ui.theme`, `export.rounding_minutes`);
   values are JSON-serialisable and stored in the `setting` table.
2. `ui/settings_dialog.py`: add the control to the right tab (`_general_tab`,
   `_timer_tab`, `_export_tab`, `_labels_tab`, `_data_tab`), read it in the
   load path and write it in the apply path.
3. If something must react live (theme, time format, idle threshold do),
   connect `SettingsService.setting_changed` in `app.py` — see `_on_setting_changed`.
4. Tests: `tests/services/test_settings_service.py` for the default and
   round-trip; `tests/ui/test_settings_dialog.py` for the control.
5. Document it: `README.md` (if user-visible), `docs/DATA-FORMAT.md` (the
   settings table lists known keys), `USER-MANUAL.md` (the Settings table).

### Change the database schema

Schema changes are forward-only, versioned migrations; the app migrates on
launch and refuses to open a database newer than itself.

1. `data/schema.py`: bump `TARGET_VERSION`, add the new DDL piece, and update
   `CURRENT_DDL` — the DDL a *fresh* database is built from.
2. Add `data/migrations/m000N_<slug>.py` exposing `version = N` and
   `upgrade(conn)`. Migrations are discovered by `pkgutil` from the file name
   and must be contiguous from 1. `m0003_manual_method.py` is the template
   for a table rebuild (SQLite cannot alter a CHECK constraint); `m0002` for
   an added index.
3. Run `tests/data/test_migrate.py`. Its drift guard applies every migration
   to an empty database and compares `sqlite_master` with `CURRENT_DDL`; a
   mismatch between the two is the most common mistake and fails there.
4. Add a `vN-1 → vN` test with a database built from the old DDL and real
   rows, like `test_v2_to_v3_…` does.
5. Update `docs/DATA-FORMAT.md` (NFR-10 promises the format is documented).

`migrate()` takes a pre-migration copy (`timetracker-pre-vN.sqlite3`) next to
the database before applying anything.

### Change an export

`services/export_service.py` produces rows via `EntryRepo.export_rows`, then
`core/rounding.py` applies increment and scope, then CSV/XLSX writers.
Goldens for the CSV shape live in `tests/fixtures/export_*.csv` and are
compared byte-exact (CRLF; `.gitattributes` marks them `-text`). After a
deliberate change:

```powershell
$env:UPDATE_GOLDENS = "1"; .venv\Scripts\python -m pytest tests/services/test_export_service.py -q
```

Output: the run rewrites the fixtures and passes; `git diff tests/fixtures`
then shows exactly what changed in the file format. Remove the variable
afterwards. Rounding must never touch stored rows — `test_export_service.py`
checks that the database is unchanged after an export.

### Measure start-up and idle cost (NFR-01, NFR-03)

Any build — source, PyInstaller, Nuitka or the installed app — has a
measurement mode: boot, idle for N seconds, print one JSON line, exit.

```powershell
$env:TIMETRACKER_MEASURE_BOOT = "3"; $env:TIMETRACKER_ASSUME_TRAY = "1"; $env:TIMETRACKER_DATA_DIR = "$env:TEMP\tt-manual"; .venv\Scripts\python -m timetracker
```

Output (source tree, this laptop):

```
{"boot_seconds": 0.892, "idle_cpu_seconds": 0.0, "idle_wall_seconds": 3.019, "idle_cpu_percent": 0.0, "rss_mb": 72.9}
```

The installed Nuitka build on the same machine printed
`{"boot_seconds": 1.03, "idle_cpu_seconds": 0.0156, "idle_wall_seconds": 3.005, "idle_cpu_percent": 0.52, "rss_mb": 96.0}`.
`TIMETRACKER_ASSUME_TRAY=1` skips the "is there a tray?" check so this also
runs on a headless CI runner. `tests/test_nfr.py` runs it as a subprocess and
asserts the budgets.

### Build the binaries

The scripts take **no arguments** — `--help` starts a build. Install the
extra first: `.venv\Scripts\pip install -e .[build]`.

```powershell
.venv\Scripts\python scripts\build_dev.py
```

Output: PyInstaller log (`INFO: PyInstaller: 6.22.3 …`), result in
`dist\dev\timetracker\` within a minute. Good enough to check that a frozen
build finds its resources; never `--onefile` (it unpacks on every launch).

```powershell
.venv\Scripts\python scripts\build_release.py
```

Output: Nuitka log; the first run downloads a C compiler when none is found
(`--assume-yes-for-downloads`); several minutes. Result:
`dist\release\windows\timetracker.dist\timetracker.exe` (87 MB folder, Qt as
separate DLLs — required by the LGPL, see `THIRD_PARTY_NOTICES.md`). The
script prints `built C:\…\dist\release\windows\timetracker.dist` at the end.
On macOS the result is `dist/release/macos/Time Tracker.app`; on Linux
`dist/release/linux/timetracker.dist/timetracker.bin` (the `.bin` suffix
avoids a clash with the `timetracker/` package-data directory that sits
next to it; Windows has `.exe` for that).

Windows installer, after the release build:

```powershell
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer\windows.iss
```

Output: the Inno Setup compiler log ending with the output file name;
result `dist\installer\TimeTracker-1.0.0-setup.exe` (24 MB). A winget install puts ISCC under `%LOCALAPPDATA%`; the CI runner has
it under `%ProgramFiles(x86)%`. Test a silent per-user install with
`TimeTracker-1.0.0-setup.exe /SILENT` — note that silent mode does not create
the Desktop shortcut unless you pass `/TASKS=desktopicon`.

### Cut a release

1. Bump `version` in `pyproject.toml` and the heading in
   `docs/RELEASE-NOTES.md`; update `docs/MILESTONES.md`.
2. Walk `docs/RELEASE-CHECKLIST.md` (clean install, tray states, idle prompt,
   export, 50 k-row log, LGPL check).
3. Tag and push: `git tag -a v1.0.1 -m "Time Tracker 1.0.1"; git push origin v1.0.1`.
   `.github/workflows/release.yml` builds Windows (installer + portable zip),
   macOS (DMG) and Linux (AppImage + tar.gz), smoke-tests each binary in
   measurement mode, and publishes a GitHub Release with the release notes as
   body. Watch it at *Actions › Release*.

### Regenerate the icons

```powershell
.venv\Scripts\python scripts\make_icons.py
```

Output: `wrote 7 PNGs and icon.ico to C:\…\src\timetracker\resources`. The
PNG encoder is not byte-stable, so a regeneration shows as a diff even when
nothing changed; only commit it after a deliberate change to the painter in
`ui/icons.py`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `FAILED tests/test_layering.py::test_no_qt_or_ui_imports[core\_demo_bad.py]` | a module under `core/` or `data/` imports PySide6 or `timetracker.ui` | move the Qt-dependent part to `services/` or `ui/`; pass plain values down |
| `tests/test_no_network.py` fails | a new import of `socket`, `urllib`, `http`, `QtNetwork` … or a socket call at boot | remove it; NFR-05 forbids any network code path. Single-instance IPC uses a file lock plus a watched file for that reason |
| `SchemaTooNewError` / app refuses to start after switching branches | the database on disk was migrated by a newer branch | point `TIMETRACKER_DATA_DIR` at a fresh folder, or restore the `timetracker-pre-vN.sqlite3` copy |
| `test_migrate.py` drift guard fails | `CURRENT_DDL` and the sum of migrations disagree | make the fresh DDL and the migration produce identical `sqlite_master` rows (column order and constraint text included) |
| `missing golden export_….csv; run with UPDATE_GOLDENS=1` | a new export variant has no fixture | run once with `UPDATE_GOLDENS=1`, inspect the file, commit it |
| Second `timetracker.exe` exits immediately with code 1 | an instance already holds `instance.lock`; the second one only asks the first to show its popover | look for the popover; kill the first instance to run a new one |
| `FileNotFoundError: [WinError 3] … 'Z:\\'` at boot | `TIMETRACKER_DATA_DIR` points at a location whose parent cannot be created | use an existing drive/folder |
| `tests/test_log_performance.py` fails on a laptop on battery | the 200 ms budget was missed once | it is best-of-3; plug in / close other apps and re-run; CI uses a 500 ms budget |
| A console window opens with the tray app | launched via `python.exe` or from a shell that owns the console | use `timetracker.exe` / `pythonw -m timetracker`; `platform/win32.py` frees an orphaned console only when it has no other client |
| `scripts\build_release.py --help` starts compiling | the scripts have no CLI | Ctrl+C; delete `nuitka-crash-report.xml` if it appears |

## Reference

**Environment variables**

| Variable | Effect |
|---|---|
| `TIMETRACKER_DATA_DIR` | data folder (database, log, lock, backups) instead of the platform default |
| `TIMETRACKER_MEASURE_BOOT=<seconds>` | boot, idle that long, print one JSON line, exit 0 |
| `TIMETRACKER_ASSUME_TRAY=1` | skip the system-tray availability check (headless runs) |
| `UPDATE_GOLDENS=1` | tests: rewrite `tests/fixtures/export_*.csv` |
| `QT_QPA_PLATFORM=offscreen` | set by `conftest.py`; tests never open windows |

**Commands**

| Command | Purpose |
|---|---|
| `.venv\Scripts\python -m pytest -q` | 477 tests + 5 skips, ~30 s |
| `.venv\Scripts\ruff check .` | lint, line length 100, `docs/` excluded |
| `.venv\Scripts\mypy` | strict typing on `core/` and `data/` |
| `.venv\Scripts\timetracker.exe` | run from source without a console |
| `python scripts/make_icons.py` | render `resources/icon-*.png` and `icon.ico` |
| `python scripts/build_dev.py` | PyInstaller onedir → `dist/dev/` |
| `python scripts/build_release.py` | Nuitka standalone → `dist/release/<os>/` |
| `ISCC.exe installer\windows.iss` | Windows installer → `dist/installer/` |
| `installer/linux/make_appimage.sh`, `installer/macos/make_dmg.sh` | Linux/macOS packages (used by the release workflow) |

**Package map** (`src/timetracker/`)

| Module | Responsibility |
|---|---|
| `core/clock.py` | `Clock` protocol, `SystemClock(tz_name)`, `FakeClock` |
| `core/models.py` | `Entry`, `Label`, `RecordMethod` (STOPWATCH / QUICKADD / MANUAL), `Dimension` |
| `core/duration.py` | `parse_duration("1h15") → 4500`, formatting |
| `core/rounding.py` | increment + scope, applied to export rows only |
| `core/anchoring.py` | start/end anchors for Add Time entries, arithmetic in UTC |
| `core/labels.py` | normalisation, near-duplicate (edit distance ≤ 2, min length 4) |
| `data/schema.py`, `data/migrations/` | DDL pieces, `CURRENT_DDL`, `TARGET_VERSION = 3` |
| `data/*_repo.py` | `EntryRepo` (query / export_rows / summary / overlapping_ids …), `LabelRepo`, `TimerRepo`, `SettingsRepo` |
| `services/timer_service.py` | the only writer of `running_timer` and creator of STOPWATCH entries; 30 s heartbeat |
| `services/idle_monitor.py`, `power_monitor.py` | idle/sleep detection → `IdleSpan` |
| `services/reminder_service.py` | FR-702: 60 s check, `reminder_due` → tray balloon; opt-in |
| `core/export_presets.py` | FR-608: `ExportPreset` / `PresetList`, JSON in `export.presets`; run by `LogWindow.run_preset()` |
| `core/csv_import.py`, `services/import_service.py` | FR-805: sniff → `guess_mapping` → `parse_rows` (pure); the service resolves labels, flags duplicates (`EntryRepo.exists_like`) and commits via `EntryService.add_many` (one transaction) |
| `services/entry_service.py`, `label_service.py`, `export_service.py`, `backup_service.py`, `settings_service.py` | one workflow each |
| `platform/` | `IdleProvider`, `AutostartProvider` per OS; `factory.py` picks; `launch_command()` |
| `ui/tray.py`, `ui/popover.py`, `ui/quickadd/`, `ui/log/`, `ui/dialogs/`, `ui/settings_dialog.py`, `ui/theme.py` | widgets |
| `app.py` | `App(QApplication)`: bootstrap order, wiring, quit and relaunch |
| `instance_lock.py`, `crashlog.py`, `diagnostics.py` | single instance, uncaught-exception log, measurement mode |

**Invariants the tests enforce** (full list in `CLAUDE.md`)

- `core/` and `data/` never import PySide6 or `ui/` (`test_layering.py`).
- No network module anywhere, no socket call at boot (`test_no_network.py`).
- Durations come from the monotonic clock; `duration_seconds` is
  authoritative and never recomputed from timestamps.
- Rounding only at export; stored rows never change.
- Every service takes a `Clock`; tests use `FakeClock`.
- Migrations applied in sequence equal `CURRENT_DDL`.

**Test suite layout**: `tests/core`, `tests/data`, `tests/services`,
`tests/ui` mirror the package; top-level files cover cross-cutting
requirements — `test_layering.py`, `test_no_network.py`,
`test_instance_lock.py`, `test_crash_recovery.py`, `test_log_performance.py`
(50 000 rows, 200 ms), `test_nfr.py`, `test_first_run.py`,
`test_scenario_s3.py`, `test_platform_*.py`.

## Verification

**Verified** by running on this machine (Windows 11, Python 3.13.0, commit
`614dc2f`):

- `pytest -q` → 477 passed, 5 skipped in 27.39 s; `ruff check .` → All
  checks passed; `mypy` → no issues in 23 source files.
- `pytest tests/core/test_rounding.py -q` → 62 passed.
- Layering guard: a file `core/_demo_bad.py` containing `import PySide6`
  makes `test_layering.py` fail with the message quoted in Troubleshooting;
  the file was removed afterwards.
- Measurement mode on the source tree and on the installed 1.0.0 exe printed
  the JSON lines quoted above, exit 0; the data folder contained
  `instance.lock`, `timetracker.log`, `timetracker.sqlite3`.
- A second `timetracker.exe` while one runs exits with code 1.
- `TIMETRACKER_DATA_DIR=Z:/nope` produces the `FileNotFoundError` quoted.
- `build_release.py --help` and `build_dev.py --help` start builds (they parse
  no arguments); `make_icons.py` prints the line quoted and produces a diff
  in `icon-16.png`, `icon-24.png` and `icon.ico` on a no-change regeneration.
- The Nuitka build, ISCC installer build and silent install were done during
  M7 (`MILESTONES.md`); CI run for `614dc2f` is green on all six jobs.
- Dependency versions from `pip`: PySide6 6.11.2, openpyxl 3.1.5.

**Assumed** (not executed while writing this):

- The macOS and Linux command forms (`.venv/bin/…`) and the `make_dmg.sh` /
  `make_appimage.sh` scripts — exercised only by the release workflow.
- The exact `pip install` output text; only its success was observed.
- The `UPDATE_GOLDENS=1` run was done during M5, not re-run for this manual.
