"""The sidebar: number keys, back, help, remembered page, badges
(PLANS/active/dashboard-design-system.md)."""

import pytest
from textual.widgets import Button, Input

from max_cli.interface.tui.activity_log import ActivityLog
from max_cli.interface.tui.app import MaxDashboardApp
from max_cli.interface.tui.ui_prefs import load_prefs
from max_cli.interface.tui.widgets.dialogs import HelpScreen
from max_cli.interface.tui.widgets.download_panel import DownloadPanel
from max_cli.interface.tui.widgets.sidebar import SECTION_KEYS, Badge, Sidebar

from .waiting import wait_until

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
        app.navigate("audio")
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
        first.navigate("audio")
        await pilot.pause()

    assert load_prefs()["last_page"] == "audio"
    second = MaxDashboardApp()
    async with second.run_test(size=WIDE) as pilot:
        await pilot.pause()
        assert _shown(second) == "audio"


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
async def test_arrow_keys_move_when_the_pages_dont_fit():
    """The scroll area around the pages took up and down for itself."""
    app = MaxDashboardApp()
    async with app.run_test(size=(120, 20)) as pilot:
        app.query_one(Sidebar).focus_nav()
        await pilot.pause()
        await pilot.press(*["down"] * 10)
        await pilot.pause()

        assert app.focused.id == "nav-settings"


@pytest.mark.asyncio
async def test_clicking_a_page_opens_it():
    app = MaxDashboardApp()
    async with app.run_test(size=WIDE) as pilot:
        await pilot.click("#nav-audio")
        await pilot.pause()

        assert _shown(app) == "audio"


@pytest.mark.asyncio
async def test_the_sidebar_starts_open_and_the_button_folds_it():
    """Maintainer's choice (2026-10-02): names first, a button for icons."""
    app = MaxDashboardApp()
    async with app.run_test(size=WIDE) as pilot:
        sidebar = app.query_one(Sidebar)
        assert not sidebar.compact

        await pilot.click("#sidebar-toggle")
        await pilot.pause()
        assert sidebar.compact
        assert load_prefs()["sidebar_open"] is False

        await pilot.click("#sidebar-toggle")
        await pilot.pause()
        assert not sidebar.compact
        assert load_prefs()["sidebar_open"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "old_prefs", ['{"sidebar_compact": true}', '{"sidebar_collapsed": true}']
)
async def test_an_old_folded_choice_does_not_override_the_new_default(
    isolated_home, old_prefs
):
    """Both older keys were saved while icons were the default; only
    `sidebar_open` counts."""
    prefs = isolated_home / ".max_cli" / "dashboard_prefs.json"
    prefs.parent.mkdir(parents=True, exist_ok=True)
    prefs.write_text(old_prefs, encoding="utf-8")

    app = MaxDashboardApp()
    async with app.run_test(size=WIDE):
        assert not app.query_one(Sidebar).compact


@pytest.mark.asyncio
async def test_narrow_windows_disable_the_expand_button():
    app = MaxDashboardApp()
    async with app.run_test(size=NARROW) as pilot:
        await pilot.press("ctrl+b")
        await pilot.pause()

        assert app.query_one(Sidebar).compact
        assert app.query_one("#sidebar-toggle", Button).disabled


@pytest.mark.asyncio
async def test_running_downloads_show_as_a_badge():
    app = MaxDashboardApp()
    async with app.run_test(size=WIDE) as pilot:
        panel = app.query_one(DownloadPanel)
        sidebar = app.query_one(Sidebar)
        panel.post_message(DownloadPanel.RunningChanged(2))
        await wait_until(pilot, lambda: sidebar.badge("download") is not None)
        assert sidebar.badge("download") == Badge("running", 2)

        panel.post_message(DownloadPanel.RunningChanged(0))
        await wait_until(pilot, lambda: sidebar.badge("download") is None)
        assert sidebar.badge("download") is None


@pytest.mark.asyncio
async def test_new_failures_badge_activity_until_you_open_it():
    app = MaxDashboardApp()
    async with app.run_test(size=WIDE) as pilot:
        ActivityLog().add_entry("download", "grab", status="failed")
        app._refresh_badges()
        assert app.query_one(Sidebar).badge("activity") == Badge("failed", 1)

        app.navigate("activity")
        await pilot.pause()
        app._refresh_badges()
        # Seen: the badge goes back to counting the queue (empty here).
        assert app.query_one(Sidebar).badge("activity") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("old_page", ["queue", "history"])
async def test_a_saved_queue_or_history_page_opens_activity(old_page):
    from max_cli.interface.tui.ui_prefs import save_pref

    save_pref("last_page", old_page)
    app = MaxDashboardApp()
    async with app.run_test(size=WIDE) as pilot:
        await pilot.pause()
        assert _shown(app) == "activity"


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
    async with second.run_test(size=WIDE) as pilot:
        assert second.query_one(Sidebar).compact
        await pilot.press("ctrl+b")
        await pilot.pause()

    third = MaxDashboardApp()
    async with third.run_test(size=WIDE):
        assert not third.query_one(Sidebar).compact


@pytest.mark.asyncio
async def test_expanded_items_have_equal_left_and_right_margins():
    """The active item lost its right padding and its badge hit the edge."""
    from max_cli.interface.tui.widgets.sidebar import NavItem

    app = MaxDashboardApp()
    async with app.run_test(size=WIDE) as pilot:
        app.navigate("download")
        await pilot.pause()

        for item in app.query(NavItem):
            left = item.content_region.x - item.region.x
            right = item.region.right - item.content_region.right
            assert left == right == 2, item.section_id


@pytest.mark.asyncio
async def test_collapsed_icons_are_centred_in_a_narrow_strip():
    """The collapsed rules sat in NavItem's scoped CSS and never matched,
    so icons hugged the left of an 11-column strip."""
    from max_cli.interface.tui.widgets.sidebar import NavItem

    app = MaxDashboardApp()
    async with app.run_test(size=WIDE) as pilot:
        await pilot.press("ctrl+b")
        await pilot.pause()
        sidebar = app.query_one(Sidebar)
        assert sidebar.compact and sidebar.size.width <= 7

        for item in app.query(NavItem):
            if item.has_class("-active"):
                continue  # its accent border takes a column
            text = item.render()
            indent = len(text.plain) - len(text.plain.lstrip(" "))
            icon_width = text.cell_length - indent
            assert item.content_region == item.region, item.section_id
            assert indent == (item.content_size.width - icon_width) // 2
