from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typer import Typer

from max_cli.interface import cli_queue


def register(app: "Typer") -> None:
    app.add_typer(cli_queue.app, name="queue", help="Manage background task queue")
