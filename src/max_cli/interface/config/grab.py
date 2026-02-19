import typer
from pathlib import Path
from rich.prompt import Prompt, Confirm
from rich.panel import Panel

from max_cli.common.logger import console, log_success, log_error
from max_cli.config import settings

app = typer.Typer()

GLOBAL_CONFIG_PATH = Path.home() / ".max_config.env"


@app.command("grab")
def configure_grab():
    """Configure default settings for the Media Downloader."""
    console.print(
        Panel("[bold cyan]Downloader Preferences[/bold cyan]", border_style="cyan")
    )

    current_data = {}

    q_choice = Prompt.ask(
        "Default Video/Audio Quality?",
        choices=["s", "m", "h", "x"],
        default=settings.GRAB_QUALITY,
    )
    current_data["GRAB_QUALITY"] = q_choice

    strip_pl = Confirm.ask(
        "Auto-strip Playlist info?", default=settings.GRAB_STRIP_PLAYLIST
    )
    console.print("[dim]  (If Yes: 'watch?v=ID&list=LIST' becomes 'watch?v=ID')[/dim]")
    current_data["GRAB_STRIP_PLAYLIST"] = str(strip_pl)

    meta = Confirm.ask(
        "Embed Metadata (Tags/Thumbnail)?", default=settings.GRAB_INCLUDE_METADATA
    )
    current_data["GRAB_INCLUDE_METADATA"] = str(meta)

    type_choice = Prompt.ask(
        "Default download type?",
        choices=["video", "audio"],
        default=settings.GRAB_DEFAULT_TYPE,
    )
    current_data["GRAB_DEFAULT_TYPE"] = type_choice

    default_path = Prompt.ask(
        "Default download folder?",
        default=str(settings.GRAB_DEFAULT_PATH),
    )
    current_data["GRAB_DEFAULT_PATH"] = default_path

    queue_enabled = Confirm.ask(
        "Enable queue system?", default=settings.GRAB_QUEUE_ENABLED
    )
    console.print(
        "[dim]  (Queue allows adding multiple URLs and processing in background)[/dim]"
    )
    current_data["GRAB_QUEUE_ENABLED"] = str(queue_enabled)

    try:
        lines = []
        if GLOBAL_CONFIG_PATH.exists():
            lines = GLOBAL_CONFIG_PATH.read_text().splitlines()

        keys = [
            "GRAB_QUALITY",
            "GRAB_STRIP_PLAYLIST",
            "GRAB_INCLUDE_METADATA",
            "GRAB_DEFAULT_TYPE",
            "GRAB_DEFAULT_PATH",
            "GRAB_QUEUE_ENABLED",
        ]
        lines = [line for line in lines if not any(line.startswith(k) for k in keys)]

        for k, v in current_data.items():
            lines.append(f"{k}={v}")

        GLOBAL_CONFIG_PATH.write_text("\n".join(lines) + "\n")
        log_success("Downloader settings saved!")

    except Exception as e:
        log_error(f"Failed to save settings: {e}")
