import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich import box

from max_cli.common.events import get_emitter
from max_cli.common.logger import console, log_success, log_error
from max_cli.config import settings
from max_cli.interface.event_subscriber import EventSubscriber

app = typer.Typer(help="Download media from various platforms.")


def _get_engine():
    from max_cli.core.engines.network_engine import NetworkEngine

    return NetworkEngine()


def _get_queue_manager():
    from max_cli.core.engines.queue_manager import get_queue_manager

    return get_queue_manager()


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
@app.command("do", hidden=True)
def download_media(
    url: Optional[str] = typer.Argument(None, help="URL to download."),
    quality: Optional[str] = typer.Option(
        None,
        "--quality",
        "-q",
        help="Quality: [ss] (360p), [s]mall (480p), [m]edium (720p), [h]igh (1080p), [x]best (4K).",
    ),
    resolution: Optional[int] = typer.Option(
        None,
        "--resolution",
        "-r",
        help="Custom resolution: 144, 240, 360, 480, 720, 1080, etc. Overrides quality.",
    ),
    video: bool = typer.Option(False, "--video", "-v", help="Force video download."),
    audio: bool = typer.Option(False, "--audio", "-a", help="Audio only."),
    subtitles: bool = typer.Option(
        False,
        "--subtitles",
        "-s",
        help="Download subtitles/closed captions.",
    ),
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
    progress: bool = typer.Option(
        True,
        "--progress/--no-progress",
        help="Show download progress bar.",
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
            qm = _get_queue_manager()
            while processing:
                try:
                    qm.process_now()
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
                qm = _get_queue_manager()
                qm.add(
                    url=clean_u,
                    quality=final_quality,
                    audio_only=is_audio,
                    output_path=target_output,
                    include_metadata=include_metadata,
                    playlist_items=index,
                    no_playlist=no_playlist,
                    subtitles=subtitles,
                    custom_height=resolution,
                )
                console.print("[green]+ Added[/green]")
        except KeyboardInterrupt:
            pass

        # Wait for pending downloads to complete before exiting
        qm = _get_queue_manager()
        stats = qm.get_stats()
        pending = stats["pending"] + stats["downloading"]
        wait_count = 0
        if pending > 0:
            console.print(f"[dim]Waiting for {pending} download(s)...[/dim]")
            while pending > 0 and wait_count < 30:
                time.sleep(1)
                stats = qm.get_stats()
                pending = stats["pending"] + stats["downloading"]
                wait_count += 1

        processing = False
        if process_thread:
            process_thread.join(timeout=2)

        # Check final status
        stats = qm.get_stats()
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
            subtitles,
            resolution,
            progress,
        )
        if queue:
            import threading

            console.print("[dim]Processing queue in background...[/dim]")

            def process_background():
                qm = _get_queue_manager()
                try:
                    qm.process_now()
                except Exception:
                    pass

            thread = threading.Thread(target=process_background, daemon=True)
            thread.start()


def _add_to_queue_or_download(
    url: str,
    quality: str,
    audio_only: bool,
    include_metadata: bool,
    index: Optional[str],
    no_playlist: bool,
    output_path: Path,
    queue_enabled: bool,
    subtitles: bool = False,
    custom_height: Optional[int] = None,
    show_progress: bool = True,
) -> None:
    """Add to queue or download immediately based on settings."""
    if queue_enabled:
        qm = _get_queue_manager()
        qm.add(
            url=url,
            quality=quality,
            audio_only=audio_only,
            output_path=output_path,
            include_metadata=include_metadata,
            playlist_items=index,
            no_playlist=no_playlist,
            subtitles=subtitles,
            custom_height=custom_height,
        )
        log_success("Added to queue.")
    else:
        eng = _get_engine()
        q_info = eng.get_quality_info(quality, custom_height)
        _download_immediate(
            url,
            quality,
            audio_only,
            include_metadata,
            index,
            no_playlist,
            output_path,
            subtitles=subtitles,
            custom_height=custom_height,
            quality_label=str(q_info["label"]),
            show_progress=show_progress,
        )


def _download_immediate(
    url: str,
    quality: str,
    audio_only: bool,
    include_metadata: bool,
    index: Optional[str],
    no_playlist: bool,
    output_path: Path,
    subtitles: bool = False,
    custom_height: Optional[int] = None,
    quality_label: str = "",
    show_progress: bool = True,
) -> None:
    """Download a single item immediately."""
    should_check_playlist = ("list=" in url) and (not no_playlist) and (not index)

    if should_check_playlist:
        with console.status("[dim]Checking URL...[/dim]"):
            try:
                eng = _get_engine()
                info = eng.get_info(url)
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

    if audio_only:
        eng = _get_engine()
        q_info = eng.get_quality_info(quality, custom_height)
        bitrate = q_info.get("bitrate", 192)
        quality_display = f"{bitrate}kbps"
    else:
        quality_display = quality_label if quality_label else quality.upper()
    console.print(
        f"[cyan]Grabbing {'Audio' if audio_only else 'Video'} ({quality_display})...[/cyan]"
    )
    if subtitles:
        console.print("[dim]Subtitles: Enabled[/dim]")
    if not include_metadata:
        console.print("[dim]Metadata disabled.[/dim]")

    if not show_progress:
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                eng = _get_engine()
                eng.download_media(
                    url=url,
                    output_path=output_path,
                    quality=quality,
                    audio_only=audio_only,
                    include_metadata=include_metadata,
                    playlist_items=index,
                    no_playlist=no_playlist,
                    subtitles=subtitles,
                    custom_height=custom_height,
                )
                log_success("Download Finished.")
                return
            except Exception as e:
                last_error = e
                if attempt < 2:
                    wait = 5 * (attempt + 1)
                    console.print(
                        f"[yellow]Download failed (attempt {attempt + 1}/3). Retrying in {wait}s...[/yellow]"
                    )
                    time.sleep(wait)
        log_error(str(last_error))
        return

    emitter = get_emitter()
    subscriber = EventSubscriber(emitter)
    subscriber.subscribe()

    with subscriber.create_progress_context(
        1, f"Grabbing {'Audio' if audio_only else 'Video'}..."
    ):
        retry_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                eng = _get_engine()
                eng.download_media(
                    url=url,
                    output_path=output_path,
                    quality=quality,
                    audio_only=audio_only,
                    include_metadata=include_metadata,
                    playlist_items=index,
                    no_playlist=no_playlist,
                    subtitles=subtitles,
                    custom_height=custom_height,
                )
                log_success("Download Finished.")
                break
            except Exception as e:
                retry_error = e
                if attempt < 2:
                    wait = 5 * (attempt + 1)
                    console.print(
                        f"[yellow]Download failed (attempt {attempt + 1}/3). Retrying in {wait}s...[/yellow]"
                    )
                    time.sleep(wait)
        else:
            log_error(str(retry_error))

    subscriber.unsubscribe()


@app.command("queue")
def show_queue(
    process: bool = typer.Option(
        False, "--process", "-p", help="Process pending downloads."
    ),
):
    """Show the current download queue."""
    qm = _get_queue_manager()
    items = qm.get_all()
    stats = qm.get_stats()

    console.print("\n[bold]Queue Status:[/bold]")
    console.print(
        f"  Pending: {stats['pending']} | Downloading: {stats['downloading']} | Completed: {stats['completed']} | Failed: {stats['failed']}\n"
    )

    if process:
        console.print("[dim]Processing queue...[/dim]")
        qm.process_now()
        stats = qm.get_stats()
        if stats["completed"] > 0:
            console.print(f"[green]Completed: {stats['completed']}[/green]")
        if stats["failed"] > 0:
            console.print(f"[red]Failed: {stats['failed']}[/red]")
        return

    if not items:
        console.print("[dim]Queue is empty.[/dim]")
        return

    table = Table(title="Download Queue", box=box.ROUNDED)
    table.add_column("ID", style="cyan", width=8)
    table.add_column("Status", width=12)
    table.add_column("URL", width=50)
    table.add_column("Progress", justify="right", width=10)
    table.add_column("Type", width=8)

    for item in items:
        status_color = {
            "pending": "yellow",
            "downloading": "cyan",
            "completed": "green",
            "failed": "red",
        }.get(item.status, "white")

        url = item.url
        progress = f"{item.progress:.0f}%" if item.status == "downloading" else "-"

        table.add_row(
            item.id,
            f"[{status_color}]{item.status}[/{status_color}]",
            url,
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
        qm = _get_queue_manager()
        count = qm.clear()
        log_success(f"Cleared {count} items from queue.")
    else:
        qm = _get_queue_manager()
        pending = qm.get_pending()
        if not pending:
            console.print("[dim]No pending items to clear.[/dim]")
            return

        if not force:
            if not Confirm.ask(f"[yellow]Clear {len(pending)} pending items?[/yellow]"):
                console.print("[yellow]Aborted.[/yellow]")
                return

        qm.clear()
        log_success(f"Cleared {len(pending)} pending items.")


@app.command("status")
def queue_status():
    """Show detailed queue statistics."""
    qm = _get_queue_manager()
    stats = qm.get_stats()

    table = Table(title="Queue Statistics", box=box.ROUNDED)
    table.add_column("Status", style="cyan")
    table.add_column("Count", justify="right", style="bold")

    table.add_row("Total", str(stats["total"]))
    table.add_row("Pending", str(stats["pending"]))
    table.add_row("Downloading", str(stats["downloading"]))
    table.add_row("Completed", f"[green]{stats['completed']}[/green]")
    table.add_row("Failed", f"[red]{stats['failed']}[/red]")

    console.print(table)


@app.command("history")
def show_history(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of items to show."),
    clear: bool = typer.Option(False, "--clear", "-c", help="Clear history."),
):
    """Show download history."""
    if clear:
        qm = _get_queue_manager()
        count = qm.clear_history()
        log_success(f"Cleared {count} items from history.")
        return

    qm = _get_queue_manager()
    history = qm.get_history()[:limit]

    if not history:
        console.print("[dim]No download history.[/dim]")
        return

    from max_cli.common.utils import format_size

    table = Table(title="Download History", box=box.ROUNDED)
    table.add_column("URL/Title", style="cyan", width=50)
    table.add_column("Size", justify="right", width=10)
    table.add_column("Type", width=8)
    table.add_column("Quality", width=8)
    table.add_column("Date", width=20)

    for item in history:
        title = item.title if item.title else item.url
        size = format_size(item.file_size) if item.file_size > 0 else "-"

        # Format date
        date = "-"
        if item.completed_at:
            try:
                dt = datetime.fromisoformat(item.completed_at)
                date = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass

        table.add_row(
            title,
            size,
            "Audio" if item.audio_only else "Video",
            item.quality.upper(),
            date,
        )

    console.print(table)


if __name__ == "__main__":
    app()
