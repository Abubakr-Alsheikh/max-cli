"""Regression tests for the dashboard P0 bugs (tui-bugfix-and-ux-improvements.md)."""

import threading
from unittest.mock import patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Input


@pytest.mark.asyncio
async def test_config_search_filters_rows_and_clearing_restores_them():
    """Typing in the search box used to raise AttributeError (Label.renderable)."""
    from max_cli.interface.tui.widgets.config_panel import ConfigPanel

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield ConfigPanel()

    async with TestApp().run_test() as pilot:
        search = pilot.app.query_one("#config-search", Input)
        rows = list(pilot.app.query(".config-row"))
        assert rows

        search.value = "grab_quality"
        await pilot.pause()
        shown = [row.name for row in rows if row.display]
        assert shown == ["GRAB_QUALITY"]

        search.value = ""
        await pilot.pause()
        assert all(row.display for row in rows)


@pytest.mark.asyncio
async def test_files_filter_hides_rows_that_do_not_match(tmp_path):
    """The filter set Row.visible, which Textual ignores, so nothing changed."""
    from max_cli.interface.tui.widgets.files_panel import FilesPanel

    (tmp_path / "holiday.jpg").write_bytes(b"x")
    (tmp_path / "report.pdf").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")

    class TestApp(App):
        def compose(self) -> ComposeResult:
            panel = FilesPanel()
            panel._current_path = tmp_path
            yield panel

    async with TestApp().run_test() as pilot:
        table = pilot.app.query_one("#files-table", DataTable)
        assert table.row_count == 3

        pilot.app.query_one("#files-filter", Input).value = "report"
        await pilot.pause()
        assert table.row_count == 1
        assert "report.pdf" in str(table.get_row_at(0)[0])

        pilot.app.query_one("#files-filter", Input).value = ""
        await pilot.pause()
        assert table.row_count == 3


def test_config_sections_name_real_settings_fields():
    """The sections listed OPENAI_MODEL, YTDLP_FORMAT and others that don't exist."""
    from max_cli.config import Settings
    from max_cli.interface.tui.widgets.config_panel import CONFIG_SECTIONS

    listed = [name for names in CONFIG_SECTIONS.values() for name in names]
    assert set(listed) <= set(Settings.model_fields)


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


@pytest.mark.asyncio
async def test_chat_calls_the_ai_off_the_ui_thread():
    """Chat called the AI on the UI thread, so the screen froze until it replied."""
    from max_cli.interface.tui.widgets.chat_panel import ChatPanel

    ai_threads: list[threading.Thread] = []

    def fake_interpret(self, prompt, app_instance, explain=False):
        ai_threads.append(threading.current_thread())
        return {"thought": "Sure, here you go", "command": None}

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield ChatPanel()

    with (
        patch(
            "max_cli.core.engines.ai_engine.AIEngine.interpret_intent",
            fake_interpret,
        ),
        patch("max_cli.core.cli.registry.build_full_app", return_value=None),
    ):
        async with TestApp().run_test() as pilot:
            pilot.app.query_one("#chat-input", Input).value = "hello"
            pilot.app.query_one(ChatPanel)._on_send()
            await pilot.app.workers.wait_for_complete()
            await pilot.pause()

            messages = [str(m.content) for m in pilot.app.query(".chat-msg")]

    assert ai_threads
    assert ai_threads[0] is not threading.main_thread()
    assert any("Sure, here you go" in m for m in messages)
    assert not any("Thinking..." in m for m in messages)


DASHBOARD_SECTIONS = [
    "home",
    "download",
    "queue",
    "history",
    "files",
    "tools",
    "analytics",
    "config",
    "system",
    "chat",
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
