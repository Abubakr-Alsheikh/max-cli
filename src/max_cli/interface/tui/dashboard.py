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
        # textual is a required dependency, so only a broken install gets here.
        console.print(
            "[yellow]The dashboard needs the 'textual' library, "
            "which is missing.[/yellow]\n"
            "Reinstall Max with: [bold]pip install --upgrade max-cli[/bold]"
        )
        raise typer.Exit(1) from None

    max_app = MaxDashboardApp()
    max_app.run()
