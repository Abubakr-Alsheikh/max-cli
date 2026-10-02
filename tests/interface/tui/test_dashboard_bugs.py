"""Regression tests for the dashboard P0 bugs (tui-bugfix-and-ux-improvements.md)."""


import pytest


def test_grab_activity_counts_as_download():
    """Downloads log as "grab", but the Home card and History filter read "download"."""
    from max_cli.interface.tui.activity_log import ActivityLog

    log = ActivityLog()
    log.add_entry(category="grab", action="download", status="success")

    assert log.get_stats()["download"] == 1
    assert len(log.get_entries(category_filter="download")) == 1


def test_old_grab_entries_on_disk_count_as_download():
    import json

    from max_cli.interface.tui.activity_log import ActivityLog

    ActivityLog.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ActivityLog.LOG_FILE.write_text(
        json.dumps([{"category": "grab", "action": "download", "status": "success"}]),
        encoding="utf-8",
    )

    assert ActivityLog().get_stats()["download"] == 1


DASHBOARD_SECTIONS = [
    "home",
    "download",
    "video",
    "images",
    "pdf",
    "activity",
    "files",
    "audio",
    "settings",
    "ai",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("section", DASHBOARD_SECTIONS)
async def test_every_page_scrolls_in_a_small_terminal(section):
    """Five pages had no scroll container, so a short terminal cut them off."""
    from max_cli.interface.tui.app import MaxDashboardApp

    app = MaxDashboardApp()
    async with app.run_test(size=(80, 16)) as pilot:
        app._show_panel(section)
        await pilot.pause()
        panel = app.query_one(f"#{section}-panel")

        assert panel.virtual_size.height > panel.container_size.height
        assert panel.allow_vertical_scroll


@pytest.mark.asyncio
async def test_refresh_timer_survives_shutdown():
    """The 2-second refresh timer can fire while the app tears its panels down.

    It used to raise NoMatches for #queue-panel; a slow test run hit it.
    """
    from max_cli.interface.tui.app import MaxDashboardApp

    app = MaxDashboardApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await app.query_one("#content").remove_children()

        app._refresh_active_panel()
        app.action_refresh()
