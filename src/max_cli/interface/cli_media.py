import typer
from pathlib import Path
from typing import Optional

from max_cli.core.media_engine import MediaEngine
from max_cli.common.logger import console, log_error, log_success
from max_cli.common.utils import format_size

app = typer.Typer()

# Initialize engine (might raise error if ffmpeg missing)
try:
    engine = MediaEngine()
except RuntimeError:
    # If this module is imported but FFmpeg isn't there, we don't crash main.py
    # We just won't be able to run commands.
    engine: Optional[MediaEngine] = None


def _check_engine():
    if not engine:
        log_error("FFmpeg is not installed. Please install it to use media features.")
        log_error("Try: 'brew install ffmpeg' or 'sudo apt install ffmpeg'")
        raise typer.Exit(1)


@app.command("compress")
def compress_video(
    target: Path = typer.Argument(..., help="Video file to compress."),
    output: Optional[Path] = typer.Option(None, "-o", help="Output path."),
    level: str = typer.Option(
        "balanced", help="Quality: high, balanced, max (smaller size)."
    ),
):
    """
    Compress video files to H.264 MP4.
    """
    _check_engine()

    if not output:
        output = target.parent / f"{target.stem}_compressed.mp4"

    # Map friendly names to CRF values
    # CRF: Lower = Better Quality / Higher Size
    crf_map = {
        "high": 23,  # Default FFmpeg quality
        "balanced": 28,  # Good compression, decent quality
        "max": 35,  # Very small size, visible artifacts
    }

    crf = crf_map.get(level.lower(), 28)

    console.print(
        f"[cyan]Compressing video (Level: {level})... This may take time.[/cyan]"
    )

    # We use an indeterminate spinner because video encoding time varies wildly
    with console.status("[bold green]Encoding... (CPU working hard)[/bold green]"):
        try:
            engine.compress_video(target, output, crf=crf)

            orig_size = target.stat().st_size
            new_size = output.stat().st_size
            reduction = ((orig_size - new_size) / orig_size) * 100

            log_success(f"Video saved: {output}")
            console.print(
                f"Size: {format_size(orig_size)} -> [bold green]{format_size(new_size)}[/bold green] (-{reduction:.1f}%)"
            )

        except Exception as e:
            log_error(f"Compression failed: {e}")


@app.command("convert")
def convert_format(
    target: Path = typer.Argument(..., help="Input video file."),
    fmt: str = typer.Option(
        "mp4", "--format", "-f", help="Target format (mp4, mkv, avi)."
    ),
):
    """
    Convert video containers (e.g., MKV -> MP4).
    """
    _check_engine()

    output = target.parent / f"{target.stem}.{fmt}"

    console.print(f"[cyan]Converting {target.suffix} -> .{fmt}...[/cyan]")

    try:
        engine.convert_format(target, output)
        log_success(f"Converted file: {output}")
    except Exception as e:
        log_error(f"Conversion failed: {e}")


@app.command("to-audio")
def video_to_audio(
    target: Path = typer.Argument(..., help="Source video file."),
    format: str = typer.Option(
        "mp3", "--format", "-f", help="Target audio format: mp3, wav, flac, aac."
    ),
    quality: str = typer.Option(
        "h",
        "--quality",
        "-q",
        help="Quality: [s]mall (96k), [m]edium (128k), [h]igh (192k), [x]treme (320k).",
    ),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="Output path."),
):
    """
    Convert a video file into a standalone audio file.
    """
    _check_engine()

    if not target.exists():
        log_error(f"File not found: {target}")
        raise typer.Exit(1)

    # Resolve Bitrate
    bitrate_map = {"s": "96k", "m": "128k", "h": "192k", "x": "320k"}
    bitrate = bitrate_map.get(quality.lower()[0], "192k")

    # Resolve Output Path
    target_ext = f".{format.lower().lstrip('.')}"
    if not output:
        output = target.parent / f"{target.stem}{target_ext}"
    else:
        # Ensure the user-provided output has the right extension
        if output.suffix.lower() != target_ext:
            output = output.with_suffix(target_ext)

    console.print(f"[cyan]Converting video to {format.upper()} ({bitrate})...[/cyan]")

    with console.status("[bold green]Ripping audio track...[/bold green]"):
        try:
            engine.extract_audio(target, output, bitrate=bitrate)

            final_size = output.stat().st_size
            log_success(f"Audio extraction complete: [bold]{output.name}[/bold]")
            console.print(f"File Size: [green]{format_size(final_size)}[/green]")
        except Exception as e:
            log_error(f"Conversion failed: {e}")


@app.command("gif")
def create_gif(
    target: Path = typer.Argument(..., help="Input video."),
    output: Optional[Path] = typer.Option(None, "-o", help="Output GIF."),
    width: int = typer.Option(480, help="Width in pixels (Height auto-scaled)."),
    fps: int = typer.Option(15, help="Frames Per Second."),
):
    """
    Convert a video clip into a high-quality GIF.
    """
    _check_engine()

    if not output:
        output = target.parent / f"{target.stem}.gif"

    console.print(f"[cyan]Generating GIF (FPS={fps}, Width={width})...[/cyan]")

    with console.status("[bold green]Rendering palette & GIF...[/bold green]"):
        try:
            engine.video_to_gif(target, output, fps, width)
            log_success(f"GIF saved: {output}")
        except Exception as e:
            log_error(f"GIF creation failed: {e}")


@app.command("cut")
def cut_video(
    target: Path = typer.Argument(..., help="Video file."),
    start: str = typer.Option(
        ..., "--start", "-s", help="Start time (e.g. '00:01:00' or '60')."
    ),
    end: str = typer.Option(None, "--end", "-e", help="End time."),
    duration: str = typer.Option(
        None, "--duration", "-d", help="Duration to keep (e.g. '10')."
    ),
    output: Optional[Path] = typer.Option(None, "-o", help="Output file."),
):
    """
    Trim a video file. Provide --end OR --duration.
    """
    _check_engine()
    if not output:
        output = target.parent / f"{target.stem}_cut.mp4"

    if not end and not duration:
        log_error("You must provide either --end or --duration.")
        raise typer.Exit(1)

    console.print(f"[cyan]Cutting video from {start}...[/cyan]")
    with console.status("[bold green]Processing cut...[/bold green]"):
        try:
            engine.trim_video(target, output, start, end, duration)
            log_success(f"Clip saved: {output}")
        except Exception as e:
            log_error(f"Cut failed: {e}")


@app.command("snap")
def snapshot(
    target: Path = typer.Argument(..., help="Video file."),
    time: str = typer.Option(
        "00:00:05", "--time", "-t", help="Timestamp for screenshot."
    ),
    output: Optional[Path] = typer.Option(None, "-o", help="Output image."),
):
    """
    Take a high-quality JPG screenshot at a specific time.
    """
    _check_engine()
    if not output:
        output = target.parent / f"{target.stem}_thumb.jpg"

    try:
        engine.get_thumbnail(target, output, time)
        log_success(f"Thumbnail saved: {output}")
    except Exception as e:
        log_error(f"Snapshot failed: {e}")


@app.command("louder")
def boost_volume(
    target: Path = typer.Argument(..., help="Video/Audio file."),
    db: float = typer.Option(5.0, "--db", help="Decibels to add (e.g., 5 or 10)."),
    output: Optional[Path] = typer.Option(None, "-o", help="Output file."),
):
    """
    Increase volume (Useful for quiet recordings).
    """
    _check_engine()
    if not output:
        ext = target.suffix
        output = target.parent / f"{target.stem}_boosted{ext}"

    console.print(f"[cyan]Boosting volume by {db}dB...[/cyan]")

    # This is fast because we copy video stream and only re-encode audio
    with console.status("[bold green]Adjusting audio...[/bold green]"):
        try:
            engine.adjust_volume(target, output, db)
            log_success(f"Louder file saved: {output}")
        except Exception as e:
            log_error(f"Volume adjustment failed: {e}")


@app.command("mute")
def mute_track(
    target: Path = typer.Argument(..., help="Video file."),
    output: Optional[Path] = typer.Option(None, "-o", help="Output file."),
):
    """
    Remove audio track from video.
    """
    _check_engine()
    if not output:
        output = target.parent / f"{target.stem}_mute.mp4"

    console.print("[cyan]Removing audio track...[/cyan]")

    try:
        engine.mute_video(target, output)
        log_success(f"Muted video saved: {output}")
    except Exception as e:
        log_error(f"Mute failed: {e}")
