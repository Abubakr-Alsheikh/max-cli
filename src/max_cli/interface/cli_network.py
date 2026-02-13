import typer
import urllib.parse
from pathlib import Path
from typing import Optional
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
)
from rich.prompt import Confirm, Prompt

from max_cli.core.network_engine import NetworkEngine
from max_cli.common.logger import console, log_success, log_error
from max_cli.config import settings

app = typer.Typer()
engine = NetworkEngine()


def _clean_url(url: str, strip_playlist: bool) -> str:
    """
    Removes playlist params (list, index) if the URL points to a specific video (v=...).
    """
    if not strip_playlist:
        return url

    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)

    # Only strip if it's a video AND a list (e.g. youtube.com/watch?v=...&list=...)
    if "v" in query and "list" in query:
        # Rebuild query with only 'v' (and keep other stuff like 't' for timestamp)
        new_query = {"v": query["v"]}
        if "t" in query:
            new_query["t"] = query["t"]

        new_parts = list(parsed)
        new_parts[4] = urllib.parse.urlencode(new_query, doseq=True)
        cleaned_url = urllib.parse.urlunparse(new_parts)

        console.print(f"[dim]Auto-cleaned URL: Removed playlist info.[/dim]")
        return cleaned_url

    return url


@app.command("grab")
def download_media(
    url: str = typer.Argument(..., help="URL to download."),
    # We use Optional[str] = None so we can detect if the User provided a flag or not.
    quality: Optional[str] = typer.Option(
        None,
        "--quality",
        "-q",
        help=f"Quality: [s]mall, [m]edium, [h]igh, [x]best. (Default: {settings.GRAB_QUALITY})",
    ),
    audio: bool = typer.Option(False, "--audio", "-a", help="Audio only."),
    # Index/Playlist Controls
    index: str = typer.Option(
        None, "--index", "-i", help="Playlist index (e.g. '1', '1-5')."
    ),
    no_playlist: bool = typer.Option(
        False, "--no-playlist", help="Force single video download."
    ),
    # Metadata: We default to None to allow Config fallback, but allow --no-meta/--nom to override
    no_meta: bool = typer.Option(
        False,
        "--no-meta",
        "--nom",  # <--- New Shortcut
        help=f"Disable metadata/thumbnails. (Default Setting: {'Include' if settings.GRAB_INCLUDE_METADATA else 'Exclude'})",
    ),
    output: Path = typer.Option(Path("."), "--output", "-o"),
):
    """
    Download media using saved preferences or overrides.
    """
    if not output.exists():
        output.mkdir(parents=True, exist_ok=True)

    # --- 1. Resolve Settings Priority (Flag > Config > Default) ---
    final_quality = quality if quality else settings.GRAB_QUALITY

    # Logic for Metadata:
    # If user passed --no-meta (True), we force False.
    # If user didn't pass it (False), we use the Config setting.
    include_metadata = False if no_meta else settings.GRAB_INCLUDE_METADATA

    # --- 2. URL Cleaning ---
    # If the user explicitly asks for an index or no_playlist, we don't mess with the URL.
    # Otherwise, we check the config preference.
    if not index and not no_playlist:
        url = _clean_url(url, settings.GRAB_STRIP_PLAYLIST)

    # --- 3. Playlist Check Logic ---
    # Only perform the check if we haven't already stripped the playlist info
    should_check_playlist = ("list=" in url) and (not no_playlist) and (not index)

    if should_check_playlist:
        with console.status("[dim]Checking URL...[/dim]"):
            try:
                info = engine.get_info(url)
                if "entries" in info:
                    count = len(info["entries"])
                    if not Confirm.ask(
                        f"[yellow]Playlist detected ({count} items). Download ALL?[/yellow]"
                    ):
                        choice = Prompt.ask(
                            "Enter [bold]index[/bold] (e.g. 1) or [bold]n[/bold] to cancel",
                            default="n",
                        )
                        if choice.lower() == "n":
                            raise typer.Exit()
                        index = choice
            except Exception:
                pass  # Fail silently on check, let downloader handle errors

    # --- 4. Execution ---
    console.print(
        f"[cyan]Grabbing {'Audio' if audio else 'Video'} ({final_quality.upper()})...[/cyan]"
    )
    if not include_metadata:
        console.print("[dim]Metadata disabled.[/dim]")

    # Setup Rich Progress (Same as before)
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
                quality=final_quality,  # Use the resolved quality
                audio_only=audio,
                include_metadata=include_metadata,  # Use resolved meta
                playlist_items=index,
                no_playlist=no_playlist,
                progress_hook=rich_hook,
            )
            log_success("Download Finished.")
        except Exception as e:
            log_error(str(e))
