import typer
import sys
from rich.console import Console

# Import interfaces
from max_cli.interface import cli_images, cli_files, cli_pdf, cli_ai
from max_cli.common.exceptions import MaxError

# Initialize Console directly here to ensure it's available for the crash handler
console = Console()

app = typer.Typer(
    name="max",
    help="MAX: The High-Performance CLI Utility.",
    add_completion=True,
    no_args_is_help=True,
)

# --- 1. Register Commands with Aliases ---
# We register 'images' AND 'img' so users can type less.
app.add_typer(
    cli_images.app, name="images", help="Compress, resize, and convert images."
)
app.add_typer(cli_images.app, name="img", hidden=True)  # Hidden alias

app.add_typer(cli_files.app, name="files", help="Organize and bulk-rename files.")
app.add_typer(cli_files.app, name="file", hidden=True)  # Hidden alias

app.add_typer(cli_pdf.app, name="pdf", help="Merge and compress PDFs.")

app.add_typer(cli_ai.app, name="ai", help="Ask AI to run commands.")


def main():
    """
    Main entry point with Global Error Handling.
    """
    try:
        app()
    except MaxError as e:
        # Expected errors (User mistake, missing file)
        console.print(f"[bold red]✖ Error:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        # Unexpected crashes (Bugs)
        console.print("[bold red]💥 Critical Error (Unexpected)[/bold red]")
        console.print(f"An error occurred: {e}")
        console.print("[dim]If this persists, please report it to the developer.[/dim]")
        # Uncomment the next line during development to see the full stack trace:
        # raise e
        sys.exit(1)


if __name__ == "__main__":
    main()
