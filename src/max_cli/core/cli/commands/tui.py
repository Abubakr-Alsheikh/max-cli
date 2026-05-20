"""TUI dashboard command registration."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typer import Typer


def register(app: "Typer") -> None:
    from max_cli.interface.tui.dashboard import app as dashboard_app

    app.add_typer(
        dashboard_app, name="dashboard", help="Launch the interactive TUI dashboard."
    )
