"""The Home page (command center) and its charts
(PLANS/active/dashboard-design-system.md, R3)."""

from datetime import date, datetime

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Digits, Input

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
    Launcher,
    Tile,
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
        log.add_entry(
            "download", "grab", status=status, details={"title": "Song [red]"}
        )

    app = MaxDashboardApp()
    async with app.run_test(size=(140, 50)) as pilot:
        await pilot.pause()
        actions = app.query_one("#tile-actions", Tile)

        assert actions.query_one(Digits).value == "66"  # % that worked
        assert "2 of 3 worked" in str(actions.query_one(".tile-note").render())
        recent = str(app.query_one("#home-recent").render())
        assert "Song [red]" in recent  # plain text, not markup


@pytest.mark.asyncio
async def test_quick_launch_opens_pages():
    app = MaxDashboardApp()
    async with app.run_test(size=(140, 50)) as pilot:
        await pilot.click("#launch-audio")
        # Two hops: the tile posts OpenPage -> the app navigates.
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


@pytest.mark.asyncio
async def test_the_ask_bar_sends_the_request_to_the_ai_page(monkeypatch):
    from max_cli.config import settings
    from max_cli.interface.tui.widgets.ai_panel import AIPanel

    monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(settings, "AI_FALLBACK_PROVIDER", "")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    sent = []
    monkeypatch.setattr(AIPanel, "send", lambda panel, text: sent.append(text))
    app = MaxDashboardApp()
    async with app.run_test(size=(140, 50)) as pilot:
        box = app.query_one("#home-ask-input", Input)
        box.value = "shrink the videos here"
        await box.action_submit()
        for _ in range(POLL_ATTEMPTS):
            await pilot.pause(POLL_SECONDS)
            if sent:
                break
        on_ai_page = app.query_one("#ai-panel").display

    assert sent == ["shrink the videos here"]
    assert on_ai_page


@pytest.mark.asyncio
async def test_pick_up_again_opens_the_actions_you_use_most(isolated_home):
    log = ActivityLog()
    for _ in range(3):
        log.add_entry("video", "compress", status="success", details={})
    log.add_entry("pdf", "merge", status="success", details={})
    app = MaxDashboardApp()
    opened = []
    async with app.run_test(size=(140, 50)) as pilot:
        app.open_action = opened.append  # type: ignore[method-assign]  # spy
        await pilot.pause()
        chips = list(app.query("#home-again Launcher").results(Launcher))
        labels = [chip.label.plain for chip in chips]
        chips[0].action_launch()

    assert labels == ["▸ video compress", "▸ pdf merge"]
    assert opened == ["video.compress"]


@pytest.mark.asyncio
async def test_stack_chart_colours_each_kind():
    from max_cli.interface.tui.widgets.charts import Stack, StackChart

    class StackApp(App):
        def compose(self) -> ComposeResult:
            yield StackChart(id="stacks")

    app = StackApp()
    async with app.run_test(size=(40, 12)) as pilot:
        chart = app.query_one(StackChart)
        assert "No activity yet" in chart.render().plain
        chart.set_data(
            [
                Stack("01", ((3, "$primary"), (1, "$secondary"))),
                Stack("now", ((2, "$secondary"),), highlight=True),
            ]
        )
        await pilot.pause()
        rendered = chart.render()

    assert "peak 4" in rendered.plain and "now" in rendered.plain
    styles = {str(span.style) for span in rendered.spans}
    assert "$primary" in styles and "$secondary" in styles


@pytest.mark.parametrize(
    ("style", "glyph"), [("emoji", "\U0001f3e0"), ("nerd", "\U000f02dc")]
)
def test_page_icons_follow_the_setting(monkeypatch, style, glyph):
    from max_cli.config import settings
    from max_cli.interface.tui.widgets.sidebar import page_icon

    monkeypatch.setattr(settings, "DASHBOARD_ICONS", style)

    icon = page_icon("home")

    assert icon.plain.startswith(glyph)
    assert icon.cell_length == 2  # labels line up either way
