# Time Tracker — user manual

*For Time Tracker 1.0.0 · written 16 September 2026 · Windows screenshots
described in words; macOS and Linux differ only where stated.*

## Overview

**Who this is for:** someone who has never used Time Tracker and wants to know
where their working hours went — per client, per kind of work — without
learning a new tool. No technical knowledge is assumed.

**After reading, you can** record your working time in two ways (a stopwatch
and a quick "add 15 minutes" grid), look the entries up, correct them, and hand
a spreadsheet of them to whoever needs it.

Time Tracker has no main window. It lives as a small **clock icon in the
system tray** — the row of little icons next to the Windows clock at the
bottom right of the screen (top right menu bar on a Mac). Everything starts
from that icon:

| Do this on the icon | You get |
|---|---|
| **Left-click** | the *popover*: stopwatch, or the Add Time grid |
| **Right-click** | a menu: *Start* / *Stop*, *Add Time…*, *Open log…*, *Settings…*, *Quit* |
| **Hover** | a tooltip: what is running, or "Not tracking" |

Your time is stored in one file on your own computer. The app never connects
to the internet and never sends anything anywhere.

## Prerequisites

- Windows 10 or 11, macOS 13 or newer, or a Linux desktop with a system tray
  (KDE, XFCE and LXQt work directly; GNOME needs the *AppIndicator* extension).
- The installer or archive from the project's *Releases* page:
  `TimeTracker-1.0.0-setup.exe` (Windows, 24 MB), `TimeTracker-1.0.0.dmg`
  (macOS) or `TimeTracker-1.0.0-x86_64.AppImage` (Linux).
- No administrator rights: the Windows installer installs for your user only,
  into `C:\Users\<you>\AppData\Local\Programs\Time Tracker`.

Because the app is not code-signed, Windows shows a blue *Windows protected
your PC* box the first time. Click **More info**, then **Run anyway**. On a
Mac, right-click the app and choose **Open** the first time.

## Step by step: your first entry

Timed on a fresh installation: 20 seconds from the welcome screen to the first
saved entry.

1. **Install.** Double-click `TimeTracker-1.0.0-setup.exe`, click *Next*
   through the wizard. Two boxes are worth ticking: *Create a Desktop shortcut*
   and *Start Time Tracker when I log in*. Leave *Launch Time Tracker* ticked
   on the last page and click *Finish*.
2. **Welcome screen.** A window titled *Welcome to Time Tracker* asks for your
   clients, one per line. Type the two or three you bill most; you can add
   more later, and a client typed anywhere in the app is remembered. Below is
   a box *Start Time Tracker when I log in* — leave it ticked if you want the
   clock icon there every morning. Click **Get started**.
3. **The popover opens by itself.** It shows a big `0:00:00`, two drop-downs
   (client and category), a **Start** button and an **Add Time…** button.
   The categories are already filled in: *Email/Chat*, *Phone*,
   *Meeting/Call*, *Work*.
4. **Record time with the stopwatch.** Pick a client and a category, click
   **Start**. The popover closes; the clock icon changes to show it is running,
   and hovering it tells you what is running. When you are done, left-click
   the icon and click **Stop**. That is one entry saved.
5. **Or record time you already spent.** Click **Add Time…**. A grid with four
   columns appears: *Time*, *Category*, *Client*, *Note*.
   - Click `+15min` twice: the header now reads `0:30`. Time chips **add up**.
   - Click one category and one client (exactly one of each stays selected).
   - Optionally type a note.
   - Click **Add**. A small message confirms what was logged, with an **Undo**
     button that stays for ten seconds. The total resets to `0:00`; the client and
     category stay selected, so the next block is two clicks.
6. **Look at what you have.** Right-click the icon → **Open log…** (or the
   *Open log* link at the bottom of the popover). Each entry is one line:
   date, start, end, total, client, type, how it was recorded, note. The
   status line at the bottom shows *Total h:mm*, then the totals per client
   and per type for whatever the filters show.

Expected after step 6: two lines in the log for today, one with method
*Start-Stop* and one with *Add Time*, and a *Total* equal to their sum.

## Common tasks

### Add Time faster

- **Clear the total** with the **Clear** button in the footer; **subtract** a
  chip by holding **Shift** while clicking it.
- **Custom…** at the bottom of the *Time* column accepts anything like `45`,
  `1:30`, `1h15` or `2h` (`45` means 45 minutes). *Custom…* under *Category*
  and *Client* creates a new label on the spot — it becomes a chip next time.
- **Keyboard only**, once the grid has focus: `1`–`5` press the time chips
  (`Shift`+digit subtracts), `Q W E R T` pick a category, `A S D F G` pick a
  client, `Tab` jumps to the note, `Enter` adds, `Ctrl+Z` undoes the last
  add, `Esc` closes the popover and keeps the total you had.
- The app remembers which page you used last, so the grid is one left-click
  away tomorrow.
- If you type a client that nearly matches an existing one (for example
  `Niek` when `Nike` exists), the app offers the existing one instead of
  creating a near-duplicate.

### When you step away

If a timer is running and you do not touch the keyboard or mouse for 10
minutes (changeable in *Settings › Timer*), or the computer sleeps or is
locked, the app asks what to do with the away time when you come back:

| Button | Effect |
|---|---|
| **Keep it** | the away time stays in the running entry |
| **Discard it** | the away time is removed; the timer keeps running from now |
| **Discard and stop** | the entry ends at the moment you went away |
| **Log it separately** | the timer stops at the moment you went away and the away time becomes its own entry, same client and category, note `Idle` — handy when the "idle" time was a meeting |

You do not have to answer straight away: the timer keeps running, the icon
shows a small attention mark, and a left-click brings the question back.

### Pause

For a break you know about — lunch, a school run — click **Pause** next to
**Stop** (or right-click the icon → **Pause**). The clock stops counting, the
icon turns grey with two bars, and **Resume** continues the *same* entry.
While paused nothing is counted and the app does not ask about away time. If
you click **Stop** while paused, the entry ends at the moment you paused.
The log keeps the total paused time for each entry (hover the *Total* cell).

A timer that runs for 12 hours (changeable) raises a second question:
**Keep running** or **Stop now**.

### Forgot to start the timer?

*Settings › Timer › Remind me when nothing is being tracked* (off unless you
turn it on) shows a passive notification when no timer is running and
nothing has been added for, say, 60 minutes — only inside the working hours
and days you set. It repeats every N minutes until you start, pause, add or
edit something. Quiet time before the working day starts does not count, so
the first reminder of a Monday comes N minutes after your start time.

### Fix a mistake in the log

- **Change a value:** double-click the cell (date, start, end, total, client,
  type, note) and type. Changing the *Total* keeps the start and moves the
  end. An edited line shows ✎ in the first column; the method column never
  changes.
- **Delete:** select the line, press **Delete** (toolbar or key). **Undo
  delete** in the toolbar brings it back, as long as the log window stays
  open. Deleting several lines at once asks for confirmation.
- **Add an entry by hand:** toolbar **Add entry…**: date, start, duration
  (`1:30`, `1h15`, `45`), client, type, note. It is stored with method
  *Manual*, so you can tell it apart later.
- **Two entries at the same time** (for example a forgotten stopwatch plus an
  Add Time block) are marked ⧉ in the first column. Nothing is blocked — you
  decide which to shorten.

### Find entries

The log's top bar: a date preset (*Today*, *This week*, *Last week*, *This
month*, *Last month*, *All time*, *Custom range*) next to two date fields you
can edit directly — editing one switches the preset to *Custom range* —
then client, type and method drop-downs and a **Search notes…** field. Click
a column header to sort by it.

### Get a spreadsheet

In the log, set the filters to what you want to hand over (for example *Last
month* and one client), click **Export** → **Excel (XLSX)…** or **CSV…**.

The export dialog offers **rounding**: none, 6, 10, 15 or 30 minutes, always
rounded *up*, and a **scope**: *per entry* (each line rounded) or *per day ×
client × type* (the day's lines for one client and category are added first,
then rounded once — three 2-minute emails become one 6-minute block, not
three). The stored entries are never changed; only the file is. The file
says which rounding was used (last lines of the CSV, an *Export info* sheet in
the XLSX).

The Excel file has real durations you can sum, a frozen header row, and a
total row.

The same dialog lets you untick **columns** you do not want in the file and
pick the **folder**. **Save as preset…** keeps that combination (format,
columns, rounding, scope, folder) under a name; from then on it sits in the
**Export** menu and one click writes the current view to that folder with a
dated name (`timetracker_<from>_<to>.xlsx`) — no dialog, and an existing file
is never overwritten (`-2`, `-3`, … are added). The filters are *not* part of
a preset: a preset exports whatever the log shows. Remove presets in
*Settings › Export*.

### Quit, and what happens to a running timer

Right-click → **Quit** while a timer runs asks: **Stop and save**, **Keep
running** (cancels the quit) or **Discard**. If the computer crashes or loses
power, the next launch offers **Recover entry** — at most 30 seconds are lost.

### Settings

Right-click → **Settings…**. Five tabs:

| Tab | What is there |
|---|---|
| **General** | *Start Time Tracker when I log in*; theme (system / light / dark); first day of the week; 12 h / 24 h clock |
| **Timer** | idle threshold in minutes (0 = off); long-running warning in hours (0 = off). Sleep and lock are always detected. *Remind me when nothing is being tracked* (off by default): a small notification from the clock icon after N quiet minutes, only between the hours and on the days you tick; clicking it opens the popover. |
| **Export** | default rounding and scope; CSV separator; export folder; the list of export presets (delete here, create them in the log's Export dialog) |
| **Labels** | rename, archive (hide from the chips, keep in history) or delete a client or category; delete works only when no entry uses it |
| **Data** | *Reveal data folder*, *Open log file*, **Back up now**, **Restore from backup…**, **Export all data…** (every entry and label as CSV and JSON) |

Restoring from a backup restarts the app; a snapshot of the current data is
taken first, so nothing is lost by trying.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Blue *Windows protected your PC* screen when running the installer | The app is not code-signed | Click *More info* → *Run anyway* |
| Nothing visible after launch | The icon is in the tray overflow | Click the `^` arrow left of the Windows clock; drag the clock icon onto the taskbar to keep it visible. On GNOME, install the AppIndicator extension. |
| Launching it again does nothing new | Only one copy runs at a time; the second one just pops the first one's popover open and exits (exit code 1, no message) | Look for the popover near the tray |
| **Add** stays greyed out in the grid | The total is `0:00`, or no client / category is selected — both are required by default | Click a time chip and one chip in each column; *Settings › Timer › Add Time requires* relaxes this |
| Typed `abc` in Custom… or the Add entry duration and nothing happened | The field only accepts durations: `45`, `1:30`, `1h15`, `2h` | Type one of those forms |
| The stopwatch total in the popover is bigger than the wall-clock difference | You kept away time, or the laptop slept and you chose *Keep it* | Edit the *Total* in the log if that was not intended |
| An entry has a ⚠ mark in the log | After editing, end − start no longer matches the total by two minutes or more | It is only a marker; fix the start, end or total |
| The tray icon shows a small mark and clicking it opens a question, not the popover | An idle prompt is waiting | Answer it; the popover comes back |
| *Restore from backup…* refuses a file | It is not a SQLite file, fails SQLite's integrity check, is not a Time Tracker database, or comes from a newer version | Pick a file made by *Back up now* or *Export all data…* of this or an older version |
| Windows Task Manager › Startup apps shows *Time Tracker* with a strange short path (`TIMETR~1`) | 1.0.0 wrote the 8.3 name it was launched with; cosmetic, Windows resolves it | Toggle *Start at login* off and on in *Settings › General* (later versions write the long path) |

The app writes uncaught errors to `timetracker.log` in the data folder
(*Settings › Data › Open log file*).

## Reference

**Where your data is.** One file, `timetracker.sqlite3`, in:

| OS | Folder |
|---|---|
| Windows | `C:\Users\<you>\AppData\Local\TimeTracker` |
| macOS | `~/Library/Application Support/TimeTracker` |
| Linux | `~/.local/share/timetracker` |

Back it up with *Settings › Data › Back up now* (timestamped copy next to
it). Do not put the folder on OneDrive or Dropbox: two machines writing the
same file corrupts it. Uninstalling the app leaves the folder in place.

**Duration forms accepted everywhere:** `45` (minutes), `1:30`, `1h15`, `2h`,
`0:05`.

**Tray menu:** Start / Stop · Add Time… · Open log… · Settings… · Quit.

**Popover, stopwatch page (380 px wide):** elapsed time, client, category,
Start/Stop, Add Time…, *Open log*, *Settings*.
**Popover, Add Time page (640 px wide):** ‹ Timer, pending total,
`+6min +15min +30min +45min Custom…`, category chips + Custom…, client chips
+ Custom…, note; footer with today's total, **Clear**, **Add**.

**Log columns:** (flags) · Date · Start · End · Total · Client · Type · Method
· Note. Methods: *Start-Stop*, *Add Time*, *Manual*.

**Export columns:** Date, Start, End, Duration (decimal hours), Duration
(h:mm), Client, Type, Record method, Note — then, in CSV, footer lines
*Exported*, *Application* and the rounding used.

**Defaults:** idle threshold 10 min; long-running warning 12 h; client and
category required in Add Time; rounding none, scope per day × client × type;
theme system; week starts Monday; 24 h clock.

**Keyboard in the Add Time grid:** `1–5` time chips (`Shift` subtracts),
`Q W E R T` category, `A S D F G` client, `Tab` note, `Enter` add, `Ctrl+Z`
undo, `Esc` close.

**Uninstall (Windows):** *Settings › Apps › Installed apps › Time Tracker ›
Uninstall*, or `Uninstall Time Tracker` in the Start Menu. Your data folder
stays.

## Verification

**Verified** on this PC (Windows 11, Time Tracker 1.0.0 installed from
`TimeTracker-1.0.0-setup.exe`):

- Installer runs without an administrator prompt; files land in
  `%LOCALAPPDATA%\Programs\Time Tracker`; Start Menu entry and uninstaller
  present; the *Create a Desktop shortcut* and *Start … when I log in* options
  exist in the wizard.
- First run with an empty data folder: welcome screen → clients → *Get
  started* → popover opened by itself → first entry in 20 seconds.
- Start/Stop, Add Time (`+15min` twice = `0:30`), Undo toast, log window with
  editing, deletion and undo, *Add entry…*, overlap marker, XLSX and CSV
  export with rounding, idle prompt with the four buttons, quit prompt with
  three buttons, recovery after a killed process, settings tabs and their
  controls, backup and restore with relaunch — all exercised during the
  milestone acceptance runs (M2–M7) recorded in `MILESTONES.md`.
- Second launch while running exits with code 1 and raises the first
  instance's popover.
- Duration forms: `1:30`→1 h 30, `1h15`→1 h 15, `45`→45 min, `2h`, `0:05`
  accepted; `abc` and empty rejected.
- Data folder contents after first run: `timetracker.sqlite3`,
  `timetracker.log`, `instance.lock`.

**Assumed** (not checked by hand):

- macOS and Linux behaviour: the DMG/AppImage are built and smoke-tested by
  the release workflow only; the tray, idle and autostart code paths for those
  systems are covered by unit tests, not by a person.
- The SmartScreen wording *Windows protected your PC* is Microsoft's standard
  text for unsigned executables; this installer was not downloaded through a
  browser here, so the exact screen was not seen.
