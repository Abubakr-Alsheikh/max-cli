"""Home: the launchpad and command center, the first page a user sees.

Top to bottom: who and when (with a streak), an ask bar that hands a
request to the AI page, the launchpad (every page with what it's for, plus
the actions you use most), live system meters, key numbers, the activity of
the last two weeks split by kind, and what ran lately.

Every number comes from the activity log over one window (`home_stats`), so
the tiles, the chart and BY TYPE agree; the queue tile is live.

The app refreshes this page every 2 seconds while it's showing. Every
widget updates only when its value changes, and the whole refresh is one
repaint (see PLANS/active/dashboard-design-system.md, R0 rules).
"""

import shutil
from collections import deque
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.content import Content
from textual.events import Click
from textual.geometry import Size
from textual.widget import Widget
from textual.widgets import Digits, Input, Static

from max_cli.common.activity_log import ActivityEntry, ActivityLog
from max_cli.common.utils import format_size
from max_cli.interface.tui import home_stats
from max_cli.interface.tui.messages import AskAI, OpenPage
from max_cli.interface.tui.widgets.charts import (
    HBar,
    HBarChart,
    Meter,
    Spark,
    StackChart,
)
from max_cli.interface.tui.widgets.sidebar import (
    ICON_WIDTH,
    SECTION_KEYS,
    page_colour,
    page_icon,
)

HISTORY_SAMPLES = 60  # 2 minutes of CPU history at one sample per refresh
GIGABYTE = 1024**3
BUSY_PERCENT = 85
WARM_PERCENT = 60
LOG_LIMIT = 10_000
NARROW_WIDTH = 86  # below this many columns, Home stacks its cards
AGAIN_LABEL_WIDTH = 15  # "PICK UP AGAIN  "
CHIP_EXTRA = 5  # a chip's arrow, padding and gap around its name
ASK_EXAMPLE = 'Ask Max in plain words, e.g. "convert every .m4a here to mp3"'
ASK_OFF = "Set up an AI on the Settings page ({key}) to ask Max in plain words"

# (page id, name, what it's for) on the launchpad, in sidebar order.
LAUNCHPAD = [
    ("download", "Download", "videos · music"),
    ("video", "Video", "compress · cut"),
    ("audio", "Audio", "tags · to MP3"),
    ("images", "Images", "shrink · resize"),
    ("pdf", "PDF", "merge · OCR"),
    ("files", "Files", "sort · dedupe"),
    ("ai", "Ask AI", "plain words"),
    ("activity", "Activity", "queue · history"),
]


# A launch tile lights up in its page's colour, like its chip.
LAUNCH_HOVER_CSS = "".join(
    f"""
    Launcher.-page-{page}:hover, Launcher.-page-{page}:focus {{
        background: {page_colour(page)} 15%;
        border: round {page_colour(page)};
    }}"""
    for page, _name, _purpose in LAUNCHPAD
)


def greeting(now: datetime) -> str:
    if now.hour < 12:
        return "Good morning"
    if now.hour < 18:
        return "Good afternoon"
    return "Good evening"


def load_colour(percent: float) -> str:
    if percent >= BUSY_PERCENT:
        return "$error"
    if percent >= WARM_PERCENT:
        return "$warning"
    return "$primary"


def trend(this_week: int, last_week: int) -> Content:
    """`▲ 9 vs last week`: green up, amber down."""
    if this_week == last_week:
        return Content.styled("= last week", "$text-muted")
    if this_week > last_week:
        return Content.assemble(
            ("▲ ", "$success"),
            (f"{this_week - last_week} vs last week", "$text-muted"),
        )
    return Content.assemble(
        ("▼ ", "$warning"),
        (f"{last_week - this_week} vs last week", "$text-muted"),
    )


class Tile(Vertical):
    """One key number with a line under it. A tile with `link` opens that
    page (and tab) when clicked."""

    def __init__(self, title: str, *, id: str, link: str = "", tab: str = "") -> None:
        super().__init__(id=id, classes="home-card tile")
        self.border_title = title
        self.link, self.tab = link, tab
        self._shown: Optional[tuple[str, str]] = None
        if link:
            self.tooltip = "Click to open"

    def compose(self) -> ComposeResult:
        yield Digits("0", classes="tile-value")
        yield Static("", classes="tile-note")

    def show(self, value: str, note: "str | Content") -> None:
        key = (value, str(note))
        if key == self._shown:
            return
        self._shown = key
        self.query_one(Digits).update(value)
        text = (
            note if isinstance(note, Content) else Content.styled(note, "$text-muted")
        )
        self.query_one(".tile-note", Static).update(text)

    def on_click(self, event: Click) -> None:
        if self.link:
            event.stop()
            self.post_message(OpenPage(self.link, tab=self.tab))


class Launcher(Widget, can_focus=True):
    """A launchpad tile or a "pick up again" chip: click or Enter runs it.

    Not a Button: the app's CSS styles every Button, and app CSS beats a
    widget's own, so the tiles lost their background and hover.
    """

    DEFAULT_CSS = """
    Launcher {
        height: 4;
        width: 1fr;
        padding: 0 1;
        background: $boost;
        border: round $border;
    }
    Launcher:hover, Launcher:focus {
        background: $primary 18%;
        border: round $primary;
    }
    Launcher.-chip {
        height: 1;
        width: auto;
        padding: 0 1;
        margin: 0 1 0 0;
        color: $primary;
    }
    Launcher.-chip {
        border: none;
    }
    Launcher.-chip:hover, Launcher.-chip:focus {
        border: none;
        background: $primary 25%;
    }
    """
    BINDINGS = [("enter", "launch", "Open"), ("space", "launch", "Open")]

    def __init__(
        self,
        label: Content,
        *,
        id: Optional[str] = None,
        page: str = "",
        action: str = "",
        chip: bool = False,
        classes: str = "",
    ) -> None:
        super().__init__(id=id, classes=f"{'-chip' if chip else ''} {classes}".strip())
        self.label = label
        self.page, self.action = page, action
        self.tooltip = f"Open {action.replace('.', ' ')}" if action else None

    def render(self) -> Content:
        return self.label

    def action_launch(self) -> None:
        if self.action:
            self.app.open_action(self.action)  # type: ignore[attr-defined]  # MaxDashboardApp's own method
        elif self.page:
            self.post_message(OpenPage(self.page))

    def on_click(self, event: Click) -> None:
        event.stop()
        self.action_launch()


class SystemLine(Vertical):
    """One live system value: name, meter, percent; a detail line under it."""

    def __init__(self, name: str, *, id: str, spark: bool = False) -> None:
        super().__init__(id=id, classes="system-line")
        self.label = name
        self.spark = spark
        self._history: deque[float] = deque(maxlen=HISTORY_SAMPLES)
        self._shown: Optional[tuple[str, str]] = None

    def compose(self) -> ComposeResult:
        with Horizontal(classes="system-top"):
            yield Static(Content.styled(self.label, "bold"), classes="system-name")
            yield Meter(classes="system-meter")
            yield Static("", classes="system-value")
        if self.spark:
            yield Spark(classes="system-spark")
        else:
            yield Static("", classes="system-detail")

    def show(self, percent: float, detail: str, full: str = "") -> None:
        """`detail` fits under the meter; `full` (the tooltip) says it all."""
        colour = load_colour(percent)
        self.query_one(Meter).set_value(percent, colour)
        if self.spark:
            self._history.append(percent)
            self.query_one(Spark).set_data(list(self._history), colour)
        shown = (f"{percent:.0f}", detail)
        if shown == self._shown:
            return
        self._shown = shown
        self.query_one(".system-value", Static).update(
            Content.styled(f"{percent:>3.0f}%", f"bold {colour}")
        )
        self.tooltip = full or detail
        if not self.spark:
            self.query_one(".system-detail", Static).update(
                Content.styled(detail, "$text-muted")
            )


class RecentList(Widget):
    """What ran lately, in columns that fit the card's width: when, result,
    kind, action, what it ran on, what came out, time taken, via AI."""

    DEFAULT_CSS = """
    RecentList {
        height: auto;
        width: 1fr;
    }
    """
    EMPTY = "Nothing yet. Press {key} to download something, or ask Max above."
    WHEN, WHAT, TOOK = 10, 22, 8

    def __init__(self, *, id: str) -> None:
        super().__init__(id=id)
        self._rows: list[home_stats.RecentRow] = []

    def set_rows(self, rows: list[home_stats.RecentRow]) -> None:
        if rows != self._rows:
            self._rows = rows
            self.refresh(layout=True)

    def get_content_height(self, container: Size, viewport: Size, width: int) -> int:
        return max(1, len(self._rows))

    def render(self) -> Content:
        if not self._rows:
            return Content.styled(
                self.EMPTY.format(key=SECTION_KEYS["download"]), "$text-muted"
            )
        width = max(40, self.content_size.width)
        free = width - (self.WHEN + 2 + self.WHAT + self.TOOK + 4)
        subject_width = max(10, free // 2)
        result_width = max(8, free - subject_width - 1)
        return Content("\n").join(
            self._line(row, subject_width, result_width) for row in self._rows
        )

    def _line(
        self, row: home_stats.RecentRow, subject_width: int, result_width: int
    ) -> Content:
        return Content.assemble(
            (_fit(row.when, self.WHEN), "$text-muted"),
            ("✓ " if row.ok else "✗ ", "$success" if row.ok else "$error"),
            (_fit(f"{row.kind} {row.what}", self.WHAT), f"bold {row.style}"),
            (_fit(row.subject, subject_width) + " ", ""),
            (
                _fit(row.result, result_width),
                "$text-muted" if row.ok else "$error",
            ),
            (_fit(row.took, self.TOOK, right=True), "$text-muted"),
            (" AI" if row.via_ai else "   ", "bold $accent"),
        )


def _fit(text: str, width: int, right: bool = False) -> str:
    """`text` cut or padded to `width` columns, with … when cut."""
    if len(text) > width:
        text = text[: max(0, width - 2)] + "… "
    return text.rjust(width) if right else text.ljust(width)


class HomePanel(Vertical):
    """The dashboard's first page."""

    DEFAULT_CSS = (
        """
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
        border-subtitle-color: $text-muted;
        padding: 0 1;
    }
    HomePanel .home-card:hover, HomePanel .home-card:focus-within {
        border: round $primary;
    }
    /* The ask bar: the page's hook, so it glows in the brand colour. */
    #home-ask {
        height: 3;
        margin-bottom: 1;
        border: round $secondary 60%;
        border-title-color: $secondary;
    }
    #home-ask:focus-within {
        border: round $secondary;
    }
    #home-ask-mark {
        width: 3;
        color: $secondary;
        text-style: bold;
        content-align: left middle;
    }
    #home-ask-input {
        width: 1fr;
        border: none;
        background: $surface;
        padding: 0;
        height: 1;
    }
    #home-tiles, #home-charts, #home-bottom {
        height: auto;
        grid-gutter: 0 2;
        margin-bottom: 1;
    }
    #home-bottom {
        grid-size: 2;
        grid-columns: 3fr 1fr;
    }
    #home-tiles {
        grid-size: 4;
        grid-columns: 1fr 1fr 1fr 1fr;
    }
    /* Narrow windows: two launch tiles a row, cards stacked. */
    HomePanel.-narrow #home-launch-grid {
        grid-size: 2;
        grid-columns: 1fr 1fr;
        height: 16;
    }
    HomePanel.-narrow #home-launch-card {
        height: 19;
    }
    HomePanel.-narrow #home-tiles {
        grid-size: 2;
        grid-columns: 1fr 1fr;
    }
    HomePanel.-narrow #home-charts, HomePanel.-narrow #home-bottom {
        grid-size: 1;
        grid-columns: 1fr;
    }
    #home-charts {
        grid-size: 2;
        grid-columns: 2fr 1fr;
    }
    #home-launch-card {
        height: 11;
        margin-bottom: 1;
    }
    #home-system-card {
        height: 12;
    }
    #home-launch-grid {
        grid-size: 4;
        grid-columns: 1fr 1fr 1fr 1fr;
        grid-gutter: 0 1;
        height: 8;
    }
    #home-again {
        height: 1;
    }
    #home-again-label {
        width: auto;
        color: $text-muted;
        text-style: bold;
    }
    HomePanel .system-line {
        height: 3;
    }
    #system-cpu {
        height: 4;
    }
    HomePanel .system-top {
        height: 1;
    }
    HomePanel .system-name {
        width: 8;
    }
    HomePanel .system-meter {
        width: 1fr;
    }
    HomePanel .system-value {
        width: 5;
        text-align: right;
    }
    HomePanel .system-spark {
        height: 2;
        margin-left: 8;
        margin-right: 5;
    }
    HomePanel .system-detail {
        height: 1;
        margin-left: 8;
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
    #tile-queue:hover {
        background: $boost;
    }
    #home-activity-card, #home-types-card {
        height: 14;
    }
    #home-types {
        margin-top: 1;
    }
    #home-types-note {
        margin-top: 1;
    }
    #home-recent-card {
        height: 12;
    }
    """
        + LAUNCH_HOVER_CSS
    )

    OpenPage = OpenPage

    def __init__(self, *, id: str) -> None:
        super().__init__(id=id)
        self._again: list[str] = []  # the "pick up again" actions shown
        self._top: list[str] = []  # the actions you use most, before fitting
        self._known_actions: set[str] = set()

    def compose(self) -> ComposeResult:
        with Horizontal(id="home-header"):
            yield Static(self._brand(0), id="home-brand")
            yield Static(self._status(), id="home-status")
        with Horizontal(id="home-ask", classes="home-card"):
            yield Static("›", id="home-ask-mark")
            yield Input(placeholder=self._ask_hint(), id="home-ask-input")
        with Vertical(id="home-launch-card", classes="home-card"):
            with Grid(id="home-launch-grid"):
                for section_id, name, purpose in LAUNCHPAD:
                    yield Launcher(
                        self._launch_label(section_id, name, purpose),
                        id=f"launch-{section_id}",
                        page=section_id,
                        classes=f"-page-{section_id}",
                    )
            with Horizontal(id="home-again"):
                yield Static("PICK UP AGAIN  ", id="home-again-label")
        with Grid(id="home-tiles"):
            yield Tile("THIS WEEK", id="tile-week")
            yield Tile("SUCCESS %", id="tile-actions")
            yield Tile("SPACE SAVED", id="tile-saved")
            yield Tile("QUEUE", id="tile-queue", link="activity", tab="queue")
        with Grid(id="home-charts"):
            with Vertical(id="home-activity-card", classes="home-card"):
                yield StackChart(id="home-activity-chart")
            with Vertical(id="home-types-card", classes="home-card"):
                yield HBarChart(id="home-types")
                yield Static("", id="home-types-note")
        with Grid(id="home-bottom"):
            with Vertical(id="home-recent-card", classes="home-card"):
                yield RecentList(id="home-recent")
            with Vertical(id="home-system-card", classes="home-card"):
                yield SystemLine("CPU", id="system-cpu", spark=True)
                yield SystemLine("MEMORY", id="system-mem")
                yield SystemLine("DISK", id="system-disk")

    def on_mount(self) -> None:
        from max_cli.core.catalog import actions_for, group_names
        from max_cli.core.catalog.spec import Surface

        days = home_stats.WINDOW_DAYS
        self.query_one("#home-ask").border_title = "ASK MAX"
        self.query_one("#home-launch-card").border_title = "LAUNCHPAD"
        self.query_one("#home-system-card").border_title = "SYSTEM"
        self.query_one(
            "#home-activity-card"
        ).border_title = f"ACTIVITY · LAST {days} DAYS"
        self.query_one("#home-types-card").border_title = f"BY TYPE · {days} DAYS"
        self.query_one("#home-recent-card").border_title = "RECENT"
        self.query_one("#home-recent-card").border_subtitle = "click for full history"
        self._known_actions = {
            action.id
            for group in group_names()
            for action in actions_for(group, Surface.DASHBOARD)
        }
        self.refresh_data()

    # --- header and launchpad ---------------------------------------------------

    @staticmethod
    def _brand(streak: int) -> Content:
        now = datetime.now()
        line = f"{greeting(now)}  ·  {now:%a %d %b  %H:%M}"
        return Content.assemble(
            ("◢◤ ", "bold $secondary"),
            ("MAX", "bold $primary"),
            (" // COMMAND CENTER\n", "bold"),
            (line, "$text-muted"),
            *(
                [("  ·  ", "$text-muted"), (f"{streak}-day streak", "bold $secondary")]
                if streak > 1
                else []
            ),
        )

    @staticmethod
    def _status() -> Content:
        from max_cli.common.ffmpeg_resolver import FFmpegResolver
        from max_cli.core.engines.ai_providers import provider_chain

        ffmpeg = bool(shutil.which("ffmpeg") or FFmpegResolver.get_cached_resolution())
        ai = bool(provider_chain())  # the main AI or its fallback has a key

        def light(on: bool, label: str) -> tuple[str, str]:
            return (f"● {label}   ", "$success" if on else "$text-muted")

        return Content.assemble(
            light(ffmpeg, "FFMPEG" if ffmpeg else "NO FFMPEG"),
            light(ai, "AI" if ai else "AI OFF"),
        )

    @staticmethod
    def _ask_hint() -> str:
        from max_cli.core.engines.ai_providers import provider_chain

        if provider_chain():
            return ASK_EXAMPLE
        return ASK_OFF.format(key=SECTION_KEYS["settings"])

    @staticmethod
    def _launch_label(section_id: str, name: str, purpose: str) -> Content:
        """The page's chip and name with its key, what it's for under them."""
        return Content.assemble(
            page_icon(section_id),
            (f" {name}", "bold"),
            (f"  {SECTION_KEYS[section_id]}\n", "bold $text-muted"),
            (" " * (ICON_WIDTH + 1) + purpose, "$text-muted"),
        )

    # --- refresh ------------------------------------------------------------------

    def refresh_data(self) -> None:
        # One repaint for all of this page's updates, not one per label.
        with self.app.batch_update():
            self._refresh_now()

    def _refresh_now(self) -> None:
        entries = ActivityLog().get_entries(limit=LOG_LIMIT)
        today = date.today()
        totals = home_stats.totals(entries, today)
        self.query_one("#home-brand", Static).update(self._brand(totals.streak))
        self._refresh_system()
        self._refresh_tiles(totals)
        self._refresh_charts(entries, today, totals)
        self.query_one(RecentList).set_rows(
            home_stats.recent_rows(entries, datetime.now())
        )
        self._refresh_again(entries)

    def _refresh_system(self) -> None:
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=None)
            cores = psutil.cpu_count() or 0
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage(Path.home().anchor)
        except (ImportError, OSError):
            return
        self.query_one("#system-cpu", SystemLine).show(cpu, f"{cores} cores")
        self.query_one("#system-mem", SystemLine).show(
            memory.percent,
            f"{memory.used / GIGABYTE:.1f} / {memory.total / GIGABYTE:.1f} GB",
            f"{memory.used / GIGABYTE:.1f} of {memory.total / GIGABYTE:.1f} GB used",
        )
        self.query_one("#system-disk", SystemLine).show(
            disk.percent,
            f"{format_size(disk.free)} free",
            f"{format_size(disk.free)} free of {format_size(disk.total)}",
        )

    def _refresh_tiles(self, totals: home_stats.Totals) -> None:
        from max_cli.core.engines.task_manager import get_task_manager

        self.query_one("#tile-week", Tile).show(
            str(totals.this_week), trend(totals.this_week, totals.last_week)
        )
        if totals.finished:
            rate = (totals.finished - totals.failed) * 100 // totals.finished
            self.query_one("#tile-actions", Tile).show(
                str(rate),
                f"{totals.finished - totals.failed} of {totals.finished} worked",
            )
        else:
            self.query_one("#tile-actions", Tile).show("0", "none yet")

        if totals.saved_bytes:
            size, unit = format_size(totals.saved_bytes).split(" ", 1)
            self.query_one("#tile-saved", Tile).show(
                size, f"{unit} by {totals.saving_actions} actions"
            )
        else:
            self.query_one("#tile-saved", Tile).show("0", "compress something")

        manager = get_task_manager()
        manager.try_refresh()  # busy store: show the counts read last time
        stats = manager.get_stats()
        running, waiting = int(stats.get("running", 0)), int(stats.get("pending", 0))
        note = f"{running} now · {waiting} next" if running or waiting else "idle"
        self.query_one("#tile-queue", Tile).show(str(running + waiting), note)

    def _refresh_charts(
        self, entries: list[ActivityEntry], today: date, totals: home_stats.Totals
    ) -> None:
        self.query_one(StackChart).set_data(home_stats.daily_stacks(entries, today))
        bars = [
            HBar(home_stats.look(kind).label, count, home_stats.look(kind).style)
            for kind, count in home_stats.type_counts(entries, today)
        ]
        self.query_one("#home-types", HBarChart).set_data(bars)
        note = Content.assemble(
            ("✓ ", "$success"),
            (f"{totals.finished - totals.failed} worked   ", "$text-muted"),
            ("✗ ", "$error" if totals.failed else "$text-muted"),
            (f"{totals.failed} failed", "$text-muted"),
        )
        types_note = self.query_one("#home-types-note", Static)
        types_note.update(note)
        types_note.tooltip = (
            "AI counts the requests you made; what the agent ran counts in its "
            "own kind."
        )

    def on_resize(self) -> None:
        self.set_class(self.size.width < NARROW_WIDTH, "-narrow")
        self._show_again()

    def _refresh_again(self, entries: list[ActivityEntry]) -> None:
        """The actions you run most, as chips that open their forms."""
        self._top = home_stats.top_actions(entries, self._known_actions)
        self._show_again()

    def _show_again(self) -> None:
        """As many of the top actions as fit on the row, whole."""
        room = self.size.width - AGAIN_LABEL_WIDTH - 8  # page and card edges
        top = []
        for action_id in self._top:
            room -= len(action_id) + CHIP_EXTRA
            if room < 0:
                break
            top.append(action_id)
        if top == self._again and (top or self.query(".again-empty")):
            return
        self._again = top
        row = self.query_one("#home-again", Horizontal)
        for chip in row.query(Launcher):
            chip.remove()
        if not top:
            row.mount(
                Static(
                    Content.styled(
                        "the actions you use most show up here", "$text-muted"
                    ),
                    classes="again-empty",
                )
            )
            return
        for empty in row.query(".again-empty"):
            empty.remove()
        row.mount_all(
            Launcher(
                Content.assemble(("▸ ", "$secondary"), action_id.replace(".", " ")),
                action=action_id,
                chip=True,
            )
            for action_id in top
        )

    # --- input --------------------------------------------------------------------

    @on(Input.Submitted, "#home-ask-input")
    def _on_ask(self, event: Input.Submitted) -> None:
        event.stop()
        text = event.value.strip()
        from max_cli.core.engines.ai_providers import provider_chain

        if not provider_chain():
            self.post_message(OpenPage("settings"))
            return
        if text:
            event.input.value = ""
            self.post_message(AskAI(text))

    @on(Click, "#home-recent-card")
    def _on_recent(self, event: Click) -> None:
        event.stop()
        self.post_message(OpenPage("activity", tab="history"))
