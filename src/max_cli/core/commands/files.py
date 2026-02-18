from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typer import Typer

from max_cli.interface import cli_files, cli_pdf


def register(app: "Typer") -> None:
    """Register file management commands."""
    app.add_typer(cli_files.app, name="files", help="Organize and bulk-rename files.")
    app.add_typer(cli_files.app, name="file", hidden=True)

    app.add_typer(cli_pdf.app, name="pdf", help="Merge, split, and compress PDFs.")
