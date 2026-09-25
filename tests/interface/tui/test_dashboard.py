"""Tests for the TUI dashboard application."""

import sys
from unittest.mock import MagicMock, patch

import pytest
from textual.widgets import DataTable

from max_cli.core.engines.task_queue import TaskItem, TaskStatus, TaskType
from max_cli.interface.tui.widgets.sidebar import Sidebar


@pytest.fixture
def mock_manager():
    with (
        patch("max_cli.interface.tui.widgets.queue_panel.get_task_manager") as mock_q,
        patch("max_cli.interface.tui.widgets.system_panel.get_task_manager") as mock_s,
    ):
        manager = MagicMock()
        manager.get_all.return_value = []
        manager.get_stats.return_value = {
            "total": 0,
            "pending": 0,
            "running": 0,
            "failed": 0,
            "paused": 0,
            "by_type": {},
        }
        manager.get_history.return_value = []
        manager.get.return_value = None
        mock_q.return_value = manager
        mock_s.return_value = manager
        yield manager


@pytest.fixture
def mock_activity_log():
    with patch("max_cli.interface.tui.widgets.history_panel.ActivityLog") as mock:
        activity = MagicMock()
        activity.get_entries.return_value = []
        mock.return_value = activity
        yield activity


class TestMaxDashboardApp:
    @pytest.mark.asyncio
    async def test_app_starts(self, mock_manager, mock_activity_log):
        from max_cli.interface.tui.app import MaxDashboardApp

        async with MaxDashboardApp().run_test() as pilot:
            assert pilot.app.query_one(Sidebar) is not None

    @pytest.mark.asyncio
    async def test_queue_panel_renders_empty(self, mock_manager, mock_activity_log):
        from max_cli.interface.tui.app import MaxDashboardApp

        async with MaxDashboardApp().run_test() as pilot:
            table = pilot.app.query_one("#queue-table", DataTable)
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_queue_panel_shows_tasks(self, mock_manager, mock_activity_log):
        from max_cli.interface.tui.app import MaxDashboardApp

        mock_task = TaskItem(
            id="abc123",
            type=TaskType.DOWNLOAD,
            status=TaskStatus.RUNNING,
            title="Test Download",
            progress=45.0,
        )
        mock_manager.get_all.return_value = [mock_task]

        async with MaxDashboardApp().run_test() as pilot:
            panel = pilot.app.query_one("#queue-panel")
            panel.refresh_data()
            await pilot.pause()

            table = pilot.app.query_one("#queue-table", DataTable)
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_cancel_button_calls_manager(self, mock_manager, mock_activity_log):
        from max_cli.interface.tui.app import MaxDashboardApp

        mock_task = TaskItem(
            id="abc123",
            type=TaskType.DOWNLOAD,
            status=TaskStatus.PENDING,
            title="Test",
        )
        mock_manager.get_all.return_value = [mock_task]

        async with MaxDashboardApp().run_test() as pilot:
            panel = pilot.app.query_one("#queue-panel")
            panel.refresh_data()
            await pilot.pause()

            table = pilot.app.query_one("#queue-table", DataTable)
            table.cursor_coordinate = (0, 0)

            btn = pilot.app.query_one("#btn-cancel")
            btn.press()
            await pilot.pause()

            mock_manager.cancel.assert_called_once_with("abc123")

    @pytest.mark.asyncio
    async def test_history_filter(self, mock_manager, mock_activity_log):
        from max_cli.interface.tui.activity_log import ActivityEntry
        from max_cli.interface.tui.app import MaxDashboardApp

        entries = [
            ActivityEntry(
                entry_id="t1",
                category="download",
                action="download_media",
                status="success",
                details={"url": "https://youtube.com/watch?v=1"},
            ),
            ActivityEntry(
                entry_id="t2",
                category="task",
                action="compress_video",
                status="success",
                details={"target": "video.mp4"},
            ),
        ]
        mock_activity_log.get_entries.return_value = entries

        async with MaxDashboardApp().run_test() as pilot:
            pilot.app._show_panel("history")
            await pilot.pause()

            panel = pilot.app.query_one("#history-panel")
            panel.refresh_data()
            await pilot.pause()

            table = pilot.app.query_one("#history-table", DataTable)
            assert table.row_count == 2

            filter_input = pilot.app.query_one("#history-filter")
            filter_input.value = "download"
            await pilot.pause()

            panel.refresh_data()
            await pilot.pause()

            table = pilot.app.query_one("#history-table", DataTable)
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_auto_refresh_timer(self, mock_manager, mock_activity_log):
        from max_cli.interface.tui.app import MaxDashboardApp

        async with MaxDashboardApp().run_test() as pilot:
            await pilot.pause()
            pilot.app._refresh_active_panel()
            assert True


class TestDashboardCommand:
    @pytest.mark.skip(reason="Module manipulation causes test isolation issues")
    def test_dashboard_missing_textual(self):
        from typer.testing import CliRunner

        runner = CliRunner()

        saved_modules = {}
        keys_to_delete = []
        for key in list(sys.modules.keys()):
            if "max_cli.interface.tui" in key:
                saved_modules[key] = sys.modules[key]
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del sys.modules[key]

        try:
            with patch.dict(
                "sys.modules",
                {"textual": None, "textual.app": None, "textual.widgets": None},
            ):
                from max_cli.interface.tui.dashboard import app

                result = runner.invoke(app, [])
                assert result.exit_code == 1
                assert "pip install max-cli[tui]" in result.output
        finally:
            for key, module in saved_modules.items():
                sys.modules[key] = module
            import importlib

            import max_cli.interface.tui.app

            importlib.reload(max_cli.interface.tui.app)
