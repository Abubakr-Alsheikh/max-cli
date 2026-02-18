from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typer import Typer

from max_cli.interface import cli_network


def register(app: "Typer") -> None:
    """Register network and download commands."""
    app.add_typer(
        cli_network.app, name="net", help="Network tools (Download, Speedtest)."
    )
    app.add_typer(
        cli_network.app, name="grab", help="Download media from various platforms."
    )
