"""`max audio`: parse options, call `core/operations/audio.py`, print the result.

The options match the catalog (`core/catalog/groups/audio.py`);
`tests/test_catalog_drift.py` fails when they drift apart.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

import typer
from rich.markup import escape
from rich.table import Table

from max_cli.common.exceptions import ResourceNotFoundError, ValidationError
from max_cli.common.logger import console, log_error, log_success
from max_cli.common.utils import format_size
from max_cli.core.presets import (
    AUDIO_COMPRESS_BITRATES,
    DEFAULT_AUDIO_COMPRESS_QUALITY,
    DEFAULT_AUDIO_ORGANIZE_PATTERN,
    bitrate_for_quality,
)
from max_cli.interface.batch_cli import (
    QUEUE_OPTION,
    RECURSIVE_OPTION,
    REDO_OPTION,
    run_batch,
)

if TYPE_CHECKING:
    from max_cli.core.operations.result import ActionResult

app = typer.Typer()

MAX_LISTED_MOVES = 5
BITS_PER_KILOBIT = 1000
SECONDS_PER_MINUTE = 60


def _get_engine():
    from max_cli.core.engines.audio_metadata_engine import AudioMetadataEngine

    return AudioMetadataEngine()


def _get_media_engine():
    try:
        from max_cli.core.engines.media_engine import MediaEngine
        from max_cli.interface.ffmpeg_prompt import ffmpeg_prompt_callbacks

        return MediaEngine(auto_resolve=True, **ffmpeg_prompt_callbacks())
    except RuntimeError as e:
        log_error(str(e))
        raise typer.Exit(1) from None


def _run(
    operation: Callable[..., "ActionResult"], fail_message: str, **kwargs: Any
) -> Optional["ActionResult"]:
    """Call an audio operation and report its errors.

    Bad input (a missing file, no tags given) exits 1 before any work. Other
    failures print `fail_message` and return None; `max` still exits 1.
    """
    try:
        return operation(**kwargs)
    except (ResourceNotFoundError, ValidationError) as e:
        log_error(escape(str(e)))
        raise typer.Exit(1) from None
    except Exception as e:
        log_error(escape(f"{fail_message}: {e}"))
        return None


def _ops():
    from max_cli.core.operations import audio

    return audio


def _clock(seconds: float) -> str:
    minutes, secs = divmod(int(round(seconds)), SECONDS_PER_MINUTE)
    return f"{minutes}:{secs:02}"


@app.command("compress")
@app.command("c", hidden=True)
def compress_audio(
    target: list[Path] = typer.Argument(
        ..., help="Audio file to compress. Or several files, a folder, or a pattern."
    ),
    output: Optional[Path] = typer.Option(
        None, "-o", "--output", help="Output audio file path."
    ),
    quality: str = typer.Option(
        DEFAULT_AUDIO_COMPRESS_QUALITY,
        "--quality",
        "-q",
        help="Quality: [s]mall (64k), [m]edium (96k), [h]igh (128k), [x]treme (192k).",
    ),
    mono: bool = typer.Option(
        False, "--mono", "-m", help="Convert to mono for maximum compression."
    ),
    recursive: bool = RECURSIVE_OPTION,
    redo: bool = REDO_OPTION,
    queue: bool = QUEUE_OPTION,
):
    """
    Compress an audio file by re-encoding to a lower bitrate.

    Great for shrinking large recordings (e.g., 80MB -> ~3MB for a 4-min file).
    Defaults to high-quality MP3 (128k) with stereo.
    Use --quality s and --mono for maximum space savings.
    """
    if run_batch(
        "audio.compress",
        {"target": target, "output": output, "quality": quality, "mono": mono},
        queue=queue,
        recursive=recursive,
        redo=redo,
    ):
        return
    source = target[0]
    if not source.is_file():
        log_error(escape(f"File not found: {source}"))
        raise typer.Exit(1)
    bitrate = bitrate_for_quality(
        AUDIO_COMPRESS_BITRATES, quality, DEFAULT_AUDIO_COMPRESS_QUALITY
    )
    console.print(
        f"[cyan]Compressing audio ({bitrate}, {'mono' if mono else 'stereo'})...[/cyan]"
    )
    engine = _get_media_engine()
    with console.status("[bold green]Encoding audio...[/bold green]"):
        result = _run(
            _ops().compress,
            "Compression failed",
            target=source,
            output=output,
            quality=quality,
            mono=mono,
            engine=engine,
        )
    if result is None:
        return
    log_success(escape(result.message))
    before, after = result.details["input_size"], result.details["output_size"]
    if before and after is not None:
        reduction = (before - after) / before * 100
        console.print(
            f"Size: {format_size(before)} -> [bold green]{format_size(after)}[/bold green]"
            f" (-{reduction:.1f}%)"
        )


@app.command("denoise")
@app.command("dn", hidden=True)
def denoise_audio_cmd(
    target: list[Path] = typer.Argument(
        ...,
        help="Audio file with background noise. Or several files, a folder, or a pattern.",
    ),
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
    recursive: bool = RECURSIVE_OPTION,
    redo: bool = REDO_OPTION,
    queue: bool = QUEUE_OPTION,
):
    """
    Remove background noise from audio.

    Uses FFmpeg filters to clean up hiss, hum, fan noise, and ambient sounds.
    The --strength parameter only applies to 'auto' mode.

    Examples:
      max audio denoise recording.mp3
      max audio denoise podcast.mp3 --mode hiss --strength aggressive
      max audio denoise lecture.mp3 --mode hum --output clean_lecture.mp3
    """
    if run_batch(
        "audio.denoise",
        {"target": target, "mode": mode, "strength": strength, "output": output},
        queue=queue,
        recursive=recursive,
        redo=redo,
    ):
        return
    source = target[0]
    from max_cli.core.operations import video
    from max_cli.core.presets import DENOISE_MODES

    if not source.is_file():
        log_error(escape(f"File not found: {source}"))
        raise typer.Exit(1)
    if mode not in DENOISE_MODES:
        log_error(f"Unknown mode '{escape(mode)}'. Use: {', '.join(DENOISE_MODES)}.")
        raise typer.Exit(1)
    engine = _get_media_engine()
    console.print(
        f"[cyan]Denoising audio (mode: {mode}, strength: {strength})...[/cyan]"
    )
    with console.status("[bold green]Removing background noise...[/bold green]"):
        result = _run(
            video.denoise,
            "Denoising failed",
            target=source,
            mode=mode,
            strength=strength,
            output=output,
            engine=engine,
        )
    if result is None:
        return
    log_success(escape(result.message))
    size = result.details.get("output_size")
    if size is not None:
        console.print(f"File Size: [green]{format_size(size)}[/green]")


@app.command("get")
@app.command("g", hidden=True)
def get_metadata(
    target: Path = typer.Argument(..., help="Audio file to read metadata from."),
):
    """
    Display all metadata from an audio file (title, artist, album, genre, etc.).
    """
    from rich.text import Text

    result = _run(
        _ops().get, "Failed to read metadata", target=target, engine=_get_engine()
    )
    if result is None:
        return
    table = Table(title=f"Metadata: {escape(target.name)}", show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    for key, value in result.details["tags"].items():
        table.add_row(key, Text(str(value)))
    stream = result.details["stream"]
    if stream.get("duration") is not None:
        table.add_row("length", _clock(stream["duration"]))
    if stream.get("bitrate"):
        table.add_row("bitrate", f"{stream['bitrate'] // BITS_PER_KILOBIT} kbps")
    if stream.get("sample_rate"):
        table.add_row("sample rate", f"{stream['sample_rate']} Hz")
    if stream.get("channels"):
        table.add_row("channels", str(stream["channels"]))
    console.print(table)


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
        None, "--date", "-d", help="Release date (2024 or 2024-05-01)."
    ),
    tracknumber: Optional[str] = typer.Option(
        None, "--track", "-n", help="Track number (3, or 3/12)."
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
    result = _run(
        _ops().set_tags,
        "Failed to set metadata",
        target=target,
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
        output=output,
        engine=_get_engine(),
    )
    if result is not None:
        log_success(escape(result.message))


@app.command("clear")
@app.command("cl", hidden=True)
def clear_metadata(
    target: list[Path] = typer.Argument(
        ...,
        help="Audio file to clear metadata from. Or several files, a folder, or a pattern.",
    ),
    output: Optional[Path] = typer.Option(
        None, "-o", "--output", help="Output file (default: overwrite)."
    ),
    keep_duration: bool = typer.Option(
        True,
        "--keep-duration/--no-duration",
        hidden=True,
        help="Does nothing: clearing tags never changes the audio. Kept so old "
        "scripts still run.",
    ),
    recursive: bool = RECURSIVE_OPTION,
):
    """
    Remove all metadata from an audio file. The audio itself stays the same.
    """
    if run_batch(
        "audio.clear",
        {"target": target, "output": output},
        recursive=recursive,
    ):
        return
    source = target[0]
    result = _run(
        _ops().clear,
        "Failed to clear metadata",
        target=source,
        output=output,
        engine=_get_engine(),
    )
    if result is not None:
        log_success(escape(result.message))


@app.command("batch")
@app.command("b", hidden=True)
def batch_set_metadata(
    targets: list[Path] = typer.Argument(
        ..., help="Audio files, a folder of them, or a pattern such as *.mp3."
    ),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Song title."),
    artist: Optional[str] = typer.Option(None, "--artist", "-a", help="Artist name."),
    album: Optional[str] = typer.Option(None, "--album", "-b", help="Album name."),
    albumartist: Optional[str] = typer.Option(
        None, "--album-artist", help="Album artist name."
    ),
    genre: Optional[str] = typer.Option(None, "--genre", "-g", help="Genre."),
    date: Optional[str] = typer.Option(
        None, "--date", "-d", help="Release date (2024 or 2024-05-01)."
    ),
    tracknumber: Optional[str] = typer.Option(
        None,
        "--track",
        "-n",
        help="One track number for every file. To count up, use --start.",
    ),
    start: Optional[int] = typer.Option(
        None, "--start", help="Number the tracks in file order, starting here."
    ),
    discnumber: Optional[str] = typer.Option(None, "--disc", help="Disc number."),
    composer: Optional[str] = typer.Option(None, "--composer", help="Composer name."),
    comment: Optional[str] = typer.Option(
        None, "--comment", "-c", help="Comment/description."
    ),
):
    """
    Set the same metadata on multiple audio files at once.
    Useful for organizing files into an album or artist.
    """
    result = _run(
        _ops().batch,
        "Batch tagging failed",
        targets=targets,
        title=title,
        artist=artist,
        album=album,
        albumartist=albumartist,
        genre=genre,
        date=date,
        tracknumber=tracknumber,
        start=start,
        discnumber=discnumber,
        composer=composer,
        comment=comment,
        engine=_get_engine(),
    )
    if result is None:
        return
    for failure in result.details["failed"]:
        console.print(
            f"[red]Failed on {escape(failure['file'])}: {escape(failure['error'])}[/red]"
        )
    if result.ok:
        log_success(escape(result.message))
    else:
        log_error(escape(result.message))


@app.command("organize")
@app.command("org", hidden=True)
def organize_files(
    targets: list[Path] = typer.Argument(
        ..., help="Audio files, a folder of them, or a pattern such as *.mp3."
    ),
    output: Optional[Path] = typer.Option(
        None, "-o", "--output", help="Target directory (default: same as source)."
    ),
    pattern: str = typer.Option(
        DEFAULT_AUDIO_ORGANIZE_PATTERN,
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
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show where each file would go; move nothing."
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
    Use --dry-run to see the moves first.
    """
    with console.status("[bold green]Organizing files...[/bold green]"):
        result = _run(
            _ops().organize,
            "Organizing failed",
            targets=targets,
            output=output,
            pattern=pattern,
            filter_value=filter_value,
            dry_run=dry_run,
            engine=_get_engine(),
        )
    if result is None:
        return
    moves = result.details["moves"]
    if moves:
        heading = "Would move" if dry_run else "Moved"
        console.print(f"[green]{heading} {len(moves)} files:[/green]")
        for move in moves[:MAX_LISTED_MOVES]:
            console.print(f"  [dim]{escape(move)}[/dim]")
        if len(moves) > MAX_LISTED_MOVES:
            console.print(f"  [dim]...and {len(moves) - MAX_LISTED_MOVES} more[/dim]")
    errors = result.details["errors"]
    if errors:
        console.print(f"[red]Errors ({len(errors)}):[/red]")
        for error in errors[:MAX_LISTED_MOVES]:
            console.print(f"  [red]{escape(error)}[/red]")
    if dry_run:
        log_success(f"Dry run: nothing moved. Errors: {len(errors)}")
    else:
        log_success(f"Done! Moved: {len(moves)}, Errors: {len(errors)}")
    if result.undo_group:
        console.print("[dim]Undo with: max files undo[/dim]")
