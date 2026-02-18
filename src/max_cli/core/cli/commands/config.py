from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typer import Typer

from max_cli.interface import cli_config


def register(app: "Typer") -> None:
    """Register configuration commands."""
    app.add_typer(cli_config.app, name="config", help="Manage API keys and settings.")
