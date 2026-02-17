import typer
import sys
from rich.console import Console

# Import interfaces
from max_cli.interface import (
    cli_images,
    cli_files,
    cli_pdf,
    cli_ai,
    cli_media,
    cli_network,
    cli_tools,
    cli_config,
)  # <--- Import this
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

app.add_typer(cli_pdf.app, name="pdf", help="Merge, split, and compress PDFs.")

# Register Video/Audio
app.add_typer(
    cli_media.app, name="video", help="Compress, convert, and process video/audio."
)
app.add_typer(cli_media.app, name="v", hidden=True)  # Short alias

app.add_typer(cli_network.app, name="net", help="Network tools (Download, Speedtest).")

app.add_typer(cli_ai.app, name="ai", help="Ask AI to run commands.")

# Register grab-related commands at top level
app.add_typer(
    cli_network.app,
    name="grab",
    help="Download media from various platforms.",
)

# Register the group (optional, if you want 'max tools share')
app.add_typer(cli_tools.app, name="tools", help="System utilities (Clipboard, QR).")

# Register config commands
app.add_typer(cli_config.app, name="config", help="Manage API keys and settings.")

# Register top-level Shortcuts (The "Lazy" Way)
# This allows 'max share' instead of 'max tools share'
app.command("share")(cli_tools.share_qr)
app.command("paste")(cli_tools.paste_image)
app.command("copy")(cli_tools.copy_file)

# --- CRITICAL LINKING STEP ---
# Give the AI module access to this app instance so it can read the docs
cli_ai.MAIN_APP_REF = app


def main():
    """
    Main entry point with Global Error Handling.
    """
    try:
        app()
    except MaxError as e:
        # Expected errors (User mistake, missing file)
        console.print(f"[bold red]X Error:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        # Unexpected crashes (Bugs)
        console.print("[bold red]!! Critical Error (Unexpected)[/bold red]")
        console.print(f"An error occurred: {e}")
        console.print("[dim]If this persists, please report it to the developer.[/dim]")
        # Uncomment the next line during development to see the full stack trace:
        # raise e
        sys.exit(1)


if __name__ == "__main__":
    main()
