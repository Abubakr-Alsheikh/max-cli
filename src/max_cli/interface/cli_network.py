import typer
from pathlib import Path
from typing import Optional
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn
)

from max_cli.core.network_engine import NetworkEngine
from max_cli.common.logger import console, log_success, log_error

app = typer.Typer()
engine = NetworkEngine()

@app.command("grab")
def download_media(
    url: str = typer.Argument(..., help="URL (YouTube, Twitch, Twitter, etc)."),
    
    # Audio Options
    audio: bool = typer.Option(False, "--audio", "-a", help="Extract audio only."),
    audio_fmt: str = typer.Option("mp3", "--audio-format", help="Audio format (mp3, m4a, wav)."),
    
    # Video Options
    res: str = typer.Option(None, "--res", "-r", help="Max resolution (e.g. 1080p, 720p). Default: Best available."),
    ext: str = typer.Option("mp4", "--ext", help="Video container (mp4, mkv)."),
    
    # General Options
    output: Path = typer.Option(Path("."), "--output", "-o", help="Output folder."),
):
    """
    Download media from the internet.
    Supports YouTube playlists, metadata embedding, and 4K video.
    """
    
    if not output.exists():
        output.mkdir(parents=True, exist_ok=True)

    mode = "Audio" if audio else "Video"
    console.print(f"[cyan]Initializing {mode} Download...[/cyan]")
    console.print(f"[dim]URL: {url}[/dim]")

    # Setup Rich Progress Bar
    # We use a custom layout: [Spinner] [Description] [Bar] [Size] [Speed] [Time]
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
        transient=True 
    )

    task_id = progress.add_task("Starting...", filename="Fetching info...", start=False)

    # Define the hook function that yt-dlp will call
    def rich_hook(d):
        if d['status'] == 'downloading':
            # Extract filename for UI
            filename = d.get('filename', '').split('/')[-1]
            # Remove extension for cleaner look, limit length
            filename = (filename[:30] + '...') if len(filename) > 30 else filename
            
            progress.update(
                task_id,
                total=d.get('total_bytes') or d.get('total_bytes_estimate'),
                completed=d.get('downloaded_bytes'),
                filename=filename,
                start=True # Start the timer
            )
        elif d['status'] == 'finished':
            progress.update(task_id, filename="Processing (Merging/Converting)...")

    # Run the download
    with progress:
        try:
            engine.download_media(
                url=url,
                output_path=output,
                audio_only=audio,
                audio_format=audio_fmt,
                video_format=ext,
                resolution=res,
                progress_hook=rich_hook
            )
            
            # Since the progress bar is transient (disappears on done), 
            # we print a success message manually.
            log_success(f"Download complete! Saved to [bold]{output}[/bold]")

        except Exception as e:
            log_error(str(e))
