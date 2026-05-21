import typer

from max_cli.common.logger import console

app = typer.Typer(
    help="Launch the interactive TUI dashboard.",
    invoke_without_command=True,
)


@app.callback()
def dashboard(
    ctx: typer.Context,
) -> None:
    """Launch the interactive Max CLI dashboard."""
    if ctx.invoked_subcommand is not None:
        return

    try:
        from max_cli.interface.tui.app import MaxDashboardApp
    except ImportError:
        console.print(
            "[yellow]The TUI dashboard requires the 'textual' library.[/yellow]\n"
            "Install it with: [bold]pip install max-cli\\[tui][/bold]"
        )
        raise typer.Exit(1)

    max_app = MaxDashboardApp()
    max_app.run()
