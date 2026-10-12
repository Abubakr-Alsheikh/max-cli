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

    from max_cli.interface.tui.app import UPDATE_RESULT

    max_app = MaxDashboardApp()
    if max_app.run() == UPDATE_RESULT:
        # The dashboard closed for the update, so nothing holds Max's files
        # but this process; on Windows the update waits for it to end.
        from max_cli.interface.cli_update import update_max

        update_max(assume_yes=True)
