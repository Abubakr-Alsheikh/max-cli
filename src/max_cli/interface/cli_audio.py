import typer
from pathlib import Path
from typing import Optional, List
from rich.table import Table

from max_cli.core.engines.audio_metadata_engine import AudioMetadataEngine
from max_cli.common.logger import console, log_error, log_success

app = typer.Typer()
engine = AudioMetadataEngine()


@app.command("get")
def get_metadata(
    target: Path = typer.Argument(..., help="Audio file to read metadata from."),
):
    """
    Display all metadata from an audio file (title, artist, album, genre, etc.).
    """
    try:
        metadata = engine.get_metadata(target)

        table = Table(title=f"Metadata: {target.name}", show_header=False)
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")

        for key, value in metadata.items():
            table.add_row(key, str(value))

        console.print(table)

    except Exception as e:
        log_error(f"Failed to read metadata: {e}")


@app.command("set")
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
        result = engine.set_metadata(
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
        result = engine.clear_metadata(target, output, keep_duration=keep_duration)
        log_success(f"Cleared metadata: {result}")

    except Exception as e:
        log_error(f"Failed to clear metadata: {e}")


@app.command("batch")
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

            engine.set_metadata(
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
