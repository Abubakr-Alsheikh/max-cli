"""Tests for the TUI dashboard application."""

import sys
from unittest.mock import MagicMock, patch

import pytest
from textual.widgets import DataTable

from max_cli.core.engines.task_queue import TaskItem, TaskStatus, TaskType


@pytest.fixture
def mock_daemon():
    with (
        patch("max_cli.interface.tui.widgets.queue_panel.DaemonManager") as mock_q,
        patch("max_cli.interface.tui.widgets.history_panel.DaemonManager") as mock_h,
        patch("max_cli.interface.tui.widgets.system_panel.DaemonManager") as mock_s,
    ):
        daemon = MagicMock()
        daemon.get_all.return_value = []
        daemon.get_stats.return_value = {
            "total": 0,
            "pending": 0,
            "running": 0,
            "failed": 0,
            "paused": 0,
            "by_type": {},
        }
        daemon.get_history.return_value = []
        daemon.get.return_value = None
        mock_q.return_value = daemon
        mock_h.return_value = daemon
        mock_s.return_value = daemon
        yield daemon


class TestMaxDashboardApp:
    @pytest.mark.asyncio
    async def test_app_starts(self, mock_daemon):
        from max_cli.interface.tui.app import MaxDashboardApp

        async with MaxDashboardApp().run_test() as pilot:
            assert pilot.app.query_one("TabbedContent") is not None

    @pytest.mark.asyncio
    async def test_queue_panel_renders_empty(self, mock_daemon):
        from max_cli.interface.tui.app import MaxDashboardApp

        async with MaxDashboardApp().run_test() as pilot:
            table = pilot.app.query_one("#queue-table", DataTable)
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_queue_panel_shows_tasks(self, mock_daemon):
        from max_cli.interface.tui.app import MaxDashboardApp

        mock_task = TaskItem(
            id="abc123",
            type=TaskType.DOWNLOAD,
            status=TaskStatus.RUNNING,
            title="Test Download",
            progress=45.0,
        )
        mock_daemon.get_all.return_value = [mock_task]

        async with MaxDashboardApp().run_test() as pilot:
            panel = pilot.app.query_one("#queue-panel")
            panel.refresh_data()
            await pilot.pause()

            table = pilot.app.query_one("#queue-table", DataTable)
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_cancel_button_calls_daemon(self, mock_daemon):
        from max_cli.interface.tui.app import MaxDashboardApp

        mock_task = TaskItem(
            id="abc123",
            type=TaskType.DOWNLOAD,
            status=TaskStatus.PENDING,
            title="Test",
        )
        mock_daemon.get_all.return_value = [mock_task]

        async with MaxDashboardApp().run_test() as pilot:
            panel = pilot.app.query_one("#queue-panel")
            panel.refresh_data()
            await pilot.pause()

            table = pilot.app.query_one("#queue-table", DataTable)
            table.cursor_coordinate = (0, 0)

            btn = pilot.app.query_one("#btn-cancel")
            btn.press()
            await pilot.pause()

            mock_daemon.cancel.assert_called_once_with("abc123")

    @pytest.mark.asyncio
    async def test_history_filter(self, mock_daemon):
        from max_cli.interface.tui.app import MaxDashboardApp

        tasks = [
            TaskItem(
                id="t1",
                type=TaskType.DOWNLOAD,
                status=TaskStatus.COMPLETED,
                title="Video 1",
            ),
            TaskItem(
                id="t2",
                type=TaskType.VIDEO_COMPRESS,
                status=TaskStatus.COMPLETED,
                title="Compressed",
            ),
        ]
        mock_daemon.get_history.return_value = tasks

        async with MaxDashboardApp().run_test() as pilot:
            tabs = pilot.app.query_one("TabbedContent")
            tabs.active = "history"
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
    async def test_auto_refresh_timer(self, mock_daemon):
        from max_cli.interface.tui.app import MaxDashboardApp

        async with MaxDashboardApp().run_test() as pilot:
            await pilot.pause()
            pilot.app._refresh_active_panel()
            assert True


class TestDashboardCommand:
    def test_dashboard_missing_textual(self):
        from typer.testing import CliRunner

        for key in list(sys.modules.keys()):
            if "max_cli.interface.tui" in key:
                del sys.modules[key]

        with patch.dict(
            "sys.modules",
            {"textual": None, "textual.app": None, "textual.widgets": None},
        ):
            from max_cli.interface.tui.dashboard import app

            runner = CliRunner()
            result = runner.invoke(app, [])
            assert result.exit_code == 1
            assert "pip install max-cli[tui]" in result.output
