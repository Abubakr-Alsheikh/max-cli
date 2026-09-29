"""The sidebar: number keys, back, help, remembered page, badges
(PLANS/active/dashboard-design-system.md)."""

import pytest
from textual.widgets import Input, OptionList

from max_cli.interface.tui.activity_log import ActivityLog
from max_cli.interface.tui.app import MaxDashboardApp
from max_cli.interface.tui.ui_prefs import load_prefs
from max_cli.interface.tui.widgets.dialogs import HelpScreen
from max_cli.interface.tui.widgets.download_panel import DownloadPanel
from max_cli.interface.tui.widgets.sidebar import SECTION_KEYS, Badge, Sidebar

WIDE = (120, 40)
NARROW = (90, 30)


def _shown(app: MaxDashboardApp) -> str:
    [panel] = [panel for panel in app.query("#content > *") if panel.display]
    return str(panel.id).removesuffix("-panel")


@pytest.mark.asyncio
async def test_number_keys_jump_to_pages():
    app = MaxDashboardApp()
    async with app.run_test(size=WIDE) as pilot:
        await pilot.press(SECTION_KEYS["files"])
        await pilot.pause()

        assert _shown(app) == "files"
        assert app.query_one(Sidebar).active == "files"


@pytest.mark.asyncio
async def test_digits_typed_into_a_field_stay_in_the_field():
    app = MaxDashboardApp()
    async with app.run_test(size=WIDE) as pilot:
        app.navigate("download")
        await pilot.pause()
        link = app.query_one("#dl-url", Input)
        link.focus()
        await pilot.press(SECTION_KEYS["files"])
        await pilot.pause()

        assert link.value == SECTION_KEYS["files"]
        assert _shown(app) == "download"


@pytest.mark.asyncio
async def test_alt_left_goes_back():
    app = MaxDashboardApp()
    async with app.run_test(size=WIDE) as pilot:
        app.navigate("download")
        app.navigate("tools")
        await pilot.press("alt+left")
        await pilot.pause()
        assert _shown(app) == "download"

        await pilot.press("alt+left")
        await pilot.pause()
        assert _shown(app) == "home"


@pytest.mark.asyncio
async def test_the_dashboard_reopens_on_the_last_page():
    first = MaxDashboardApp()
    async with first.run_test(size=WIDE) as pilot:
        first.navigate("queue")
        await pilot.pause()

    assert load_prefs()["last_page"] == "queue"
    second = MaxDashboardApp()
    async with second.run_test(size=WIDE) as pilot:
        await pilot.pause()
        assert _shown(second) == "queue"


@pytest.mark.asyncio
async def test_question_mark_opens_help_and_escape_closes_it():
    app = MaxDashboardApp()
    async with app.run_test(size=WIDE) as pilot:
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_arrow_keys_and_enter_open_a_page():
    app = MaxDashboardApp()
    async with app.run_test(size=WIDE) as pilot:
        app.query_one(Sidebar).focus_nav()
        await pilot.press("down", "enter")
        await pilot.pause()

        assert _shown(app) == "download"


@pytest.mark.asyncio
async def test_group_headings_cannot_be_opened():
    app = MaxDashboardApp()
    async with app.run_test(size=WIDE):
        nav = app.query_one("#sidebar-nav", OptionList)
        headings = [
            nav.get_option_at_index(index)
            for index in range(nav.option_count)
            if (nav.get_option_at_index(index).id or "").startswith(("group-", "gap-"))
        ]

        assert headings and all(option.disabled for option in headings)


@pytest.mark.asyncio
async def test_running_downloads_show_as_a_badge():
    app = MaxDashboardApp()
    async with app.run_test(size=WIDE) as pilot:
        panel = app.query_one(DownloadPanel)
        panel.post_message(DownloadPanel.RunningChanged(2))
        await pilot.pause()
        assert app.query_one(Sidebar).badge("download") == Badge("running", 2)

        panel.post_message(DownloadPanel.RunningChanged(0))
        await pilot.pause()
        assert app.query_one(Sidebar).badge("download") is None


@pytest.mark.asyncio
async def test_new_failures_badge_history_until_you_open_it():
    app = MaxDashboardApp()
    async with app.run_test(size=WIDE) as pilot:
        ActivityLog().add_entry("download", "grab", status="failed")
        app._refresh_badges()
        assert app.query_one(Sidebar).badge("history") == Badge("failed", 1)

        app.navigate("history")
        await pilot.pause()
        app._refresh_badges()
        assert app.query_one(Sidebar).badge("history") is None


@pytest.mark.asyncio
async def test_narrow_windows_get_the_icon_sidebar():
    app = MaxDashboardApp()
    async with app.run_test(size=NARROW):
        assert app.query_one(Sidebar).compact


@pytest.mark.asyncio
async def test_ctrl_b_choice_is_remembered():
    first = MaxDashboardApp()
    async with first.run_test(size=WIDE) as pilot:
        await pilot.press("ctrl+b")
        await pilot.pause()
        assert first.query_one(Sidebar).compact

    second = MaxDashboardApp()
    async with second.run_test(size=WIDE):
        assert second.query_one(Sidebar).compact
