from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typer import Typer

from max_cli.interface import cli_ai


def register(app: "Typer") -> None:
    """Register AI assistant commands."""
    app.add_typer(cli_ai.app, name="ai", help="Ask AI to run commands.")
    cli_ai.MAIN_APP_REF = app
