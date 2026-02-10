import typer
from pathlib import Path
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
    # Smart Quality Control
    quality: str = typer.Option(
        "h",
        "--quality",
        "-q",
        help="Quality Preset: [s]mall, [m]edium, [h]igh (default), [x]best.",
    ),
    # Mode Switches
    audio: bool = typer.Option(
        False, "--audio", "-a", help="Download audio only (MP3)."
    ),
    # Output Control
    output: Path = typer.Option(Path("."), "--output", "-o", help="Output folder."),
    # Advanced Overrides (Optional)
    ext: str = typer.Option("mp4", "--ext", help="Video container (mp4, mkv)."),
):
    """
    Download media with Smart Quality Presets.

    [bold]Quality Guide:[/bold]
    [green]s (Small)[/green]:  480p Video / 64k Audio  (Great for data saving / speech)
    [green]m (Medium)[/green]: 720p Video / 128k Audio (Standard Web Quality)
    [green]h (High)[/green]:   1080p Video / 192k Audio (HD - Default)
    [green]x (Xtreme)[/green]: 4K Video    / 320k Audio (Best possible quality)
    """

    if not output.exists():
        output.mkdir(parents=True, exist_ok=True)

    # UI Feedback
    q_map = {"s": "Small", "m": "Medium", "h": "High", "x": "Best"}
    q_label = q_map.get(quality.lower()[0], "Custom")

    console.print(f"[cyan]Grabbing ({q_label} Quality)...[/cyan]")
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
                video_format=ext,
                progress_hook=rich_hook,
            )
            log_success(f"Saved to [bold]{output}[/bold]")

        except Exception as e:
            log_error(str(e))
