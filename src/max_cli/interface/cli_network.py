import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

import shutil
import typer
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich import box

from max_cli.common.events import get_emitter
from max_cli.common.logger import console, log_success, log_error
from max_cli.config import settings
from max_cli.core.engines.network_engine import POT_PROVIDER_PACKAGE
from max_cli.interface.event_subscriber import EventSubscriber

app = typer.Typer(help="Download media from various platforms.")

INTERACTIVE_POLL_SECONDS = 0.5
INTERACTIVE_WAIT_SECONDS = 30  # how long interactive mode waits for downloads


class PlayerClient(str, Enum):
    """YouTube player clients accepted by --player-client."""

    AUTO = "auto"
    DEFAULT = "default"
    WEB = "web"
    TV = "tv"
    IOS = "ios"
    ANDROID = "android"
    MWEB = "mweb"
    TV_EMBEDDED = "tv_embedded"


def _get_engine():
    from max_cli.core.engines.network_engine import NetworkEngine

    return NetworkEngine()


def _get_task_manager():
    from max_cli.core.engines.task_manager import get_task_manager

    return get_task_manager()


def _queue_download(url: str, **options) -> Optional[str]:
    """Queue a download task. Returns its ID, or None if the URL is downloading."""
    from max_cli.core.engines.network_engine import make_download_task
    from max_cli.core.engines.task_queue import TaskStatus, TaskType

    manager = _get_task_manager()
    for task in manager.get_all(status=TaskStatus.RUNNING):
        if task.type == TaskType.DOWNLOAD and task.payload.get("url") == url:
            console.print(f"[yellow]Already downloading:[/yellow] {url}")
            return None
    task = manager.add(make_download_task(url, **options))
    console.print(f"[dim]Added to queue:[/dim] {url}")
    return task.id


def _process_downloads() -> None:
    from max_cli.core.engines.task_queue import TaskType

    _get_task_manager().process_now(task_type=TaskType.DOWNLOAD)


def _download_stats() -> dict:
    from max_cli.core.engines.task_queue import TaskType

    return _get_task_manager().get_stats(task_type=TaskType.DOWNLOAD)


def _print_outcome(task_ids: List[str]) -> None:
    """Print how many of `task_ids` completed and failed."""
    from max_cli.core.engines.task_queue import TaskStatus

    manager = _get_task_manager()
    statuses = [getattr(manager.get(task_id), "status", None) for task_id in task_ids]
    completed = statuses.count(TaskStatus.COMPLETED)
    failed = statuses.count(TaskStatus.FAILED)
    if completed:
        console.print(f"[green]Completed: {completed}[/green]")
    if failed:
        console.print(f"[red]Failed: {failed}[/red]")


def _clean_url(url: str, strip_playlist: bool) -> str:
    """
    Removes playlist params (list, index) if the URL points to a specific video (v=...).
    """
    if not strip_playlist:
        return url

    from max_cli.core.engines.network_engine import strip_playlist_params

    cleaned_url = strip_playlist_params(url)
    if cleaned_url != url:
        console.print("[dim]Auto-cleaned URL: Removed playlist info.[/dim]")
    return cleaned_url


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
    player_client: Optional[PlayerClient] = typer.Option(
        None,
        "--player-client",
        help="YouTube player client override (fixes HTTP 403/SABR errors).",
        case_sensitive=False,
    ),
):
    """
    Download media using saved preferences or overrides.

    Examples:
        max grab download                                   # Interactive mode
        max grab download https://youtube.com/watch?v=...   # Download directly
        max grab download -v https://...                    # Force video
        max grab download -a https://...                    # Audio only
    """
    final_quality = quality if quality else settings.GRAB_QUALITY
    include_metadata = False if no_meta else settings.GRAB_INCLUDE_METADATA
    player_client_name = player_client.value if player_client else None

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

        queued_ids: List[str] = []

        def process_forever():
            """Process queued downloads until the prompt loop ends."""
            while processing:
                _process_downloads()
                time.sleep(INTERACTIVE_POLL_SECONDS)

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
                task_id = _queue_download(
                    clean_u,
                    quality=final_quality,
                    audio_only=is_audio,
                    output_path=target_output,
                    include_metadata=include_metadata,
                    playlist_items=index,
                    no_playlist=no_playlist,
                    subtitles=subtitles,
                    custom_height=resolution,
                    player_client=player_client_name,
                )
                if task_id:
                    queued_ids.append(task_id)
                    console.print("[green]+ Added[/green]")
        except KeyboardInterrupt:
            pass

        # Wait for pending downloads to complete before exiting
        stats = _download_stats()
        pending = stats["pending"] + stats["running"]
        wait_count = 0
        if pending > 0:
            console.print(f"[dim]Waiting for {pending} download(s)...[/dim]")
            while pending > 0 and wait_count < INTERACTIVE_WAIT_SECONDS:
                time.sleep(1)
                stats = _download_stats()
                pending = stats["pending"] + stats["running"]
                wait_count += 1

        processing = False
        if process_thread:
            process_thread.join(timeout=2)

        _print_outcome(queued_ids)

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
            player_client_name,
        )
        if queue:
            import threading

            console.print("[dim]Processing queue in background...[/dim]")

            thread = threading.Thread(target=_process_downloads, daemon=True)
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
    player_client: Optional[str] = None,
) -> None:
    """Add to queue or download immediately based on settings."""
    if queue_enabled:
        _queue_download(
            url,
            quality=quality,
            audio_only=audio_only,
            output_path=output_path,
            include_metadata=include_metadata,
            playlist_items=index,
            no_playlist=no_playlist,
            subtitles=subtitles,
            custom_height=custom_height,
            player_client=player_client,
        )
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
            player_client=player_client,
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
    player_client: Optional[str] = None,
) -> None:
    """Download a single item immediately."""
    should_check_playlist = ("list=" in url) and (not no_playlist) and (not index)

    if should_check_playlist:
        info: dict = {}
        with console.status("[dim]Checking URL...[/dim]"):
            try:
                info = _get_engine().get_info(url)
            except Exception as e:  # noqa: BLE001 - the download itself reports real errors
                console.print(f"[dim]Could not check the playlist: {e}[/dim]")
        # Prompt outside the try: typer.Exit is an Exception and must reach typer.
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
    if not _get_engine().has_js:
        console.print(
            "[yellow]Warning: No JavaScript runtime (Node.js/Deno) found.[/yellow]"
        )
        console.print(
            "[dim]YouTube downloads may be limited or fail. "
            "Install Deno: winget install DenoLand.Deno[/dim]"
        )
    if subtitles:
        console.print("[dim]Subtitles: Enabled[/dim]")
    if not include_metadata:
        console.print("[dim]Metadata disabled.[/dim]")

    def _do_download() -> None:
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
            player_client=player_client,
        )

    def _handle_final_error(error: Optional[Exception]) -> None:
        error_text = str(error or "")
        is_youtube_403 = ("403" in error_text or "SABR" in error_text) and (
            "youtube.com" in url or "youtu.be" in url
        )
        if is_youtube_403 and _offer_pot_setup():
            try:
                _do_download()
                log_success("Download Finished.")
                return
            except Exception as retry_err:
                error = retry_err
        log_error(str(error))

    if not show_progress:
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                _do_download()
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
        _handle_final_error(last_error)
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
                _do_download()
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
            _handle_final_error(retry_error)

    subscriber.unsubscribe()


@app.command("pot-setup")
def pot_setup(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip all confirmations."),
):
    """
    Install the YouTube PO token provider (fixes HTTP 403 / SABR errors).

    This sets up the bgutil POT provider: pip plugin + Deno server script.
    Required: Deno installed and on PATH (winget install DenoLand.Deno).
    """
    eng = _get_engine()

    if not eng.has_js or not shutil.which("deno"):
        log_error("Deno not found. Install it first: winget install DenoLand.Deno")
        raise typer.Exit(code=1)

    if eng.pot_provider_available():
        console.print("[green]PO token provider is already installed.[/green]")
        return

    console.print(
        "[cyan]This will install the bgutil POT provider to fix YouTube 403/SABR errors:[/cyan]"
    )
    console.print(
        f"  1. pip install -U {POT_PROVIDER_PACKAGE} (yt-dlp plugin)"
    )
    console.print(
        "  2. git clone bgutil-ytdlp-pot-provider (to ~/bgutil-ytdlp-pot-provider)"
    )
    console.print(
        "  3. deno install of server dependencies (canvas, may take minutes)\n"
    )

    if not yes:
        if not Confirm.ask("Proceed with installation?"):
            console.print("[yellow]Aborted.[/yellow]")
            return

    with console.status("[bold]Installing yt-dlp plugin (pip)...[/bold]"):
        result = eng.install_pot_provider()
    if not result["ok"]:
        log_error(f"pip install failed:\n{result['output'][-800:]}")
        raise typer.Exit(code=1)
    log_success("Plugin installed.")

    if not yes:
        if not Confirm.ask(
            "Download and set up the bgutil token server (requires git + Deno)?"
        ):
            console.print("[yellow]Skipping server setup. Plugin alone is not enough.[/yellow]")
            raise typer.Exit(code=1)

    with console.status("[bold]Setting up token server (git clone + deno install)...[/bold]"):
        result = eng.setup_pot_server()
    if not result["ok"]:
        log_error(f"Server setup failed:\n{result['output'][-800:]}")
        raise typer.Exit(code=1)
    console.print(result["output"])

    if eng.pot_provider_available():
        log_success("PO token provider is ready. YouTube downloads will work now.")
    else:
        log_error(
            "Provider not detected after setup. Restart the terminal and re-run pot-setup."
        )


def _offer_pot_setup() -> bool:
    """Offer to install the POT provider and retry once. Returns True if retry succeeded."""
    eng = _get_engine()
    if eng.pot_provider_available():
        return False
    console.print(
        "\n[yellow]YouTube blocked this download (HTTP 403 / SABR experiment).[/yellow]"
    )
    console.print(
        "[dim]Fix: install the PO token provider (auto-fetches tokens via Deno).[/dim]"
    )
    if not Confirm.ask("Install the YouTube PO token provider now?"):
        return False
    result = eng.install_pot_provider()
    if not result["ok"]:
        log_error(f"pip install failed:\n{result['output'][-800:]}")
        return False
    result = eng.setup_pot_server()
    if not result["ok"]:
        log_error(f"Server setup failed:\n{result['output'][-800:]}")
        return False
    console.print(result["output"])
    if not eng.pot_provider_available():
        log_error("Provider still not detected. Re-run `max grab pot-setup`.")
        return False
    log_success("Provider installed. Retrying download...")
    return True


@app.command("queue")
def show_queue(
    process: bool = typer.Option(
        False, "--process", "-p", help="Process pending downloads."
    ),
):
    """Show the current download queue."""
    from max_cli.core.engines.task_queue import TaskStatus, TaskType

    manager = _get_task_manager()
    items = [task for task in manager.get_all() if task.type == TaskType.DOWNLOAD]
    stats = _download_stats()

    console.print("\n[bold]Queue Status:[/bold]")
    console.print(
        f"  Pending: {stats['pending']} | Downloading: {stats['running']} | Paused: {stats['paused']}\n"
    )

    if process:
        console.print("[dim]Processing queue...[/dim]")
        pending_ids = [t.id for t in items if t.status == TaskStatus.PENDING]
        _process_downloads()
        _print_outcome(pending_ids)
        return

    if not items:
        console.print("[dim]Queue is empty.[/dim]")
        return

    table = Table(title="Download Queue", box=box.ROUNDED)
    table.add_column("ID", style="cyan", width=8)
    table.add_column("Status", width=12)
    table.add_column("URL", width=50)
    table.add_column("Progress", justify="right", width=25)
    table.add_column("Type", width=8)

    for task in items:
        status_color = {
            TaskStatus.PENDING: "yellow",
            TaskStatus.RUNNING: "cyan",
            TaskStatus.PAUSED: "blue",
        }.get(task.status, "white")
        progress = f"{task.progress:.0f}%" if task.status == TaskStatus.RUNNING else "-"
        table.add_row(
            task.id,
            f"[{status_color}]{task.status.value}[/{status_color}]",
            task.payload.get("url", ""),
            progress,
            "Audio" if task.payload.get("audio_only") else "Video",
        )

    console.print(table)


@app.command("clear")
def clear_queue(
    all: bool = typer.Option(
        False, "--all", "-a", help="Clear all queued downloads, not only pending."
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation."),
):
    """Clear the download queue."""
    from max_cli.core.engines.task_queue import TaskStatus, TaskType

    manager = _get_task_manager()
    if all:
        if not force:
            if not Confirm.ask("[red]Clear ALL queued downloads?[/red]"):
                console.print("[yellow]Aborted.[/yellow]")
                return
        count = manager.clear(task_type=TaskType.DOWNLOAD)
        log_success(f"Cleared {count} items from queue.")
        return

    pending = manager.get_pending(task_type=TaskType.DOWNLOAD)
    if not pending:
        console.print("[dim]No pending items to clear.[/dim]")
        return

    if not force:
        if not Confirm.ask(f"[yellow]Clear {len(pending)} pending items?[/yellow]"):
            console.print("[yellow]Aborted.[/yellow]")
            return

    count = manager.clear(status=TaskStatus.PENDING, task_type=TaskType.DOWNLOAD)
    log_success(f"Cleared {count} pending items.")


@app.command("status")
def queue_status():
    """Show detailed queue statistics."""
    from max_cli.core.engines.download_history import DownloadHistory

    stats = _download_stats()
    history_stats = DownloadHistory(_get_task_manager()).get_stats()

    table = Table(title="Queue Statistics", box=box.ROUNDED)
    table.add_column("Status", style="cyan")
    table.add_column("Count", justify="right", style="bold")

    table.add_row("Queued", str(stats["total"]))
    table.add_row("Pending", str(stats["pending"]))
    table.add_row("Downloading", str(stats["running"]))
    table.add_row("Completed", f"[green]{history_stats['completed']}[/green]")
    table.add_row("Failed", f"[red]{history_stats['failed']}[/red]")

    console.print(table)


@app.command("history")
def show_history(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of items to show."),
    clear: bool = typer.Option(False, "--clear", "-c", help="Clear history."),
    force: bool = typer.Option(
        False, "-f", "--force", help="Clear without asking for confirmation."
    ),
):
    """Show download history."""
    from max_cli.core.engines.task_queue import TaskType

    manager = _get_task_manager()
    if clear:
        if not force and not Confirm.ask("Clear your whole download history?"):
            console.print("[yellow]Aborted.[/yellow]")
            return
        count = manager.clear_history(task_type=TaskType.DOWNLOAD)
        log_success(f"Cleared {count} items from history.")
        return

    history = manager.get_history(limit=limit, task_type=TaskType.DOWNLOAD)

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

    for task in history:
        file_size = int(task.result.get("file_size") or 0)
        date = "-"
        if task.completed_at:
            try:
                date = datetime.fromisoformat(task.completed_at).strftime(
                    "%Y-%m-%d %H:%M"
                )
            except ValueError:
                date = task.completed_at[:16]

        table.add_row(
            task.title or task.payload.get("url", ""),
            format_size(file_size) if file_size > 0 else "-",
            "Audio" if task.payload.get("audio_only") else "Video",
            str(task.payload.get("quality", "-")).upper(),
            date,
        )

    console.print(table)


if __name__ == "__main__":
    app()
