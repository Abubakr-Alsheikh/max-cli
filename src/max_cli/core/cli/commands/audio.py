from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typer import Typer

from max_cli.interface import cli_audio


def register(app: "Typer") -> None:
    """Register audio metadata commands."""
    app.add_typer(
        cli_audio.app, name="audio", help="Read, write, and manage audio metadata."
    )
    app.add_typer(cli_audio.app, name="a", hidden=True)
