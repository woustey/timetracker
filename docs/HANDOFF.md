# Handoff: Time Tracker 1.0.0 — shipped; post-release follow-ups

## Context & goal

The user (GitHub `woustey`, git author email wouter@dawasal.be, works on a Windows 11 PC, PowerShell 5.1, Python 3.13.0) is the product owner of a tray-resident, local-only time tracker for people who bill time across clients. The product was specified in two PRDs the user supplied — `docs/PRD-time-tracker.md` (PRD-01: product requirements, FR-/NFR- ids, priorities M/S/C, open questions §15) and `docs/PRD-time-tracker-qt.md` (PRD-02: technical design, test plan §11, milestones M0–M7 §13) — and built milestone by milestone by an AI assistant with the user acting as owner/acceptor. Repo: `C:\Users\ws\Projects\timetracker`, GitHub `https://github.com/woustey/timetracker` (public, branch `main`). All milestones M0–M7 are accepted and **release 1.0.0 is published**: https://github.com/woustey/timetracker/releases/tag/v1.0.0. The remaining goal is maintenance and whatever the user asks for next (v1.1 backlog, tidy-ups).

## Key decisions made

- Process rules (fixed, from the user): per milestone, first present the plan and files, wait for "go", implement, write the PRD-02 §11 tests for the layer and run them, commit with the milestone id in the subject (`M5: …`), report against §13 acceptance, then stop and wait. Implement only **M** (must) requirements; skip every S and C unless the user opts in. Where the spec is ambiguous or wrong, say so and ask. No AI features, no network calls, no telemetry (NFR-05 is enforced by `tests/test_no_network.py`).
- `CLAUDE.md` in the repo holds the invariants and every decision taken with the owner; it is the contract the tests enforce. Read it before touching code. Highlights: `core/` and `data/` import neither PySide6 nor `ui/` (`tests/test_layering.py`); durations are monotonic, `duration_seconds` is authoritative and never derived from timestamps; rounding only at export, never mutating stored rows (FR-605); every service takes a `Clock` (tests use `FakeClock`); Python 3.12+, PySide6 Qt Widgets (not QML), stdlib sqlite3 in WAL mode; **exactly four runtime dependencies** (PySide6, openpyxl, tzdata on win32 only, pyobjc-framework-Quartz on darwin only) — ask the user before adding a fifth.
- User opt-ins beyond M: overlap flags (FR-508), an "Add entry…" form in the log window, and a third record method `MANUAL` (schema v3) alongside `STOPWATCH` and `QUICKADD`.
- Q1 (PRD-01 §15): an entry may be saved with client/type NULL; the "mandatory labels" setting gates only the Add Time matrix's Add button.
- Popover remembers its last page (`popover.last_mode`) so the matrix is one click from the tray (the ≤ 4-click metric failed at 6 clicks before this).
- Single instance via OS file lock + a watched `show.request` file, not QLocalServer (NFR-05).
- Autostart on Windows is the HKCU `Run` key value `TimeTracker`; macOS LaunchAgent plist; Linux XDG `.desktop`. Offered once on first run.
- Windows launch: `[project.gui-scripts] timetracker` exe; `platform/win32.py` `detach_orphan_console()` frees an orphaned console; never launch the app from the chat's Run button (that terminal kills the process tree when closed).
- Packaging: Nuitka `--standalone` via `scripts/build_release.py` (Qt dynamically linked for LGPL), PyInstaller onedir via `scripts/build_dev.py`, Inno Setup per-user installer `installer/windows.iss` (no admin, never touches the data folder), AppImage/DMG scripts under `installer/`, tag-triggered `.github/workflows/release.yml` that also supports `workflow_dispatch` (builds all three platforms, publishes only on a `v*` tag). Binaries are unsigned.
- Non-Windows Nuitka binary is named `timetracker.bin` (collides with the `timetracker/` package-data directory otherwise); tzdata is passed to Nuitka on Windows only; packaging shell scripts carry the executable bit; on macOS the script picks `__main__.app` over the intermediate `__main__.dist`.
- Release procedure (now checklist step 0 in `docs/RELEASE-CHECKLIST.md`): dry-run `gh workflow run release.yml --ref main`, tag only when all three platforms are green. Moving a pushed tag is something the user does themselves in their own terminal (the assistant's permission mode blocks tag deletion); the user's shell is PowerShell 5.1, so commands must be given one per block without `&&`.
- Documentation set kept current: `README.md`, `docs/DATA-FORMAT.md` (NFR-10), `docs/RELEASE-CHECKLIST.md`, `docs/RELEASE-NOTES.md`, `docs/MILESTONES.md` (build history M0–M7 + lessons), and three manuals `docs/USER-MANUAL.md`, `docs/DEVELOPER-MANUAL.md`, `docs/PRODUCT-OWNER-MANUAL.md`, each with a rendered self-contained `.html` beside it and a Verified/Assumed section at the end that must stay truthful. The HTML is rendered from the Markdown with the user's `manual-writing` skill (`~/.claude/skills/manual-writing/scripts/render_html.py`; the assistant added a two-line `<em>` italics rule to that renderer — the user was told and did not object).
- Commit messages: no attribution lines. Commit only when the user says so (they typically say "commit"); the user has explicitly asked for commits at the end of each doc task in this session.

## Current state

- `main` head: `783da2a docs: release dry-run step, macOS budget note, 1.0.0 release history`. Working tree clean apart from this handoff file (untracked). CI green.
- Tag `v1.0.0` is on `1da5ae0`; release run 35081534306 succeeded on all four jobs. Published assets: `TimeTracker-1.0.0-setup.exe` (24 MB), `TimeTracker-1.0.0-windows-portable.zip` (34.1 MB), `TimeTracker-1.0.0.dmg` (38.7 MB), `TimeTracker-1.0.0-x86_64.AppImage` (59.5 MB), `TimeTracker-1.0.0-linux-x86_64.tar.gz` (65.2 MB). Release body = `docs/RELEASE-NOTES.md`, updated after the fact with `gh release edit v1.0.0 --notes-file docs/RELEASE-NOTES.md`.
- Commits after the original tag point `614dc2f`: `69605f5` (manuals), `0cbdaf4` (tzdata win32-only in Nuitka), `f98901d` (`timetracker.bin` rename), `1da5ae0` (exec bits, `.app` pick), `783da2a` (docs).
- Test suite: 477 passed, 5 skipped (other-platform tests) in ~27 s; `ruff check .` and `mypy` clean.
- Measured: NFR-09 first entry 20 s (user-timed on the installed build with an empty data folder); installed Windows build boot 1.03 s / RSS 96 MB locally; CI runners: Windows 0.41 s / 69 MB, Linux 0.63 s / 96 MB, macOS (Apple silicon) 1.98 s / 149 MB — macOS is at the edge of the ≤ 2 s / ≤ 150 MB budgets and this is noted in the release notes.
- On the user's PC: Time Tracker 1.0.0 is installed at `%LOCALAPPDATA%\Programs\Time Tracker\` (installed silently from the local `dist\installer` build, byte-identical version to the published one). The Desktop shortcut `C:\Users\ws\Desktop\Time Tracker.lnk` and the HKCU Run key `TimeTracker` both point at the installed exe (Run key value is the 8.3 short path `C:\Users\ws\AppData\Local\Programs\TIMETR~1\timetracker.exe` — cosmetic). Real data folder: `%LOCALAPPDATA%\TimeTracker\`. Scratch data folders `%TEMP%\tt-fresh-user` and `%TEMP%\tt-manual` still exist and can be deleted. Windows Sandbox is not enabled on the PC (needs admin + reboot); `installer/sandbox-test.wsb` exists for when it is.
- macOS and Linux artefacts have never been hand-tested by a person; they are CI-built and smoke-tested in measurement mode only (stated in the release notes and manuals).

## Work in progress (verbatim)

Nothing is mid-flight: the last task (docs follow-up, commit `783da2a`) was completed, committed and pushed. The open loose-ends list as last given to the user, verbatim:

> Remaining on this PC, when you like: the scratch folders `%TEMP%\tt-fresh-user` and `%TEMP%\tt-manual` can be deleted; the installed 1.0.0 is identical to the published one, so keep it.

Candidate small follow-ups mentioned to the user during this session but not requested (do not start them unasked):

- Write the long path instead of the 8.3 short name into the Run key (`os.path.realpath` / `GetLongPathNameW` in `platform/factory.py` `launch_command()`); cosmetic, would show nicer in Task Manager › Startup apps.
- The Windows silent install (`/SILENT`) does not create a Desktop shortcut unless `/TASKS=desktopicon` is passed; documented in the developer manual, no code change.
- Nuitka warns "To compile a package with a '__main__' module, specify its containing directory … consider '--python-flag=-m'" — harmless, unaddressed.

## Open questions

- Whether the user wants a v1.1 and which backlog items: PRD-01 §14 names pause/resume (FR-212), day timeline (FR-509), weekly grid (FR-510), export presets (FR-608), CSV import (FR-805), reminders (FR-702); everything marked S/C is eligible. Code signing (Windows Authenticode / Apple notarisation) needs a purchased certificate — `docs/RELEASE-CHECKLIST.md` §8. Not raised by the user yet.
- Whether the user will enable Windows Sandbox for a true fresh-VM check; they accepted 1.0.0 without it.
- The user's final message was cut off ("use the handover skill to write a handoff document for a new") — assumed to mean a new chat/session; unclear if something else was intended.

## Rejected paths

- QtNetwork/QLocalServer for single-instance IPC — rejected; NFR-05 forbids network modules. File lock + watched file instead.
- Onefile PyInstaller builds — rejected; unpacks on every launch (~2 s). Onedir only.
- Deriving `duration_seconds` from timestamps, or adjusting accrued time by "accrued −= idle" blindly — rejected; monotonic accrual with explicit idle outcomes.
- A Python `QSortFilterProxyModel` over the log — rejected; misses NFR-04 at 50 000 rows. Filtering/sorting/paging is SQL.
- Implementing S items in M6 (global hotkeys FR-109, merge/pin/colour FR-406–408, stop-confirmation and minimum-duration settings) — skipped by rule.
- Naming the macOS/Linux binary `TimeTracker` (capitalised) to dodge the data-dir clash — rejected; APFS is case-insensitive. `timetracker.bin` chosen.
- Having the assistant move the `v1.0.0` tag — blocked by the permission mode; the user runs the tag commands.
- Tagging `v1.0.1` instead of moving the unpublished `v1.0.0` tag — offered, user chose to move the tag (nothing had been published).
- Degrading the manuals' Markdown (removing italics) to suit the HTML renderer — rejected in favour of a two-line renderer fix.

## Tone & working preferences

- Very short messages from the user ("go", "commit", "done", "1. OK 2. OK …"). Reply concisely; lead with the result; tables for status/reports.
- Ask before starting a milestone or anything ambiguous; list questions numbered so the user can answer "1. OK 2. …".
- Stop after each milestone report and wait — do not roll into the next milestone.
- When giving the user shell commands to run themselves: PowerShell 5.1, one command per fenced `powershell` block, no `&&`, no chaining.
- Never launch the tray app from the chat's Run button; the user tests the real app by hand and reports back ("6 clicks", "works", "20 seconds").
- Report faithfully, including failures and what was not verified (the manuals' Verified/Assumed pattern came from this).
- Do not add attribution lines to commits. Commit only when told.
- Keep `CLAUDE.md` and the docs list current when behaviour changes.

## Immediate next step

Ask the user what they want next (v1.1 backlog item, a tidy-up such as the Run-key long path, or nothing), and before any code change read `CLAUDE.md` and `docs/DEVELOPER-MANUAL.md` in `C:\Users\ws\Projects\timetracker`.
