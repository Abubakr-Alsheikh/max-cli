from pathlib import Path

import typer
from rich.markup import escape

from max_cli.common.logger import console, log_error, log_success
from max_cli.core.operations import tools as tools_ops
from max_cli.interface.confirm import skip_confirmation

app = typer.Typer()


def _get_engine():
    from max_cli.core.engines.system_engine import SystemEngine

    return SystemEngine()


@app.command("share")
@app.command("qr", hidden=True)
def share_qr(
    data: str = typer.Argument(..., help="Text or link to put in the code."),
):
    """
    Generate an ASCII QR Code in the terminal.
    Useful for sending localhost URLs to your phone.
    """
    console.print(f"[cyan]Generating QR for:[/cyan] [dim]{escape(data)}[/dim]")
    try:
        result = tools_ops.share(data, engine=_get_engine())
    except Exception as e:
        log_error(escape(f"QR generation failed: {e}"))
        return
    console.print()
    console.print(result.details["qr"], markup=False, highlight=False, soft_wrap=True)


@app.command("paste")
def paste_image(
    output: Path = typer.Argument(
        tools_ops.DEFAULT_PASTE_OUTPUT,
        help="File to save. Max adds .png when you leave off the extension.",
    ),
    overwrite: bool = typer.Option(
        False, "-f", "--force", help="Replace a file that already has this name."
    ),
):
    """
    Save the image currently in your clipboard to a file.
    Great for saving screenshots quickly.
    """
    target = tools_ops.paste_target(output)
    if target.exists() and not overwrite:
        if not skip_confirmation(False):
            from rich.prompt import Confirm

            if not Confirm.ask(f"{escape(str(target))} already exists. Overwrite it?"):
                console.print("[dim]Cancelled. The file was not changed.[/dim]")
                return
        overwrite = True

    try:
        result = tools_ops.paste(output, overwrite, engine=_get_engine())
    except Exception as e:
        log_error(escape(f"Failed to save image: {e}"))
        return
    if result.ok:
        log_success(f"Image saved to: [bold]{escape(str(target))}[/bold]")
    else:
        console.print(f"[yellow]{escape(result.message)}[/yellow]")


@app.command("copy")
def copy_file(
    target: Path = typer.Argument(..., help="Text file to copy."),
):
    """
    Copy the contents of a text file to your system clipboard.
    """
    try:
        result = tools_ops.copy(target, engine=_get_engine())
    except Exception as e:
        log_error(escape(str(e)))
        return
    log_success(escape(result.message))
