import typer
from pathlib import Path

from max_cli.core.engines.system_engine import SystemEngine
from max_cli.common.logger import console, log_success, log_error

app = typer.Typer()
engine = SystemEngine()


@app.command("share")
@app.command("qr", hidden=True)
def share_qr(
    data: str = typer.Argument(..., help="Text or URL to convert to QR Code."),
):
    """
    Generate an ASCII QR Code in the terminal.
    Useful for sending localhost URLs to your phone.
    """
    console.print(f"[cyan]Generating QR for:[/cyan] [dim]{data}[/dim]")
    try:
        engine.generate_qr(data)
    except Exception as e:
        log_error(f"QR generation failed: {e}")


@app.command("paste")
def paste_image(
    output: Path = typer.Argument(
        Path("clipboard.png"), help="Filename to save the image to."
    ),
):
    """
    Save the image currently in your clipboard to a file.
    Great for saving screenshots quickly.
    """
    # Ensure extension
    if not output.suffix:
        output = output.with_suffix(".png")

    try:
        engine.save_clipboard_image(output)
        log_success(f"Image saved to: [bold]{output}[/bold]")
    except ValueError as e:
        console.print(f"[yellow]{e}[/yellow]")
    except Exception as e:
        log_error(f"Failed to save image: {e}")


@app.command("copy")
def copy_file(
    target: Path = typer.Argument(..., help="Text file to copy to clipboard."),
):
    """
    Copy the contents of a text file to your system clipboard.
    """
    try:
        engine.copy_file_to_clipboard(target)
        log_success(f"Copied [bold]{target.name}[/bold] to clipboard.")
    except Exception as e:
        log_error(str(e))
