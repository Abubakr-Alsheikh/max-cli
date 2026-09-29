"""Home: the command center. Live system gauges, key numbers, activity
charts, quick launch and a recent-activity feed.

The app refreshes this page every 2 seconds while it's showing. Every
widget updates only when its value changes, and the whole refresh is one
repaint (see PLANS/active/dashboard-design-system.md, R0 rules).
"""

import shutil
from collections import Counter, deque
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.content import Content
from textual.message import Message
from textual.widgets import Button, Digits, Static

from max_cli.common.utils import format_size
from max_cli.interface.tui.activity_log import (
    CATEGORY_ALIASES,
    ActivityEntry,
    ActivityLog,
)
from max_cli.interface.tui.widgets.charts import (
    Bar,
    BarChart,
    HBar,
    HBarChart,
    Meter,
    Spark,
)

HISTORY_SAMPLES = 60  # 2 minutes of gauge history at one sample per refresh
ACTIVITY_DAYS = 14
RECENT_ENTRIES = 7
GIGABYTE = 1024**3
BUSY_PERCENT = 85
WARM_PERCENT = 60

# Activity category -> (label, bar colour) for the "by type" chart.
CATEGORY_LOOK = {
    "download": ("Downloads", "$primary"),
    "command": ("Tools", "$accent"),
    "file_op": ("Files", "$warning"),
    "ai": ("AI", "$secondary"),
    "task": ("Queue", "$success"),
}
QUICK_LAUNCH = [
    ("download", "2", "Download"),
    ("tools", "3", "Tools"),
    ("files", "4", "Files"),
    ("chat", "5", "Ask AI"),
]


def greeting(now: datetime) -> str:
    if now.hour < 12:
        return "Good morning"
    if now.hour < 18:
        return "Good afternoon"
    return "Good evening"


def daily_counts(
    entries: list[ActivityEntry], today: date, days: int = ACTIVITY_DAYS
) -> list[Bar]:
    """Actions per day for the last `days` days, oldest first, today highlighted."""
    per_day = Counter((entry.timestamp or "")[:10] for entry in entries)
    bars = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        label = "now" if offset == 0 else day.strftime("%d")
        bars.append(Bar(label, per_day.get(day.isoformat(), 0), highlight=offset == 0))
    return bars


def category_bars(entries: list[ActivityEntry]) -> list[HBar]:
    """Actions per kind, largest first; only kinds that happened."""
    counts = Counter(
        CATEGORY_ALIASES.get(entry.category, entry.category) for entry in entries
    )
    bars = []
    for category, count in counts.most_common():
        label, style = CATEGORY_LOOK.get(category, (category.title(), "$text-muted"))
        bars.append(HBar(label, count, style))
    return bars


def load_colour(percent: float) -> str:
    if percent >= BUSY_PERCENT:
        return "$error"
    if percent >= WARM_PERCENT:
        return "$warning"
    return "$primary"


class Gauge(Vertical):
    """A live system value: big digits, a history or a meter, a detail line.

    `meter` shows how full it is instead of a 2-minute history: disk use
    barely moves, so its history is a flat block.
    """

    def __init__(self, title: str, *, id: str, meter: bool = False) -> None:
        super().__init__(id=id, classes="home-card gauge")
        self.border_title = title
        self.meter = meter
        self._history: deque[float] = deque(maxlen=HISTORY_SAMPLES)
        self._shown: Optional[tuple[str, str]] = None

    def compose(self) -> ComposeResult:
        with Horizontal(classes="gauge-top"):
            yield Digits("--", classes="gauge-value")
            yield Static("%", classes="gauge-unit")
        if self.meter:
            yield Meter(classes="gauge-meter")
        else:
            yield Spark(classes="gauge-spark")
        yield Static("", classes="gauge-detail")

    def show(self, percent: float, detail: str) -> None:
        if self.meter:
            self.query_one(Meter).set_value(percent, load_colour(percent))
        else:
            self._history.append(percent)
            self.query_one(Spark).set_data(list(self._history), load_colour(percent))
        value = f"{percent:.0f}"
        if (value, detail) == self._shown:
            return
        self._shown = (value, detail)
        digits = self.query_one(Digits)
        digits.update(value)
        digits.styles.color = self.app.theme_variables.get(
            load_colour(percent).lstrip("$"), None
        )
        self.query_one(".gauge-detail", Static).update(
            Content.styled(detail, "$text-muted")
        )


class Tile(Vertical):
    """One key number with a label under it."""

    def __init__(self, title: str, *, id: str) -> None:
        super().__init__(id=id, classes="home-card tile")
        self.border_title = title
        self._shown: Optional[tuple[str, str]] = None

    def compose(self) -> ComposeResult:
        yield Digits("0", classes="tile-value")
        yield Static("", classes="tile-note")

    def show(self, value: str, note: str) -> None:
        if (value, note) == self._shown:
            return
        self._shown = (value, note)
        self.query_one(Digits).update(value)
        self.query_one(".tile-note", Static).update(Content.styled(note, "$text-muted"))


class HomePanel(Vertical):
    """The dashboard's first page."""

    DEFAULT_CSS = """
    HomePanel {
        padding: 1 2;
    }
    #home-header {
        height: 3;
        margin-bottom: 1;
    }
    #home-brand {
        width: 1fr;
        height: 3;
    }
    #home-status {
        width: auto;
        height: 3;
        content-align: right middle;
    }
    HomePanel .home-card {
        background: $surface;
        border: round $border;
        border-title-color: $primary;
        border-title-style: bold;
        padding: 0 1;
    }
    HomePanel .home-card:hover {
        border: round $primary;
    }
    #home-gauges, #home-tiles, #home-charts, #home-bottom {
        height: auto;
        grid-gutter: 0 2;
        margin-bottom: 1;
    }
    #home-gauges {
        grid-size: 3;
        grid-columns: 1fr 1fr 1fr;
    }
    #home-tiles {
        grid-size: 4;
        grid-columns: 1fr 1fr 1fr 1fr;
    }
    #home-charts {
        grid-size: 2;
        grid-columns: 2fr 1fr;
    }
    #home-bottom {
        grid-size: 2;
        grid-columns: 1fr 2fr;
    }
    HomePanel .gauge {
        height: 9;
    }
    HomePanel .gauge-top {
        height: 3;
    }
    HomePanel .gauge-value {
        width: auto;
        color: $primary;
        text-style: bold;
    }
    HomePanel .gauge-unit {
        width: 2;
        height: 3;
        content-align: left bottom;
        color: $text-muted;
    }
    HomePanel .gauge-spark {
        height: 2;
        margin-top: 1;
    }
    HomePanel .gauge-meter {
        margin-top: 2;
    }
    HomePanel .tile {
        height: 6;
    }
    HomePanel .tile-value {
        width: 100%;
        text-align: center;
        color: $primary;
        text-style: bold;
    }
    HomePanel .tile-note {
        width: 100%;
        text-align: center;
    }
    #home-activity-card {
        height: 14;
    }
    #home-types-card {
        height: 14;
    }
    #home-types {
        margin-top: 1;
    }
    #home-success {
        margin-top: 1;
    }
    #home-launch-card, #home-recent-card {
        height: 11;
    }
    #home-launch-card Button {
        width: 100%;
        margin-bottom: 0;
        background: $boost;
        border: none;
        height: 2;
        content-align: left middle;
        text-align: left;
    }
    #home-launch-card Button:hover {
        background: $primary 30%;
        color: $text;
    }
    """

    class OpenPage(Message):
        """A quick-launch button asks the app to show a page."""

        def __init__(self, section_id: str) -> None:
            super().__init__()
            self.section_id = section_id

    def compose(self) -> ComposeResult:
        with Horizontal(id="home-header"):
            yield Static(self._brand(), id="home-brand")
            yield Static(self._status(), id="home-status")
        with Grid(id="home-gauges"):
            yield Gauge("CPU", id="gauge-cpu")
            yield Gauge("MEMORY", id="gauge-mem")
            yield Gauge("DISK", id="gauge-disk", meter=True)
        with Grid(id="home-tiles"):
            yield Tile("DOWNLOADS", id="tile-downloads")
            yield Tile("ACTIONS", id="tile-actions")
            yield Tile("QUEUE", id="tile-queue")
            yield Tile("DOWNLOADED", id="tile-size")
        with Grid(id="home-charts"):
            with Vertical(id="home-activity-card", classes="home-card"):
                yield BarChart(id="home-activity-chart")
            with Vertical(id="home-types-card", classes="home-card"):
                yield HBarChart(id="home-types")
                yield Static("", id="home-success")
        with Grid(id="home-bottom"):
            with Vertical(id="home-launch-card", classes="home-card"):
                for section_id, key, label in QUICK_LAUNCH:
                    yield Button(
                        Content.assemble((f" {key} ", "bold $primary"), f"  {label}"),
                        id=f"launch-{section_id}",
                    )
            with Vertical(id="home-recent-card", classes="home-card"):
                yield Static("", id="home-recent")

    def on_mount(self) -> None:
        self.query_one(
            "#home-activity-card"
        ).border_title = f"ACTIVITY · LAST {ACTIVITY_DAYS} DAYS"
        self.query_one("#home-types-card").border_title = "BY TYPE"
        self.query_one("#home-launch-card").border_title = "QUICK LAUNCH"
        self.query_one("#home-recent-card").border_title = "RECENT"
        self.refresh_data()

    # --- header --------------------------------------------------------------

    @staticmethod
    def _brand() -> Content:
        now = datetime.now()
        return Content.assemble(
            ("◢◤ ", "bold $secondary"),
            ("MAX", "bold $primary"),
            (" // COMMAND CENTER\n", "bold"),
            (f"{greeting(now)}  ·  {now:%a %d %b  %H:%M}", "$text-muted"),
        )

    @staticmethod
    def _status() -> Content:
        from max_cli.common.ffmpeg_resolver import FFmpegResolver
        from max_cli.config import settings

        ffmpeg = bool(shutil.which("ffmpeg") or FFmpegResolver.get_cached_resolution())
        ai = bool(settings.OPENAI_API_KEY)

        def light(on: bool, label: str) -> tuple[str, str]:
            return (f"● {label}   ", "$success" if on else "$text-muted")

        return Content.assemble(
            light(True, "ONLINE"),
            light(ffmpeg, "FFMPEG" if ffmpeg else "NO FFMPEG"),
            light(ai, "AI" if ai else "AI OFF"),
        )

    # --- refresh -------------------------------------------------------------

    def refresh_data(self) -> None:
        # One repaint for all of this page's updates, not one per label.
        with self.app.batch_update():
            self._refresh_now()

    def _refresh_now(self) -> None:
        self.query_one("#home-brand", Static).update(self._brand())
        self._refresh_gauges()
        entries = ActivityLog().get_entries(limit=10_000)
        self._refresh_tiles(entries)
        self._refresh_charts(entries)
        self._refresh_recent(entries)

    def _refresh_gauges(self) -> None:
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=None)
            cores = psutil.cpu_count() or 0
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage(Path.home().anchor)
        except (ImportError, OSError):
            return
        self.query_one("#gauge-cpu", Gauge).show(cpu, f"{cores} cores")
        self.query_one("#gauge-mem", Gauge).show(
            memory.percent,
            f"{memory.used / GIGABYTE:.1f} of {memory.total / GIGABYTE:.1f} GB",
        )
        self.query_one("#gauge-disk", Gauge).show(
            disk.percent, f"{format_size(disk.free)} free of {format_size(disk.total)}"
        )

    def _refresh_tiles(self, entries: list[ActivityEntry]) -> None:
        from max_cli.core.engines.download_history import DownloadHistory
        from max_cli.core.engines.task_manager import get_task_manager

        history = DownloadHistory()
        downloads = history.get_stats()
        today = date.today().isoformat()
        # Both numbers from the download history, so they can't disagree.
        downloads_today = sum(
            1
            for entry in history.get_recent(limit=downloads["total"] or 1)
            if str(entry.get("timestamp", "")).startswith(today)
        )
        self.query_one("#tile-downloads", Tile).show(
            str(downloads["total"]), f"{downloads_today} today"
        )

        finished = [entry for entry in entries if entry.status in ("success", "failed")]
        succeeded = sum(1 for entry in finished if entry.status == "success")
        rate = (
            f"{succeeded * 100 // len(finished)}% succeeded" if finished else "none yet"
        )
        self.query_one("#tile-actions", Tile).show(str(len(finished)), rate)

        manager = get_task_manager()
        manager.refresh()
        stats = manager.get_stats()
        running, waiting = int(stats.get("running", 0)), int(stats.get("pending", 0))
        self.query_one("#tile-queue", Tile).show(
            str(running + waiting), f"{running} running · {waiting} waiting"
        )

        total_size = downloads["total_size"]
        if total_size:
            size, unit = format_size(total_size).split(" ", 1)
            self.query_one("#tile-size", Tile).show(size, unit)
        else:
            self.query_one("#tile-size", Tile).show("0", "nothing yet")

    def _refresh_charts(self, entries: list[ActivityEntry]) -> None:
        self.query_one("#home-activity-chart", BarChart).set_data(
            daily_counts(entries, date.today())
        )
        self.query_one("#home-types", HBarChart).set_data(category_bars(entries))
        failed = sum(1 for entry in entries if entry.status == "failed")
        note = Content.assemble(
            ("✗ ", "$error" if failed else "$text-muted"),
            (f"{failed} failed", "$text-muted"),
        )
        self.query_one("#home-success", Static).update(note)

    def _refresh_recent(self, entries: list[ActivityEntry]) -> None:
        lines = [self._recent_line(entry) for entry in entries[:RECENT_ENTRIES]]
        text = (
            Content("\n").join(lines)
            if lines
            else Content.styled(
                "Nothing yet. Press 2 to download something.", "$text-muted"
            )
        )
        self.query_one("#home-recent", Static).update(text)

    @staticmethod
    def _recent_line(entry: ActivityEntry) -> Content:
        ok = entry.status == "success"
        details: Any = entry.details or {}
        subject = str(
            details.get("title") or details.get("url") or details.get("target") or ""
        )
        category = CATEGORY_ALIASES.get(entry.category, entry.category)
        label = CATEGORY_LOOK.get(category, (category.title(), ""))[0]
        return Content.assemble(
            ((entry.timestamp or "")[11:16] + "  ", "$text-muted"),
            ("✓ " if ok else "✗ ", "$success" if ok else "$error"),
            (f"{label:<10}", "bold"),
            (subject[:60], "$text-muted"),
        )

    @on(Button.Pressed)
    def _on_launch(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("launch-"):
            event.stop()
            self.post_message(self.OpenPage(button_id.removeprefix("launch-")))
