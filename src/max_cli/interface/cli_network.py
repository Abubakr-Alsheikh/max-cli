import typer
from pathlib import Path
from rich.prompt import Confirm, Prompt
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
)

from max_cli.core.network_engine import NetworkEngine
from max_cli.common.logger import console, log_success, log_error

app = typer.Typer()
engine = NetworkEngine()


@app.command("grab")
def download_media(
    url: str = typer.Argument(..., help="URL (YouTube, Twitch, Twitter, etc)."),
    quality: str = typer.Option(
        "h", "--quality", "-q", help="[s]mall, [m]edium, [h]igh, [x]best."
    ),
    audio: bool = typer.Option(False, "--audio", "-a", help="Audio only."),
    index: str = typer.Option(
        None, "--index", "-i", help="Playlist index (e.g. '1', '1-5', '1,3')."
    ),
    no_playlist: bool = typer.Option(
        False,
        "--no-playlist",
        help="Only download the specific video in a playlist URL.",
    ),
    no_meta: bool = typer.Option(
        False, "--no-meta", help="Clear file: No metadata or embedded thumbnails."
    ),
    output: Path = typer.Option(Path("."), "--output", "-o"),
):
    """
    Download media with Playlist and Metadata control.

    [bold]Quality Guide:[/bold]
    [green]s (Small)[/green]:  480p Video / 64k Audio  (Great for data saving / speech)
    [green]m (Medium)[/green]: 720p Video / 128k Audio (Standard Web Quality)
    [green]h (High)[/green]:   1080p Video / 192k Audio (HD - Default)
    [green]x (Xtreme)[/green]: 4K Video    / 320k Audio (Best possible quality)
    """
    if not output.exists():
        output.mkdir(parents=True, exist_ok=True)

    # 1. Playlist Logic Check
    with console.status("[dim]Checking URL...[/dim]"):
        try:
            info = engine.get_info(url)
            is_playlist = "entries" in info

            if is_playlist and not index and not no_playlist:
                count = len(info["entries"])
                if not Confirm.ask(
                    f"[yellow]This is a playlist with {count} items. Download ALL?[/yellow]"
                ):
                    # Offer to download just the first one or exit
                    choice = Prompt.ask(
                        "Enter [bold]index[/bold] to download, or [bold]n[/bold] to cancel",
                        default="n",
                    )
                    if choice.lower() == "n":
                        raise typer.Exit()
                    index = choice
        except Exception as e:
            log_error(f"URL Check failed: {e}")
            raise typer.Exit(1)

    # 2. UI Feedback
    q_map = {"s": "Small", "m": "Medium", "h": "High", "x": "Best"}
    q_label = q_map.get(quality.lower()[0], "Custom")

    console.print(f"[cyan]Grabbing ({q_label} Quality)...[/cyan]")
    if no_meta:
        console.print("[dim]Note: Metadata embedding is disabled.[/dim]")
    console.print(f"[dim]Source: {url}[/dim]")

    # Rich Progress Bar Setup
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.fields[filename]}", justify="left"),
        BarColumn(bar_width=None),
        "[progress.percentage]{task.percentage:>3.0f}%",
        "•",
        DownloadColumn(),
        "•",
        TransferSpeedColumn(),
        "•",
        TimeRemainingColumn(),
        console=console,
        transient=True,
    )

    task_id = progress.add_task("Starting...", filename="Fetching info...", start=False)

    def rich_hook(d):
        if d["status"] == "downloading":
            filename = d.get("filename", "").split("/")[-1]
            # Truncate long filenames
            filename = (filename[:30] + "...") if len(filename) > 30 else filename

            progress.update(
                task_id,
                total=d.get("total_bytes") or d.get("total_bytes_estimate"),
                completed=d.get("downloaded_bytes"),
                filename=filename,
                start=True,
            )
        elif d["status"] == "finished":
            progress.update(task_id, filename="Processing...")

    with progress:
        try:
            engine.download_media(
                url=url,
                output_path=output,
                quality=quality,
                audio_only=audio,
                include_metadata=not no_meta,
                playlist_items=index,
                no_playlist=no_playlist,
                progress_hook=rich_hook,
            )
            log_success(f"Saved to [bold]{output}[/bold]")
        except Exception as e:
            log_error(str(e))
