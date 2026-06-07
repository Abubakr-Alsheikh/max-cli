import typer
from pathlib import Path
from typing import Optional, List
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn
from rich.table import Table

from max_cli.common.events import EventType, get_emitter
from max_cli.common.logger import console, log_error, log_success
from max_cli.common.utils import format_size

app = typer.Typer()


def _get_engine():
    from max_cli.core.engines.audio_metadata_engine import AudioMetadataEngine

    return AudioMetadataEngine()


def _get_media_engine():
    try:
        from max_cli.core.engines.media_engine import MediaEngine

        return MediaEngine(auto_resolve=True)
    except RuntimeError as e:
        log_error(str(e))
        raise typer.Exit(1)


@app.command("compress")
@app.command("c", hidden=True)
def compress_audio(
    target: Path = typer.Argument(..., help="Audio file to compress."),
    output: Optional[Path] = typer.Option(
        None, "-o", "--output", help="Output audio file path."
    ),
    quality: str = typer.Option(
        "h",
        "--quality",
        "-q",
        help="Quality: [s]mall (64k), [m]edium (96k), [h]igh (128k), [x]treme (192k).",
    ),
    mono: bool = typer.Option(
        False, "--mono", "-m", help="Convert to mono for maximum compression."
    ),
):
    """
    Compress an audio file by re-encoding to a lower bitrate.

    Great for shrinking large recordings (e.g., 80MB -> ~3MB for a 4-min file).
    Defaults to high-quality MP3 (128k) with stereo.
    Use --quality s and --mono for maximum space savings.
    """
    _get_media_engine()

    if not target.exists():
        log_error(f"File not found: {target}")
        raise typer.Exit(1)

    bitrate_map = {"s": "64k", "m": "96k", "h": "128k", "x": "192k"}
    bitrate = bitrate_map.get(quality.lower()[0], "128k")

    if not output:
        output = target.parent / f"{target.stem}_compressed.mp3"

    console.print(
        f"[cyan]Compressing audio ({bitrate}, {'mono' if mono else 'stereo'})...[/cyan]"
    )

    with console.status("[bold green]Encoding audio...[/bold green]"):
        try:
            media_eng = _get_media_engine()
            media_eng.compress_audio(
                target,
                output,
                bitrate=bitrate,
                channels=1 if mono else None,
            )

            orig_size = target.stat().st_size
            new_size = output.stat().st_size
            reduction = ((orig_size - new_size) / orig_size) * 100

            log_success(f"Audio compressed: {output}")
            console.print(
                f"Size: {format_size(orig_size)} -> [bold green]{format_size(new_size)}[/bold green] (-{reduction:.1f}%)"
            )

        except Exception as e:
            log_error(f"Compression failed: {e}")


@app.command("denoise")
@app.command("dn", hidden=True)
def denoise_audio_cmd(
    target: Path = typer.Argument(..., help="Audio file with background noise."),
    mode: str = typer.Option(
        "auto",
        "--mode",
        "-m",
        help="Denoise mode: auto (general), hiss (constant hiss), hum (low rumble), speech (RNNoise, best for voice).",
    ),
    strength: str = typer.Option(
        "medium",
        "--strength",
        "-s",
        help="Denoising strength: mild, medium, aggressive (auto mode only).",
    ),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="Output file."),
):
    """
    Remove background noise from audio.

    Uses AI-powered filtering to clean up hiss, hum, fan noise, and ambient sounds.
    The --strength parameter only applies to 'auto' mode.

    Examples:
      max audio denoise recording.mp3
      max audio denoise podcast.mp3 --mode hiss --strength aggressive
      max audio denoise lecture.mp3 --mode hum --output clean_lecture.mp3
    """
    _get_media_engine()

    if not output:
        ext = target.suffix
        output = target.parent / f"{target.stem}_denoised{ext}"

    if mode != "auto":
        valid_strength_modes = {"mild", "medium", "aggressive"}
        if strength in valid_strength_modes:
            strength = "medium"

    console.print(f"[cyan]Denoising audio (mode: {mode}, strength: {strength})...[/cyan]")

    emitter = get_emitter()
    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        TextColumn("{task.percentage:>3.0f}%"),
        TimeRemainingColumn(compact=True),
        transient=True,
    )

    task_id = progress.add_task("Removing background noise...", total=100)

    def _on_progress(event):
        if event.type == EventType.PROGRESS and event.file == target.name:
            progress.update(task_id, completed=event.percentage)

    emitter.subscribe(_on_progress)

    with progress:
        try:
            eng = _get_media_engine()
            eng.denoise_audio(target, output, mode=mode, strength=strength)
            progress.update(task_id, completed=100, description="[green]Complete[/green]")

            final_size = output.stat().st_size
            log_success(f"Denoised audio saved: {output.name}")
            console.print(f"File Size: [green]{format_size(final_size)}[/green]")

        except Exception as e:
            log_error(f"Denoising failed: {e}")
        finally:
            emitter.unsubscribe(_on_progress)


@app.command("get")
@app.command("g", hidden=True)
def get_metadata(
    target: Path = typer.Argument(..., help="Audio file to read metadata from."),
):
    """
    Display all metadata from an audio file (title, artist, album, genre, etc.).
    """
    try:
        from rich.text import Text

        eng = _get_engine()
        metadata = eng.get_metadata(target)

        table = Table(title=f"Metadata: {target.name}", show_header=False)
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")

        for key, value in metadata.items():
            table.add_row(key, Text(str(value)))

        console.print(table)

    except Exception as e:
        log_error(f"Failed to read metadata: {e}")


@app.command("set")
@app.command("s", hidden=True)
def set_metadata(
    target: Path = typer.Argument(..., help="Audio file to modify."),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Song title."),
    artist: Optional[str] = typer.Option(None, "--artist", "-a", help="Artist name."),
    album: Optional[str] = typer.Option(None, "--album", "-b", help="Album name."),
    albumartist: Optional[str] = typer.Option(
        None, "--album-artist", help="Album artist name."
    ),
    genre: Optional[str] = typer.Option(None, "--genre", "-g", help="Genre."),
    date: Optional[str] = typer.Option(
        None, "--date", "-d", help="Release date (YYYY-MM-DD)."
    ),
    tracknumber: Optional[str] = typer.Option(
        None, "--track", "-n", help="Track number."
    ),
    discnumber: Optional[str] = typer.Option(None, "--disc", help="Disc number."),
    composer: Optional[str] = typer.Option(None, "--composer", help="Composer name."),
    comment: Optional[str] = typer.Option(
        None, "--comment", "-c", help="Comment/description."
    ),
    output: Optional[Path] = typer.Option(
        None, "-o", "--output", help="Output file (default: overwrite)."
    ),
):
    """
    Set metadata on an audio file. Use flags to set specific fields.
    """
    if not any(
        [
            title,
            artist,
            album,
            albumartist,
            genre,
            date,
            tracknumber,
            discnumber,
            composer,
            comment,
        ]
    ):
        console.print(
            "[yellow]No metadata fields specified. Use --help to see available options.[/yellow]"
        )
        return

    try:
        eng = _get_engine()
        result = eng.set_metadata(
            target,
            output,
            title=title,
            artist=artist,
            album=album,
            albumartist=albumartist,
            genre=genre,
            date=date,
            tracknumber=tracknumber,
            discnumber=discnumber,
            composer=composer,
            comment=comment,
        )
        log_success(f"Metadata saved: {result}")

    except Exception as e:
        log_error(f"Failed to set metadata: {e}")


@app.command("clear")
@app.command("cl", hidden=True)
def clear_metadata(
    target: Path = typer.Argument(..., help="Audio file to clear metadata from."),
    keep_duration: bool = typer.Option(
        True, "--keep-duration/--no-duration", help="Preserve audio info."
    ),
    output: Optional[Path] = typer.Option(
        None, "-o", "--output", help="Output file (default: overwrite)."
    ),
):
    """
    Remove all metadata from an audio file.
    """
    try:
        eng = _get_engine()
        result = eng.clear_metadata(target, output, keep_duration=keep_duration)
        log_success(f"Cleared metadata: {result}")

    except Exception as e:
        log_error(f"Failed to clear metadata: {e}")


@app.command("batch")
@app.command("b", hidden=True)
def batch_set_metadata(
    targets: List[Path] = typer.Argument(
        ..., help="Audio files to update (supports glob patterns)."
    ),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Song title."),
    artist: Optional[str] = typer.Option(None, "--artist", "-a", help="Artist name."),
    album: Optional[str] = typer.Option(None, "--album", "-b", help="Album name."),
    albumartist: Optional[str] = typer.Option(
        None, "--album-artist", help="Album artist name."
    ),
    genre: Optional[str] = typer.Option(None, "--genre", "-g", help="Genre."),
    date: Optional[str] = typer.Option(
        None, "--date", "-d", help="Release date (YYYY-MM-DD)."
    ),
    tracknumber: Optional[str] = typer.Option(
        None, "--track", "-n", help="Track number (auto-increment with --start)."
    ),
    start: Optional[int] = typer.Option(
        None, "--start", help="Starting track number for auto-increment."
    ),
):
    """
    Set the same metadata on multiple audio files at once.
    Useful for organizing files into an album or artist.
    """
    if not targets:
        log_error("No files provided.")
        return

    if not any([title, artist, album, albumartist, genre, date, tracknumber]):
        console.print(
            "[yellow]No metadata fields specified. Use --help to see available options.[/yellow]"
        )
        return

    count = 0
    current_track = start if start else 0

    for target in targets:
        try:
            track = str(current_track) if tracknumber or start else None

            eng = _get_engine()
            eng.set_metadata(
                target,
                title=title,
                artist=artist,
                album=album,
                albumartist=albumartist,
                genre=genre,
                date=date,
                tracknumber=track,
            )
            count += 1

            if start:
                current_track += 1

        except Exception as e:
            console.print(f"[red]Failed on {target.name}: {e}[/red]")

    log_success(f"Updated {count} files successfully.")


@app.command("organize")
@app.command("org", hidden=True)
def organize_files(
    targets: List[Path] = typer.Argument(
        ..., help="Audio files to organize (supports glob patterns)."
    ),
    output: Path = typer.Option(
        None, "-o", "--output", help="Target directory (default: same as source)."
    ),
    pattern: str = typer.Option(
        "artist",
        "--pattern",
        "-p",
        help="Folder structure: artist, album, genre, artist-album, contributing-artists.",
    ),
    filter_value: str = typer.Option(
        "",
        "--filter",
        "-f",
        help="Only organize files matching this folder name (e.g. --filter 'Electronic Gems').",
    ),
):
    """
    Organize audio files into folders by metadata.

    Default: Files are moved to folders named by artist.
    Example patterns:
      - artist:              Music/Artist Name/Song.mp3
      - album:               Music/Album Name/Song.mp3
      - genre:               Music/Rock/Song.mp3
      - artist-album:        Music/Artist Name/Album Name/Song.mp3
      - contributing-artists: Music/Contributing Artist/Song.mp3 (uses albumartist, falls back to artist)
    Use --filter to only process files matching a specific folder name (e.g. --filter 'Electronic Gems').
    """
    if not targets:
        log_error("No files provided.")
        return

    valid_patterns = [
        "artist",
        "album",
        "genre",
        "artist-album",
        "contributing-artists",
    ]
    if pattern not in valid_patterns:
        log_error(f"Invalid pattern. Use: {', '.join(valid_patterns)}")
        return

    target_dir = output if output else targets[0].parent

    console.print(f"[cyan]Organizing {len(targets)} files into {target_dir}...[/cyan]")

    from max_cli.common.transaction_log import TransactionLog

    txn = TransactionLog(command="audio organize")

    with console.status("[bold green]Organizing files...[/bold green]"):
        eng = _get_engine()
        eng_filter = filter_value if filter_value else None
        result = eng.organize(
            targets, target_dir, pattern, transaction_log=txn, filter_value=eng_filter
        )

    txn.save()

    if result["total_moved"]:
        console.print(f"[green]Moved {result['total_moved']} files:[/green]")
        for move in result["moved"][:5]:
            console.print(f"  [dim]{move}[/dim]")
        if len(result["moved"]) > 5:
            console.print(f"  [dim]...and {len(result['moved']) - 5} more[/dim]")

    if result["total_errors"]:
        console.print(f"[red]Errors ({result['total_errors']}):[/red]")
        for err in result["errors"][:5]:
            console.print(f"  [red]{err}[/red]")

    log_success(
        f"Done! Moved: {result['total_moved']}, Errors: {result['total_errors']}"
    )
    console.print("[dim]Undo with: max files undo[/dim]")
