"""Tests for individual TUI widgets."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from textual.app import App, ComposeResult


class TestSystemPanel:
    def test_format_bytes(self):
        from max_cli.interface.tui.widgets.system_panel import SystemPanel

        assert SystemPanel._format_bytes(512) == "512.0 B"
        assert SystemPanel._format_bytes(1536) == "1.5 KB"
        assert SystemPanel._format_bytes(1048576) == "1.0 MB"
        assert SystemPanel._format_bytes(1073741824) == "1.0 GB"

    @pytest.mark.asyncio
    async def test_disk_usage_renders(self):
        from textual.widgets import Static

        from max_cli.interface.tui.widgets.system_panel import SystemPanel

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield SystemPanel()

        with (
            patch(
                "max_cli.interface.tui.widgets.system_panel.DaemonManager"
            ) as mock_dm,
            patch.object(Path, "exists", return_value=True),
            patch("shutil.disk_usage") as mock_disk,
        ):
            mock_daemon = MagicMock()
            mock_daemon.get_stats.return_value = {
                "total": 0,
                "running": 0,
                "pending": 0,
            }
            mock_daemon.get_history.return_value = []
            mock_dm.return_value = mock_daemon

            mock_usage = MagicMock()
            mock_usage.used = 1073741824
            mock_usage.total = 107374182400
            mock_usage.free = 106300440576
            mock_disk.return_value = mock_usage

            async with TestApp().run_test() as pilot:
                disk_widget = pilot.app.query_one("#system-disk", Static)
                assert disk_widget.content != ""


class TestConfigPanel:
    @pytest.mark.asyncio
    async def test_config_fields_render(self):
        from max_cli.interface.tui.widgets.config_panel import ConfigPanel

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ConfigPanel()

        with patch(
            "max_cli.interface.tui.widgets.config_panel.Settings"
        ) as mock_settings:
            mock_settings_instance = MagicMock()
            mock_settings_instance.OPENAI_API_KEY = None
            mock_settings_instance.OPENAI_BASE_URL = None
            mock_settings_instance.GRAB_DEFAULT_PATH = Path.home() / "downloads"
            mock_settings.model_fields = {
                "APP_NAME": None,
                "DEFAULT_QUALITY": None,
                "MAX_WORKERS": None,
            }
            mock_settings.return_value = mock_settings_instance

            mock_settings_instance.APP_NAME = "Max CLI"
            mock_settings_instance.DEFAULT_QUALITY = 85
            mock_settings_instance.MAX_WORKERS = 4

            async with TestApp().run_test() as pilot:
                container = pilot.app.query_one("#config-fields")
                assert container is not None

    @pytest.mark.asyncio
    async def test_config_save_writes_file(self, tmp_path):
        from max_cli.interface.tui.widgets.config_panel import ConfigPanel

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ConfigPanel()

        with (
            patch(
                "max_cli.interface.tui.widgets.config_panel.Settings"
            ) as mock_settings,
            patch.object(Path, "home", return_value=tmp_path),
        ):
            mock_settings_instance = MagicMock()
            mock_settings_instance.APP_NAME = "Max CLI"
            mock_settings_instance.DEFAULT_QUALITY = 85
            mock_settings_instance.MAX_WORKERS = 4
            mock_settings.model_fields = {
                "APP_NAME": None,
                "DEFAULT_QUALITY": None,
                "MAX_WORKERS": None,
            }
            mock_settings.return_value = mock_settings_instance

            async with TestApp().run_test() as pilot:
                btn = pilot.app.query_one("#btn-save-config")
                btn.press()
                await pilot.pause()

                env_file = tmp_path / ".max_config.env"
                assert env_file.exists()
