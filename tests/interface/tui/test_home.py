"""The Home page (command center) and its charts
(PLANS/active/dashboard-design-system.md, R3)."""

from datetime import date, datetime, timedelta

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button, Digits

from max_cli.common.activity_log import ActivityEntry, ActivityLog
from max_cli.interface.tui.app import MaxDashboardApp
from max_cli.interface.tui.theme import THEME_NAME
from max_cli.interface.tui.widgets.charts import (
    Bar,
    BarChart,
    HBar,
    HBarChart,
    Meter,
    Spark,
)
from max_cli.interface.tui.widgets.home_panel import (
    Tile,
    category_bars,
    daily_counts,
    greeting,
    load_colour,
)

TODAY = date(2026, 9, 29)
POLL_ATTEMPTS = 40
POLL_SECONDS = 0.05


def _entry(category: str, day: date, status: str = "success") -> ActivityEntry:
    entry = ActivityEntry(category=category, action=category, status=status)
    entry.timestamp = datetime.combine(day, datetime.min.time()).isoformat()
    return entry


class TestStats:
    def test_daily_counts_cover_fourteen_days_oldest_first(self):
        entries = [
            _entry("download", TODAY),
            _entry("download", TODAY),
            _entry("ai", TODAY - timedelta(days=3)),
            _entry("ai", TODAY - timedelta(days=30)),  # too old
        ]

        bars = daily_counts(entries, TODAY)

        assert len(bars) == 14
        assert bars[-1] == Bar("now", 2, highlight=True)
        assert bars[-4].value == 1 and not bars[-4].highlight
        assert sum(bar.value for bar in bars) == 3

    def test_category_bars_merge_aliases_and_sort(self):
        entries = [_entry("grab", TODAY), _entry("download", TODAY), _entry("ai", TODAY)]

        bars = category_bars(entries)

        assert [(bar.label, bar.value) for bar in bars] == [("Downloads", 2), ("AI", 1)]

    @pytest.mark.parametrize(
        ("hour", "words"),
        [(8, "Good morning"), (14, "Good afternoon"), (21, "Good evening")],
    )
    def test_greeting(self, hour, words):
        assert greeting(datetime(2026, 9, 29, hour)) == words

    @pytest.mark.parametrize(
        ("percent", "colour"), [(10, "$primary"), (70, "$warning"), (90, "$error")]
    )
    def test_load_colour(self, percent, colour):
        assert load_colour(percent) == colour


class ChartApp(App):
    def compose(self) -> ComposeResult:
        yield BarChart(id="bars")
        yield HBarChart(id="hbars")
        yield Spark(classes="spark")
        yield Meter(classes="meter")


@pytest.mark.asyncio
async def test_charts_render_and_skip_unchanged_data():
    app = ChartApp()
    async with app.run_test(size=(60, 30)) as pilot:
        bars = app.query_one(BarChart)
        assert "No activity yet" in bars.render().plain

        data = [Bar("01", 2), Bar("now", 4, highlight=True)]
        bars.set_data(data)
        await pilot.pause()
        text = bars.render().plain
        assert "peak 4" in text and "now" in text

        refreshed = []
        bars.refresh = lambda *args, **kwargs: refreshed.append(True)  # type: ignore[method-assign]  # spy
        bars.set_data(list(data))
        assert refreshed == []

        hbars = app.query_one(HBarChart)
        hbars.set_data([HBar("Downloads", 10), HBar("AI", 5)])
        await pilot.pause()
        assert hbars.render().plain.splitlines()[0].startswith("Downloads")


@pytest.mark.asyncio
async def test_spark_uses_a_fixed_scale():
    """Textual's Sparkline filled the height for a steady 30%; this doesn't."""
    app = ChartApp()
    async with app.run_test(size=(40, 10)) as pilot:
        spark = app.query_one(Spark)
        spark.set_data([30.0] * 40)
        await pilot.pause()
        top, bottom = spark.render().plain.splitlines()

        assert top.strip() == ""  # 30% of two rows stays in the bottom row
        assert bottom.strip()


@pytest.mark.asyncio
async def test_home_shows_activity_and_counts(isolated_home):
    log = ActivityLog()
    for status in ("success", "success", "failed"):
        log.add_entry("download", "grab", status=status, details={"title": "Song [red]"})

    app = MaxDashboardApp()
    async with app.run_test(size=(140, 50)) as pilot:
        await pilot.pause()
        actions = app.query_one("#tile-actions", Tile)

        assert actions.query_one(Digits).value == "3"
        assert "66% succeeded" in str(actions.query_one(".tile-note").render())
        recent = str(app.query_one("#home-recent").render())
        assert "Song [red]" in recent  # plain text, not markup


@pytest.mark.asyncio
async def test_quick_launch_opens_pages():
    app = MaxDashboardApp()
    async with app.run_test(size=(140, 50)) as pilot:
        app.query_one("#launch-audio", Button).press()
        # Two hops: Button.Pressed -> HomePanel.OpenPage -> the app navigates.
        # Wait for the result instead of guessing a pause count.
        for _ in range(POLL_ATTEMPTS):
            await pilot.pause(POLL_SECONDS)
            if app.query_one("#audio-panel").display:
                break

        assert app.query_one("#audio-panel").display


@pytest.mark.asyncio
async def test_the_dashboard_uses_the_max_theme_and_remembers_a_switch():
    from max_cli.interface.tui.ui_prefs import load_prefs

    app = MaxDashboardApp()
    async with app.run_test(size=(100, 30)) as pilot:
        assert app.theme == THEME_NAME
        app.theme = "nord"
        await pilot.pause()

    assert load_prefs()["theme"] == "nord"
    second = MaxDashboardApp()
    async with second.run_test(size=(100, 30)):
        assert second.theme == "nord"
