import urllib.parse
from pathlib import Path
from typing import Optional

import typer
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich import box

from max_cli.core.network_engine import NetworkEngine
from max_cli.core.queue_manager import get_queue_manager
from max_cli.common.logger import console, log_success, log_error
from max_cli.config import settings

app = typer.Typer(help="Download media from various platforms.")
engine = NetworkEngine()
queue_manager = get_queue_manager()


def _clean_url(url: str, strip_playlist: bool) -> str:
    """
    Removes playlist params (list, index) if the URL points to a specific video (v=...).
    """
    if not strip_playlist:
        return url

    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)

    if "v" in query and "list" in query:
        new_query = {"v": query["v"]}
        if "t" in query:
            new_query["t"] = query["t"]

        new_parts = list(parsed)
        new_parts[4] = urllib.parse.urlencode(new_query, doseq=True)
        cleaned_url = urllib.parse.urlunparse(new_parts)

        console.print("[dim]Auto-cleaned URL: Removed playlist info.[/dim]")
        return cleaned_url

    return url


@app.command("download")
def download_media(
    url: Optional[str] = typer.Argument(None, help="URL to download."),
    quality: Optional[str] = typer.Option(
        None,
        "--quality",
        "-q",
        help=f"Quality: [s]mall, [m]edium, [h]igh, [x]best. (Default: {settings.GRAB_QUALITY})",
    ),
    video: bool = typer.Option(False, "--video", "-v", help="Force video download."),
    audio: bool = typer.Option(False, "--audio", "-a", help="Audio only."),
    index: Optional[str] = typer.Option(
        None, "--index", "-i", help="Playlist index (e.g. '1', '1-5')."
    ),
    no_playlist: bool = typer.Option(
        False, "--no-playlist", help="Force single video download."
    ),
    no_meta: bool = typer.Option(
        False,
        "--no-meta",
        "--nom",
        help=f"Disable metadata/thumbnails. (Default: {'Include' if settings.GRAB_INCLUDE_METADATA else 'Exclude'})",
    ),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
    queue: bool = typer.Option(
        False, "--queue", "-Q", help="Add to queue instead of downloading immediately."
    ),
    no_process: bool = typer.Option(
        False, "--no-process", help="Add to queue but don't process immediately."
    ),
):
    """
    Download media using saved preferences or overrides.

    Examples:
        max grab                                    # Interactive mode
        max grab https://youtube.com/watch?v=...   # Download directly
        max grab -v https://...                    # Force video
        max grab -a https://...                    # Audio only
    """
    final_quality = quality if quality else settings.GRAB_QUALITY
    include_metadata = False if no_meta else settings.GRAB_INCLUDE_METADATA

    is_audio = audio
    if video:
        is_audio = False

    if settings.GRAB_DEFAULT_TYPE == "audio" and not video and not audio:
        is_audio = True

    target_output = output or settings.GRAB_DEFAULT_PATH
    if not target_output.exists():
        target_output.mkdir(parents=True, exist_ok=True)

    if url is None:
        console.print(
            "[cyan]Interactive Mode - Enter URL to download (Ctrl+C or empty to exit)[/cyan]"
        )
        console.print(
            "[dim]URL is added to queue. Downloads run in background while you add more.[/dim]\n"
        )

        import threading
        import time

        # Track if we should keep processing
        processing = False  # Don't start yet

        def process_forever():
            """Process queue items continuously."""
            while processing:
                try:
                    queue_manager.process_now()
                except Exception:
                    pass
                time.sleep(0.5)

        # Start processing after first URL is added
        process_thread = None

        try:
            while True:
                # Start processing after first URL is added
                if process_thread is None:
                    processing = True
                    process_thread = threading.Thread(target=process_forever)
                    process_thread.start()

                line = Prompt.ask("[bold]URL[/bold] (Enter to exit)", default="")
                if not line.strip():
                    break

                # Clean URL to strip playlist info if configured
                clean_u = _clean_url(
                    line.strip(),
                    settings.GRAB_STRIP_PLAYLIST and not index and not no_playlist,
                )

                # Add to queue - background processor will handle it
                queue_manager.add(
                    url=clean_u,
                    quality=final_quality,
                    audio_only=is_audio,
                    output_path=target_output,
                    include_metadata=include_metadata,
                    playlist_items=index,
                    no_playlist=no_playlist,
                )
                console.print("[green]+ Added[/green]")
        except KeyboardInterrupt:
            pass

        # Wait for pending downloads to complete before exiting
        stats = queue_manager.get_stats()
        pending = stats["pending"] + stats["downloading"]
        wait_count = 0
        if pending > 0:
            console.print(f"[dim]Waiting for {pending} download(s)...[/dim]")
            while pending > 0 and wait_count < 30:
                time.sleep(1)
                stats = queue_manager.get_stats()
                pending = stats["pending"] + stats["downloading"]
                wait_count += 1

        processing = False
        if process_thread:
            process_thread.join(timeout=2)

        # Check final status
        stats = queue_manager.get_stats()
        if stats["completed"] > 0:
            console.print(f"[green]Completed: {stats['completed']}[/green]")
        if stats["failed"] > 0:
            console.print(f"[red]Failed: {stats['failed']}[/red]")

        raise typer.Exit()
    else:
        clean_url = _clean_url(
            url, settings.GRAB_STRIP_PLAYLIST and not index and not no_playlist
        )
        _add_to_queue_or_download(
            clean_url,
            final_quality,
            is_audio,
            include_metadata,
            index,
            no_playlist,
            target_output,
            queue,
        )
        if (settings.GRAB_QUEUE_ENABLED or queue) and not no_process:
            console.print("[dim]Processing queue...[/dim]")
            queue_manager.process_now()


def _add_to_queue_or_download(
    url: str,
    quality: str,
    audio_only: bool,
    include_metadata: bool,
    index: Optional[str],
    no_playlist: bool,
    output_path: Path,
    queue_enabled: bool,
) -> None:
    """Add to queue or download immediately based on settings."""
    if settings.GRAB_QUEUE_ENABLED or queue_enabled:
        queue_manager.add(
            url=url,
            quality=quality,
            audio_only=audio_only,
            output_path=output_path,
            include_metadata=include_metadata,
            playlist_items=index,
            no_playlist=no_playlist,
        )
    else:
        _download_immediate(
            url, quality, audio_only, include_metadata, index, no_playlist, output_path
        )


def _download_immediate(
    url: str,
    quality: str,
    audio_only: bool,
    include_metadata: bool,
    index: Optional[str],
    no_playlist: bool,
    output_path: Path,
) -> None:
    """Download a single item immediately."""
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
                pass

    console.print(
        f"[cyan]Grabbing {'Audio' if audio_only else 'Video'} ({quality.upper()})...[/cyan]"
    )
    if not include_metadata:
        console.print("[dim]Metadata disabled.[/dim]")

    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        DownloadColumn,
        TransferSpeedColumn,
        TimeRemainingColumn,
    )

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
                output_path=output_path,
                quality=quality,
                audio_only=audio_only,
                include_metadata=include_metadata,
                playlist_items=index,
                no_playlist=no_playlist,
                progress_hook=rich_hook,
            )
            log_success("Download Finished.")
        except Exception as e:
            log_error(str(e))


@app.command("queue")
def show_queue():
    """Show the current download queue."""
    items = queue_manager.get_all()
    stats = queue_manager.get_stats()

    console.print("\n[bold]Queue Status:[/bold]")
    console.print(
        f"  Pending: {stats['pending']} | Downloading: {stats['downloading']} | Completed: {stats['completed']} | Failed: {stats['failed']}\n"
    )

    if not items:
        console.print("[dim]Queue is empty.[/dim]")
        return

    table = Table(title="Download Queue", box=box.ROUNDED)
    table.add_column("ID", style="cyan", width=8)
    table.add_column("Status", width=12)
    table.add_column("Title/URL", width=40)
    table.add_column("Progress", justify="right", width=10)
    table.add_column("Type", width=8)

    for item in items:
        status_color = {
            "pending": "yellow",
            "downloading": "cyan",
            "completed": "green",
            "failed": "red",
        }.get(item.status, "white")

        title = item.title if item.title else item.url
        title = (title[:37] + "...") if len(title) > 40 else title
        progress = f"{item.progress:.0f}%" if item.status == "downloading" else "-"

        table.add_row(
            item.id,
            f"[{status_color}]{item.status}[/{status_color}]",
            title,
            progress,
            "Audio" if item.audio_only else "Video",
        )

    console.print(table)


@app.command("clear")
def clear_queue(
    all: bool = typer.Option(
        False, "--all", "-a", help="Clear including completed/failed."
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation."),
):
    """Clear the download queue."""
    if all:
        if not force:
            if not Confirm.ask(
                "[red]Clear ALL items including completed/failed?[/red]"
            ):
                console.print("[yellow]Aborted.[/yellow]")
                return
        count = queue_manager.clear()
        log_success(f"Cleared {count} items from queue.")
    else:
        pending = queue_manager.get_pending()
        if not pending:
            console.print("[dim]No pending items to clear.[/dim]")
            return

        if not force:
            if not Confirm.ask(f"[yellow]Clear {len(pending)} pending items?[/yellow]"):
                console.print("[yellow]Aborted.[/yellow]")
                return

        queue_manager.clear()
        log_success(f"Cleared {len(pending)} pending items.")


@app.command("status")
def queue_status():
    """Show detailed queue statistics."""
    stats = queue_manager.get_stats()

    table = Table(title="Queue Statistics", box=box.ROUNDED)
    table.add_column("Status", style="cyan")
    table.add_column("Count", justify="right", style="bold")

    table.add_row("Total", str(stats["total"]))
    table.add_row("Pending", str(stats["pending"]))
    table.add_row("Downloading", str(stats["downloading"]))
    table.add_row("Completed", f"[green]{stats['completed']}[/green]")
    table.add_row("Failed", f"[red]{stats['failed']}[/red]")

    console.print(table)


if __name__ == "__main__":
    app()
