from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner
from max_cli.interface.cli_network import app as network_app

# Rich renders --help with ANSI codes and wraps to terminal width, which splits
# long option names. Plain, wide output keeps substring assertions stable.
runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})


class TestCLINetwork:
    """Tests for CLI network (grab) commands."""

    def test_download_help_shows_player_client(self):
        """Test --player-client flag is exposed in help."""
        result = runner.invoke(network_app, ["do", "--help"])
        assert result.exit_code == 0
        assert "--player-client" in result.stdout

    @pytest.mark.parametrize("given", ["tv", "TV", "Android"])
    @patch("max_cli.interface.cli_network._add_to_queue_or_download")
    def test_player_client_reaches_downloader_as_lowercase_str(
        self, mock_download, given
    ):
        result = runner.invoke(
            network_app,
            ["do", "https://example.com/video", "--player-client", given],
        )

        assert result.exit_code == 0, result.output
        passed = mock_download.call_args.args[-1]
        assert passed == given.lower()
        assert type(passed) is str

    @patch("max_cli.interface.cli_network._add_to_queue_or_download")
    def test_player_client_defaults_to_none(self, mock_download):
        result = runner.invoke(network_app, ["do", "https://example.com/video"])

        assert result.exit_code == 0, result.output
        assert mock_download.call_args.args[-1] is None

    @patch("max_cli.interface.cli_network._add_to_queue_or_download")
    def test_invalid_player_client_is_rejected(self, mock_download):
        result = runner.invoke(
            network_app,
            ["do", "https://example.com/video", "--player-client", "bogus"],
        )

        assert result.exit_code == 2
        mock_download.assert_not_called()

    def test_pot_setup_help(self):
        """Test pot-setup command help."""
        result = runner.invoke(network_app, ["pot-setup", "--help"])
        assert result.exit_code == 0
        assert "PO token provider" in result.stdout

    @patch("max_cli.interface.cli_network.shutil.which", return_value="deno")
    @patch("max_cli.interface.cli_network._get_engine")
    def test_pot_setup_already_installed(self, mock_get_engine, mock_which):
        """Test pot-setup exits cleanly when provider already present."""
        mock_engine = MagicMock()
        mock_engine.has_js = True
        mock_engine.pot_provider_available.return_value = True
        mock_get_engine.return_value = mock_engine

        result = runner.invoke(network_app, ["pot-setup"])
        assert result.exit_code == 0
        assert "already installed" in result.stdout

    @patch("max_cli.interface.cli_network.shutil.which")
    def test_pot_setup_requires_deno(self, mock_which):
        """Test pot-setup errors without Deno."""
        mock_which.return_value = None

        result = runner.invoke(network_app, ["pot-setup"])
        assert result.exit_code == 1
        assert "Deno not found" in result.stdout

class TestGrabQueueUsesTaskStore:
    """`max grab queue/history/clear` read the shared task store (D1)."""

    def test_queue_lists_download_tasks_only(self):
        from max_cli.core.engines.network_engine import make_download_task
        from max_cli.core.engines.task_manager import get_task_manager
        from max_cli.core.engines.task_queue import TaskItem, TaskType

        manager = get_task_manager()
        manager.add(make_download_task("https://youtu.be/queued"))
        manager.add(TaskItem(type=TaskType.CUSTOM, title="not a download"))

        result = runner.invoke(network_app, ["queue"])

        assert result.exit_code == 0, result.output
        assert "https://youtu.be/queued" in result.stdout
        assert "not a download" not in result.stdout

    def test_history_shows_recorded_downloads(self):
        from max_cli.core.engines.download_history import DownloadHistory

        DownloadHistory().record_download(url="https://youtu.be/x", title="Clip X")

        result = runner.invoke(network_app, ["history"])

        assert result.exit_code == 0, result.output
        assert "Clip X" in result.stdout

    def test_clear_all_removes_queued_downloads(self):
        from max_cli.core.engines.network_engine import make_download_task
        from max_cli.core.engines.task_manager import get_task_manager

        manager = get_task_manager()
        manager.add(make_download_task("https://youtu.be/queued"))

        result = runner.invoke(network_app, ["clear", "--all", "--force"])

        assert result.exit_code == 0, result.output
        assert manager.get_all() == []
