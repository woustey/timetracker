"""Day timeline (FR-509, v1.1): one local day, entries as blocks on a vertical
hour axis, the gaps between them hatched and labelled so unaccounted time is
obvious at a glance.

``core/timeline.py`` computes the geometry (minutes, lanes, gaps); this paints
it. Colours come from the palette so light and dark themes both read; each
client gets a stable hue from a small palette (labels have no colour of their
own until FR-408). Double-clicking a block asks the log to reveal the entry.
"""

from __future__ import annotations

from datetime import date, time, timedelta

from PySide6.QtCore import QDate, QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import (
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from timetracker.core.clock import Clock
from timetracker.core.duration import format_hm
from timetracker.core.models import Dimension, Entry
from timetracker.core.timeline import MINUTES_PER_DAY, DayLayout, layout_day
from timetracker.core.timeutil import local_date_for, zone
from timetracker.data.entry_repo import EntryRepo
from timetracker.services.entry_service import EntryService
from timetracker.services.label_service import LabelService
from timetracker.ui import formatting

HOUR_PX = 56
AXIS_W = 56
MARGIN = 8
_CLIENT_HUES = (210, 150, 30, 275, 0, 180, 60, 320, 100, 240)


class DayCanvas(QWidget):
    """The painted timeline. Knows minutes and pixels, nothing about the database."""

    entry_activated = Signal(int)  # entry id (double-click)
    entry_hovered = Signal(int)  # entry id, or -1

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = DayLayout(date.today())
        self._names: dict[
            int, tuple[str, str, str, int | None]
        ] = {}  # id → (client, type, note, client_id)
        self._first_hour = 0
        self._last_hour = 24
        self._now_min: int | None = None
        self._hover = -1
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(320)

    # -- data ----------------------------------------------------------------

    def set_layout(
        self,
        layout: DayLayout,
        names: dict[int, tuple[str, str, str, int | None]],
        *,
        workday_start: time,
        now_min: int | None,
    ) -> None:
        self._layout = layout
        self._names = names
        self._now_min = now_min
        # Show the working day at least; widen to whatever the entries need.
        first = min(workday_start.hour, (layout.first_min or workday_start.hour * 60) // 60)
        last = max(18, -(-(layout.last_min or 18 * 60) // 60))
        if now_min is not None:
            first = min(first, now_min // 60)
            last = max(last, -(-now_min // 60))
        self._first_hour = max(0, first)
        self._last_hour = min(24, max(last, self._first_hour + 1))
        self.setFixedHeight((self._last_hour - self._first_hour) * HOUR_PX + 2 * MARGIN)
        self.update()

    @property
    def layout_data(self) -> DayLayout:
        return self._layout

    # -- geometry ------------------------------------------------------------

    def _y(self, minute: int) -> float:
        return MARGIN + (minute - self._first_hour * 60) * HOUR_PX / 60.0

    def block_rects(self) -> list[tuple[int, QRectF]]:
        width = self.width() - AXIS_W - MARGIN
        out: list[tuple[int, QRectF]] = []
        for b in self._layout.blocks:
            lane_w = width / max(1, b.lanes)
            x = AXIS_W + b.lane * lane_w
            top, bottom = self._y(b.start_min), self._y(b.end_min)
            out.append((b.entry_id, QRectF(x + 1, top, lane_w - 3, max(3.0, bottom - top - 1))))
        return out

    def block_at(self, pos: QPoint) -> int:
        for entry_id, rect in self.block_rects():
            if rect.contains(pos):
                return entry_id
        return -1

    # -- painting ------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        text = pal.color(pal.ColorRole.Text)
        grid = pal.color(pal.ColorRole.Mid)
        base = pal.color(pal.ColorRole.Base)
        p.fillRect(self.rect(), base)
        width = self.width() - AXIS_W - MARGIN
        small = QFont(self.font())
        small.setPointSizeF(max(7.0, self.font().pointSizeF() - 1))
        fm = QFontMetrics(small)

        # Hour lines and labels.
        p.setFont(small)
        for hour in range(self._first_hour, self._last_hour + 1):
            y = self._y(hour * 60)
            p.setPen(QPen(grid, 1))
            p.drawLine(AXIS_W - 4, int(y), self.width() - MARGIN, int(y))
            p.setPen(text)
            label = formatting.fmt_time(time(hour % 24, 0))
            p.drawText(
                QRect(0, int(y) - fm.height() // 2, AXIS_W - 8, fm.height()),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                label,
            )
            if hour < self._last_hour:
                y2 = self._y(hour * 60 + 30)
                p.setPen(QPen(grid, 1, Qt.PenStyle.DotLine))
                p.drawLine(AXIS_W, int(y2), self.width() - MARGIN, int(y2))

        # Gaps: hatched, labelled with their length.
        hatch = QBrush(
            QColor(text.red(), text.green(), text.blue(), 40), Qt.BrushStyle.BDiagPattern
        )
        for gap in self._layout.gaps:
            rect = QRectF(
                AXIS_W, self._y(gap.start_min), width, self._y(gap.end_min) - self._y(gap.start_min)
            )
            p.fillRect(rect, hatch)
            if rect.height() >= fm.height() + 2:
                p.setPen(text)
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"gap {format_hm(gap.minutes * 60)}")

        # Blocks.
        for entry_id, rect in self.block_rects():
            client, type_name, note, client_id = self._names.get(entry_id, ("", "", "", None))
            colour = _client_colour(client_id, dark=base.lightness() < 128)
            if entry_id == self._hover:
                colour = colour.lighter(115)
            p.setPen(QPen(colour.darker(130), 1))
            p.setBrush(colour)
            p.drawRoundedRect(rect, 4, 4)
            block = next(b for b in self._layout.blocks if b.entry_id == entry_id)
            if block.continues_before or block.continues_after:
                p.setPen(QPen(colour.darker(160), 1, Qt.PenStyle.DashLine))
                edge = rect.top() if block.continues_before else rect.bottom()
                p.drawLine(int(rect.left()), int(edge), int(rect.right()), int(edge))
            p.setPen(QColor("#ffffff") if colour.lightness() < 150 else QColor("#1f2329"))
            lines = [x for x in (client, type_name, note) if x]
            inner = rect.adjusted(6, 2, -4, -2)
            p.setFont(small)
            shown = " · ".join(lines) if rect.height() < 2 * fm.height() + 4 else "\n".join(lines)
            p.drawText(
                inner,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                shown,
            )

        # Now line.
        if (
            self._now_min is not None
            and self._first_hour * 60 <= self._now_min <= self._last_hour * 60
        ):
            y = self._y(self._now_min)
            p.setPen(QPen(QColor("#e5484d"), 2))
            p.drawLine(AXIS_W - 4, int(y), self.width() - MARGIN, int(y))
        p.end()

    # -- mouse ---------------------------------------------------------------

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        entry_id = self.block_at(event.position().toPoint())
        if entry_id != self._hover:
            self._hover = entry_id
            self.entry_hovered.emit(entry_id)
            names = self._names.get(entry_id)
            self.setToolTip(" · ".join(x for x in names[:3] if x) if names else "")
            self.update()

    def leaveEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        if self._hover != -1:
            self._hover = -1
            self.entry_hovered.emit(-1)
            self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        entry_id = self.block_at(event.position().toPoint())
        if entry_id >= 0:
            self.entry_activated.emit(entry_id)


def _client_colour(client_id: int | None, *, dark: bool) -> QColor:
    if client_id is None:
        return QColor("#8a97a8") if not dark else QColor("#5c6675")
    hue = _CLIENT_HUES[client_id % len(_CLIENT_HUES)]
    return QColor.fromHsl(hue, 120 if not dark else 90, 150 if not dark else 110)


class DayView(QWidget):
    """Header (date stepper, totals) + scrollable canvas. Re-lays out on entry changes."""

    entry_activated = Signal(int, object)  # entry id, local date

    def __init__(
        self,
        clock: Clock,
        repo: EntryRepo,
        entries: EntryService,
        labels: LabelService,
        *,
        workday_start: time = time(9, 0),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._clock = clock
        self._repo = repo
        self._labels = labels
        self._workday_start = workday_start
        self._day = local_date_for(clock.now_utc(), clock.tz_name())

        self.prev_button = QToolButton()
        self.prev_button.setText("‹")
        self.prev_button.setAccessibleName("Previous day")
        self.prev_button.clicked.connect(lambda: self.set_day(self._day - timedelta(days=1)))
        self.next_button = QToolButton()
        self.next_button.setText("›")
        self.next_button.setAccessibleName("Next day")
        self.next_button.clicked.connect(lambda: self.set_day(self._day + timedelta(days=1)))
        self.today_button = QToolButton()
        self.today_button.setText("Today")
        self.today_button.clicked.connect(
            lambda: self.set_day(local_date_for(self._clock.now_utc(), self._clock.tz_name()))
        )
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("ddd d MMM yyyy")
        self.date_edit.setAccessibleName("Day")
        self.date_edit.dateChanged.connect(lambda d: self.set_day(d.toPython()))
        self.totals = QLabel("")
        self.totals.setAccessibleName("Day totals")

        header = QHBoxLayout()
        header.addWidget(self.prev_button)
        header.addWidget(self.date_edit)
        header.addWidget(self.next_button)
        header.addWidget(self.today_button)
        header.addStretch(1)
        header.addWidget(self.totals)

        self.canvas = DayCanvas()
        self.canvas.entry_activated.connect(lambda i: self.entry_activated.emit(i, self._day))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.canvas)
        self.scroll = scroll

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.addLayout(header)
        root.addWidget(scroll, 1)

        entries.entries_changed.connect(lambda _u: self.refresh())
        labels.labels_changed.connect(lambda _d: self.refresh())
        self.set_day(self._day)

    # -- state ---------------------------------------------------------------

    @property
    def day(self) -> date:
        return self._day

    def set_day(self, day: date) -> None:
        self._day = day
        if self.date_edit.date().toPython() != day:
            self.date_edit.blockSignals(True)
            self.date_edit.setDate(QDate(day.year, day.month, day.day))
            self.date_edit.blockSignals(False)
        self.refresh()

    def refresh(self) -> None:
        entries = self._repo.list_for_date(self._day)
        # Entries that started the day before but run into this one are on the
        # previous local_date; include them so an overnight block is drawn.
        entries += [
            e
            for e in self._repo.list_for_date(self._day - timedelta(days=1))
            if e.ended_at_utc.astimezone(zone(self._clock.tz_name())).date() >= self._day
        ]
        tz_name = self._clock.tz_name()
        layout = layout_day(entries, self._day, tz_name)
        names = {e.id: self._names_for(e) for e in entries}
        now_local = self._clock.now_utc().astimezone(zone(tz_name))
        now_min = now_local.hour * 60 + now_local.minute if now_local.date() == self._day else None
        self.canvas.set_layout(layout, names, workday_start=self._workday_start, now_min=now_min)
        n = len(layout.blocks)
        if layout.is_empty:
            self.totals.setText("No entries")
        else:
            first = _hm(layout.first_min or 0)
            last = _hm(layout.last_min or 0)
            noun = "entry" if n == 1 else "entries"
            self.totals.setText(
                f"{n} {noun} · tracked {format_hm(layout.tracked_seconds)}"
                f" · gaps {format_hm(layout.gap_minutes * 60)} · {first}–{last}"
            )

    def _names_for(self, e: Entry) -> tuple[str, str, str, int | None]:
        client = self._labels.get(Dimension.CLIENT, e.client_id).name if e.client_id else ""
        type_name = self._labels.get(Dimension.TYPE, e.type_id).name if e.type_id else ""
        return client, type_name, e.note or "", e.client_id


def _hm(minute: int) -> str:
    minute = min(minute, MINUTES_PER_DAY - 1)
    return formatting.fmt_time(time(minute // 60, minute % 60))
