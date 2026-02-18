from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typer import Typer

from max_cli.interface import cli_tools


def register(app: "Typer") -> None:
    """Register utility tool commands."""
    app.add_typer(cli_tools.app, name="tools", help="System utilities (Clipboard, QR).")
