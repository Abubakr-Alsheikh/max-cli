import typer
from max_cli.interface import cli_images, cli_files, cli_pdf, cli_ai
from max_cli.common.logger import console

# Initialize the main application
app = typer.Typer(
    name="max",
    help="MAX: The High-Performance CLI Utility.",
    add_completion=True,
    no_args_is_help=True,
)

# Register sub-commands
app.add_typer(cli_images.app, name="images", help="Image manipulation tools")
app.add_typer(cli_files.app, name="files", help="File organization tools")
app.add_typer(cli_pdf.app, name="pdf", help="PDF operations")
app.add_typer(cli_ai.app, name="ai", help="AI Copilot")


@app.callback()
def main_callback():
    """
    Welcome to Max. Run 'max --help' for commands.
    """
    pass


if __name__ == "__main__":
    app()
