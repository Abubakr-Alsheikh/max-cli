"""`max update`: check PyPI for a newer Max and install it the way Max was installed.

The dashboard's Update button closes the dashboard and calls `update_max`.
"""

import typer
from rich.markup import escape
from rich.prompt import Confirm

from max_cli.common.logger import console, log_error, log_success

app = typer.Typer(
    help="Update Max to the newest version.",
    invoke_without_command=True,
)


def update_max(assume_yes: bool = False) -> None:
    """Install the newest Max: in place, or (Windows) from a window that
    waits for this Max to close."""
    from max_cli.core.engines import updates

    method = updates.install_method()
    command = updates.update_command(method)
    if command is None:
        console.print(updates.SOURCE_UPDATE_HINT)
        return
    console.print(
        f"[dim]Max is {updates.INSTALL_LABELS[method]}, so the update runs: "
        f"{escape(' '.join(command))}[/dim]"
    )
    if not assume_yes and not Confirm.ask("Update now?", default=True):
        return
    if updates.needs_hand_off():
        updates.hand_off(command)
        log_success(
            "An update window opened. It updates Max as soon as this window's "
            "Max closes, which is now."
        )
        return
    if updates.run_update(command) == 0:
        log_success("Max is up to date. Run max again to use the new version.")
    else:
        log_error(f"The update failed. Try it yourself: {' '.join(command)}")


@app.callback()
def update(
    ctx: typer.Context,
    check_only: bool = typer.Option(
        False, "--check", help="Only say whether a newer Max is out."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Update without asking."),
) -> None:
    """Check for a newer Max and install it."""
    if ctx.invoked_subcommand is not None:
        return
    from max_cli.core.engines import updates

    with console.status("[dim]Asking PyPI for the newest Max...[/dim]"):
        status = updates.check(force=True)
    if status.latest is None:
        log_error(status.error or "PyPI didn't say which Max is newest.")
        raise typer.Exit(1)
    if not status.available:
        log_success(f"Max {status.current} is the newest version.")
        return
    console.print(
        f"Max [bold cyan]{status.latest}[/bold cyan] is out. You have {status.current}."
    )
    if check_only:
        console.print("[dim]Run max update to install it.[/dim]")
        return
    update_max(assume_yes=yes)
