import typer
from max_cli.interface import cli_images, cli_ai, cli_files
from max_cli.common.logger import console

app = typer.Typer(
    name="max",
    help="MAX: The High-Performance CLI Utility.",
    add_completion=True,
    no_args_is_help=True,
)

# Register the sub-commands
app.add_typer(
    cli_images.app, name="images", help="Compress, resize, and convert images."
)
app.add_typer(cli_files.app, name="files", help="Organize and bulk-rename files.")
# app.add_typer(cli_pdf.app, name="pdf", help="Merge and compress PDFs.") # Coming soon
app.add_typer(cli_ai.app, name="ai", help="Ask AI to run commands.")


@app.callback()
def main_callback():
    """
    Welcome to Max. Run 'max --help' for commands.
    """
    pass


if __name__ == "__main__":
    app()
