"""NFR-04 / M5 acceptance: the log stays responsive with 50 000 entries.

A real file database is seeded with 50 000 synthetic rows (about twenty years
of heavy use) and the operations a user does — open, filter, sort, scroll a
page, totals — are timed against the 200 ms budget. Budgets are relaxed 2.5×
on CI runners, which are slower and noisier than a laptop.
"""

from __future__ import annotations

import os
import random
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from timetracker.core.clock import FakeClock
from timetracker.core.models import Dimension
from timetracker.data.db import connect, transaction
from timetracker.data.entry_repo import EntryRepo
from timetracker.data.label_repo import LabelRepo
from timetracker.data.migrate import migrate
from timetracker.services.entry_service import EntryService
from timetracker.services.export_service import ExportService
from timetracker.services.label_service import LabelService
from timetracker.services.settings_service import SettingsService
from timetracker.ui.log.model import Col
from timetracker.ui.log.presets import DatePreset
from timetracker.ui.log.window import LogWindow

ROWS = 50_000
BUDGET_S = 0.2 * (2.5 if os.environ.get("CI") else 1.0)


def _seed(db: Path, clock: FakeClock) -> None:
    conn = connect(db)
    migrate(conn, db, clock=clock)
    clients = LabelRepo(conn, Dimension.CLIENT, clock)
    types = LabelRepo(conn, Dimension.TYPE, clock)
    client_ids = [clients.create(f"Client {i}").id for i in range(12)]
    type_ids = [types.create(t).id for t in ("Email/Chat", "Phone", "Meeting/Call", "Work")]
    rng = random.Random(42)
    start = datetime(2007, 1, 1, 8, 0, tzinfo=UTC)
    rows = []
    t = start
    for i in range(ROWS):
        minutes = rng.choice((2, 6, 15, 30, 45, 60, 90))
        t += timedelta(minutes=rng.choice((5, 20, 45, 90)))
        if t.hour >= 18:
            t = (t + timedelta(days=1)).replace(hour=8, minute=0)
        end = t + timedelta(minutes=minutes)
        rows.append(
            (
                f"u{i}",
                t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "Europe/Brussels",
                t.date().isoformat(),
                minutes * 60,
                rng.choice(client_ids),
                rng.choice(type_ids),
                f"note {i}" if i % 3 == 0 else None,
                "STOPWATCH" if i % 2 else "QUICKADD",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            )
        )
    with transaction(conn):
        conn.executemany(
            "INSERT INTO entry (uuid, started_at_utc, ended_at_utc, tz_name, local_date, "
            "duration_seconds, client_id, type_id, note, record_method, created_at, modified_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    conn.close()


def _timed(label: str, fn: object) -> float:
    t0 = time.perf_counter()
    fn()  # type: ignore[operator]
    dt = time.perf_counter() - t0
    print(f"{label}: {dt * 1000:.0f} ms")
    return dt


def test_log_window_responsive_at_50k_rows(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    clock = FakeClock(now=datetime(2026, 9, 11, 10, 0, tzinfo=UTC))
    db = tmp_path / "big.sqlite3"
    _timed("seed 50k rows", lambda: _seed(db, clock))

    conn = connect(db)
    clients = LabelRepo(conn, Dimension.CLIENT, clock)
    types = LabelRepo(conn, Dimension.TYPE, clock)
    repo = EntryRepo(conn, clock)
    assert repo.count() == ROWS
    from timetracker.data.settings_repo import SettingsRepo

    settings = SettingsService(SettingsRepo(conn))
    labels = LabelService(clients, types)
    entry_service = EntryService(clock, repo, clients, types, settings)
    exporter = ExportService(clock, db)

    timings: dict[str, float] = {}
    holder: dict[str, LogWindow] = {}

    def open_window() -> None:
        w = LogWindow(clock, repo, entry_service, labels, settings, exporter)
        qtbot.addWidget(w)
        w.show()
        holder["w"] = w

    timings["open (this week)"] = _timed("open (this week)", open_window)
    w = holder["w"]
    timings["filter: all time"] = _timed("filter: all time", lambda: w.set_preset(DatePreset.ALL))
    assert w.model.total_count == ROWS
    assert w.model.rowCount() == 1_000  # first page only
    timings["sort by duration"] = _timed(
        "sort by duration",
        lambda: w._on_header_clicked(Col.DURATION),  # noqa: SLF001
    )
    timings["sort by client"] = _timed(
        "sort by client",
        lambda: w._on_header_clicked(Col.CLIENT),  # noqa: SLF001
    )
    timings["filter: one client"] = _timed(
        "filter: one client", lambda: w.client.setCurrentIndex(3)
    )
    timings["scroll: next page"] = _timed("scroll: next page", w.model.fetchMore)
    w.client.setCurrentIndex(0)
    timings["search"] = _timed("search", lambda: (w.search.setText("note 4999"), w.apply_filters()))
    assert w.model.total_count == 3  # "note 49992", "note 49995", "note 49998" (i % 3 == 0)

    w.close()
    slow = {k: v for k, v in timings.items() if v > BUDGET_S}
    assert not slow, f"over the {BUDGET_S * 1000:.0f} ms budget: " + ", ".join(
        f"{k} {v * 1000:.0f} ms" for k, v in slow.items()
    )
    conn.close()
