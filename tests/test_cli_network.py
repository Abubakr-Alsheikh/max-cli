from unittest.mock import patch, MagicMock
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