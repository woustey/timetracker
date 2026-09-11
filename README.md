# Time Tracker

A tray-resident, local-only time tracker for people who bill or allocate their
time across several clients. Two ways to record time: a labelled **Start–Stop**
stopwatch, and an **Add Time** matrix that logs a finished block in a handful of
clicks. Everything lives in one SQLite file on your machine. No account, no
network, no telemetry.

Requirements and design live in `docs/`:

- `docs/PRD-time-tracker.md` — product requirements (PRD-01)
- `docs/PRD-time-tracker-qt.md` — technical design and milestone plan (PRD-02)

## Status

Pre-alpha. Milestones are tracked in PRD-02 §13.

## Running from source

Python 3.12+ required.

```
python -m venv .venv
.venv/Scripts/pip install -e .[dev]        # Windows
# .venv/bin/pip install -e .[dev]          # macOS / Linux
.venv/Scripts/python -m timetracker
```

## Tests

```
.venv/Scripts/python -m pytest
.venv/Scripts/ruff check .
.venv/Scripts/mypy
```

Headless Qt tests use the `offscreen` platform plugin; CI sets
`QT_QPA_PLATFORM=offscreen`.

## Platform notes

- **Linux** tray support depends on the desktop. KDE, XFCE and LXQt work out of
  the box; GNOME needs an AppIndicator/StatusNotifier extension. Linux is
  best-effort (PRD-02 R1).
- If no system tray is available the application says so and exits; a windowed
  fallback mode is planned (FR-110).
