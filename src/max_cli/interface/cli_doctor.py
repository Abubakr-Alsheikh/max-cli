"""`max doctor`: show each setup check from `core/operations/doctor.py` with its fix."""

import typer
from rich.table import Table
from rich.text import Text

from max_cli.common.logger import console, log_error, log_success

app = typer.Typer(
    help="Check Max's setup and say how to fix it.",
    invoke_without_command=True,
)

# How each state looks: mark, colour.
LOOKS = {
    "ok": ("OK", "green"),
    "info": ("--", "cyan"),
    "warn": ("!!", "yellow"),
    "fail": ("XX", "red"),
}


@app.callback()
def doctor(
    ctx: typer.Context,
    offline: bool = typer.Option(
        False, "--offline", help="Don't ask PyPI for the newest Max."
    ),
) -> None:
    """Check Max's setup: version, FFmpeg, AI, YouTube, folders and more."""
    if ctx.invoked_subcommand is not None:
        return
    from max_cli.core.operations import doctor as doctor_ops

    with console.status("[dim]Checking...[/dim]"):
        results = doctor_ops.run(online=not offline)
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(no_wrap=True)
    table.add_column(style="bold", no_wrap=True)
    table.add_column()
    for result in results:
        mark, colour = LOOKS[result.state]
        detail = Text(result.detail)
        if result.fix:
            detail.append("\nFix: ", style="dim").append(result.fix, style="bold")
        table.add_row(Text(mark, style=f"bold {colour}"), result.name, detail)
    console.print(table)
    failed = [result.name for result in results if result.state == "fail"]
    warned = [result.name for result in results if result.state == "warn"]
    if failed:
        log_error(f"Fix these first: {', '.join(failed)}.")
    elif warned:
        console.print(
            f"[yellow]Max works. {len(warned)} thing(s) could be better.[/yellow]"
        )
    else:
        log_success("Everything Max needs is in place.")
