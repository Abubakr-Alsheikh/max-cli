"""`max video`: parses options, calls `core/operations/video.py`, prints the result.

Each command's options must match its catalog entry in
`core/catalog/groups/video.py`; `tests/test_catalog_drift.py` checks them.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

import typer
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn

from max_cli.common.events import EventType, get_emitter
from max_cli.common.exceptions import ResourceNotFoundError, ValidationError
from max_cli.common.logger import console, log_error, log_success
from max_cli.common.utils import format_size
from max_cli.core.operations import video as video_ops
from max_cli.core.presets import (
    DEFAULT_AUDIO_CONVERT_QUALITY,
    DEFAULT_CONCAT_METHOD,
    DEFAULT_VIDEO_LEVEL,
    DEFAULT_VIDEO_TO_AUDIO_QUALITY,
)

if TYPE_CHECKING:
    from max_cli.core.operations.result import ActionResult

app = typer.Typer()


def _get_engine():
    try:
        from max_cli.core.engines.media_engine import MediaEngine
        from max_cli.interface.ffmpeg_prompt import ffmpeg_prompt_callbacks

        return MediaEngine(auto_resolve=True, **ffmpeg_prompt_callbacks())
    except RuntimeError as e:
        log_error(str(e))
        raise typer.Exit(1) from None


def _run(
    operation: Callable[..., "ActionResult"],
    fail_message: str,
    status: Optional[str] = None,
    **kwargs: Any,
) -> Optional["ActionResult"]:
    """Call a video operation and report its errors.

    Bad input (a missing file, an unknown option) exits 1 before any work
    starts. Other failures print `fail_message` and return None.
    """
    engine = _get_engine()
    try:
        if status:
            with console.status(status):
                return operation(engine=engine, **kwargs)
        return operation(engine=engine, **kwargs)
    except (ResourceNotFoundError, ValidationError) as e:
        log_error(str(e))
        raise typer.Exit(1) from None
    except Exception as e:
        log_error(f"{fail_message}: {e}")
        return None


def _queue(action_name: str, **values: Any) -> None:
    from max_cli.core.catalog import get_action
    from max_cli.core.catalog.runner import enqueue_action

    try:
        task = enqueue_action(get_action(f"video.{action_name}"), values)
    except ValidationError as e:
        log_error(str(e))
        raise typer.Exit(1) from None
    console.print(f"[green]Queued:[/green] {values['target'].name} (ID: {task.id})")
    console.print("[dim]Run 'max queue status' to monitor.[/dim]")


def _report(result: Optional["ActionResult"]) -> None:
    if result:
        log_success(result.message)


@app.command("compress")
@app.command("c", hidden=True)
def compress_video(
    target: Path = typer.Argument(..., help="Video file to compress."),
    output: Optional[Path] = typer.Option(None, "-o", help="Output path."),
    level: str = typer.Option(
        DEFAULT_VIDEO_LEVEL, help="Quality: high, balanced, max (smaller size)."
    ),
    queue: bool = typer.Option(False, "--queue", "-q", help="Add to background queue"),
):
    """
    Compress video files to H.264 MP4.
    """
    _get_engine()
    if queue:
        _queue("compress", target=target, output=output, level=level)
        return

    console.print(
        f"[cyan]Compressing video (Level: {level})... This may take time.[/cyan]"
    )
    result = _run(
        video_ops.compress,
        "Compression failed",
        "[bold green]Encoding... (CPU working hard)[/bold green]",
        target=target,
        output=output,
        level=level,
    )
    if not result:
        return
    log_success(result.message)
    input_size = result.details["input_size"]
    output_size = result.details["output_size"]
    if input_size and output_size is not None:
        reduction = (input_size - output_size) / input_size * 100
        console.print(
            f"Size: {format_size(input_size)} -> "
            f"[bold green]{format_size(output_size)}[/bold green] (-{reduction:.1f}%)"
        )


@app.command("convert")
@app.command("cv", hidden=True)
def convert_format(
    target: Path = typer.Argument(..., help="Input video file."),
    format: str = typer.Option(
        "mp4", "--format", "-f", help="Target format (mp4, mkv, avi)."
    ),
):
    """
    Convert video containers (e.g., MKV -> MP4).
    """
    console.print(f"[cyan]Converting {target.suffix} -> .{format}...[/cyan]")
    _report(_run(video_ops.convert, "Conversion failed", target=target, format=format))


@app.command("to-audio")
@app.command("rip", hidden=True)
def video_to_audio(
    target: Path = typer.Argument(..., help="Source video file."),
    format: str = typer.Option(
        "mp3", "--format", "-f", help="Target audio format: mp3, wav, flac, aac."
    ),
    quality: str = typer.Option(
        DEFAULT_VIDEO_TO_AUDIO_QUALITY,
        "--quality",
        "-q",
        help="Quality: [s]mall (96k), [m]edium (128k), [h]igh (192k), [x]treme (320k).",
    ),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="Output path."),
):
    """
    Convert a video file into a standalone audio file.
    """
    console.print(f"[cyan]Converting video to {format.upper()}...[/cyan]")
    result = _run(
        video_ops.to_audio,
        "Conversion failed",
        "[bold green]Ripping audio track...[/bold green]",
        target=target,
        format=format,
        quality=quality,
        output=output,
    )
    if result:
        log_success(result.message)
        console.print(
            f"File Size: [green]{format_size(result.details['output_size'] or 0)}[/green]"
        )


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
    console.print(f"[cyan]Generating GIF (FPS={fps}, Width={width})...[/cyan]")
    _report(
        _run(
            video_ops.gif,
            "GIF creation failed",
            "[bold green]Rendering palette & GIF...[/bold green]",
            target=target,
            output=output,
            width=width,
            fps=fps,
        )
    )


@app.command("cut")
def cut_video(
    target: Path = typer.Argument(..., help="Video file."),
    start: str = typer.Option(
        ..., "--start", "-s", help="Start time (e.g. '00:01:00' or '60')."
    ),
    end: Optional[str] = typer.Option(None, "--end", "-e", help="End time."),
    duration: Optional[str] = typer.Option(
        None, "--duration", "-d", help="Duration to keep (e.g. '10')."
    ),
    output: Optional[Path] = typer.Option(None, "-o", help="Output file."),
):
    """
    Trim a video file. Provide --end OR --duration, or neither to cut to end of file.
    """
    console.print(f"[cyan]Cutting from {start}...[/cyan]")
    _report(
        _run(
            video_ops.cut,
            "Cut failed",
            "[bold green]Processing cut...[/bold green]",
            target=target,
            start=start,
            end=end,
            duration=duration,
            output=output,
        )
    )


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
    _report(
        _run(video_ops.snap, "Snapshot failed", target=target, time=time, output=output)
    )


@app.command("louder")
def boost_volume(
    target: Path = typer.Argument(..., help="Video/Audio file."),
    db: float = typer.Option(5.0, "--db", help="Decibels to add (e.g., 5 or 10)."),
    output: Optional[Path] = typer.Option(None, "-o", help="Output file."),
):
    """
    Increase volume (Useful for quiet recordings).
    """
    console.print(f"[cyan]Boosting volume by {db}dB...[/cyan]")
    _report(
        _run(
            video_ops.louder,
            "Volume adjustment failed",
            "[bold green]Adjusting audio...[/bold green]",
            target=target,
            db=db,
            output=output,
        )
    )


@app.command("mute")
def mute_track(
    target: Path = typer.Argument(..., help="Video file."),
    output: Optional[Path] = typer.Option(None, "-o", help="Output file."),
):
    """
    Remove audio track from video.
    """
    console.print("[cyan]Removing audio track...[/cyan]")
    _report(_run(video_ops.mute, "Mute failed", target=target, output=output))


@app.command("concat")
def concat_videos(
    target: Path = typer.Argument(
        ...,
        help="Text file with video paths (one per line), or glob pattern (e.g., *.mp4).",
    ),
    output: Optional[Path] = typer.Option(None, "-o", help="Output file."),
    method: str = typer.Option(
        DEFAULT_CONCAT_METHOD,
        "--method",
        "-m",
        help="Method: fast (stream copy) or safe (re-encode).",
    ),
):
    """
    Concatenate multiple video files into one.

    Use a text file with 'file /path/to/video.mp4' lines, or a glob pattern.
    """
    console.print(f"[dim]Method: {method}[/dim]")
    result = _run(
        video_ops.concat,
        "Concatenation failed",
        "[bold green]Merging videos...[/bold green]",
        target=target,
        output=output,
        method=method,
    )
    if result:
        console.print(
            f"[cyan]Concatenated {result.details['input_count']} videos.[/cyan]"
        )
        log_success(result.message)


@app.command("brightness")
def adjust_brightness_cmd(
    target: Path = typer.Argument(..., help="Video file."),
    brightness: float = typer.Option(
        1.0, "--brightness", "-b", help="Brightness: 0.0-2.0 (1.0 is normal)."
    ),
    contrast: float = typer.Option(
        1.0, "--contrast", "-c", help="Contrast: 0.0-2.0 (1.0 is normal)."
    ),
    output: Optional[Path] = typer.Option(None, "-o", help="Output file."),
):
    """
    Adjust video brightness and contrast.
    """
    console.print(
        f"[cyan]Adjusting brightness={brightness}, contrast={contrast}...[/cyan]"
    )
    _report(
        _run(
            video_ops.brightness,
            "Adjustment failed",
            "[bold green]Processing...[/bold green]",
            target=target,
            brightness=brightness,
            contrast=contrast,
            output=output,
        )
    )


@app.command("color")
def color_grade_cmd(
    target: Path = typer.Argument(..., help="Video file."),
    preset: str = typer.Option(
        "vivid",
        "--preset",
        "-p",
        help="Color preset: vivid, vintage, noir, warm, cool, fade.",
    ),
    output: Optional[Path] = typer.Option(None, "-o", help="Output file."),
):
    """
    Apply color grading presets to video.
    """
    console.print(f"[cyan]Applying {preset} color preset...[/cyan]")
    _report(
        _run(
            video_ops.color,
            "Color grading failed",
            "[bold green]Processing...[/bold green]",
            target=target,
            preset=preset,
            output=output,
        )
    )


@app.command("stabilize")
def stabilize_cmd(
    target: Path = typer.Argument(..., help="Video file."),
    output: Optional[Path] = typer.Option(None, "-o", help="Output file."),
):
    """
    Stabilize shaky video footage.
    """
    console.print("[cyan]Analyzing video motion...[/cyan]")
    _report(
        _run(
            video_ops.stabilize,
            "Stabilization failed",
            "[bold green]Stabilizing (this may take a while)...[/bold green]",
            target=target,
            output=output,
        )
    )


@app.command("normalize")
def normalize_audio_cmd(
    target: Path = typer.Argument(..., help="Audio or video file."),
    level: float = typer.Option(
        -20.0, "--level", "-l", help="Target loudness in LUFS (default: -20.0)."
    ),
    output: Optional[Path] = typer.Option(None, "-o", help="Output file."),
):
    """
    Normalize audio loudness to a target level.
    """
    console.print(f"[cyan]Normalizing audio to {level} LUFS...[/cyan]")
    _report(
        _run(
            video_ops.normalize,
            "Normalization failed",
            "[bold green]Processing...[/bold green]",
            target=target,
            level=level,
            output=output,
        )
    )


@app.command("denoise")
@app.command("dn", hidden=True)
def denoise_audio_cmd(
    target: Path = typer.Argument(
        ..., help="Video or audio file with background noise."
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
    queue: bool = typer.Option(False, "--queue", "-q", help="Add to background queue."),
):
    """
    Remove background noise from audio/video.

    Uses AI-powered filtering to clean up hiss, hum, fan noise, and ambient sounds.
    The --strength parameter only applies to 'auto' mode.

    Examples:
      max video denoise recording.mp4
      max video denoise podcast.mp4 --mode hiss --strength aggressive
      max video denoise lecture.mp4 --mode hum --output clean_lecture.mp4
    """
    _get_engine()
    if queue:
        _queue("denoise", target=target, mode=mode, strength=strength, output=output)
        return

    console.print(
        f"[cyan]Denoising audio (mode: {mode}, strength: {strength})...[/cyan]"
    )

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
        elif event.type == EventType.STATUS:
            progress.update(task_id, description=event.message)

    emitter.subscribe(_on_progress)
    try:
        with progress:
            result = _run(
                video_ops.denoise,
                "Denoising failed",
                target=target,
                mode=mode,
                strength=strength,
                output=output,
            )
            if result:
                progress.update(
                    task_id, completed=100, description="[green]Complete[/green]"
                )
    finally:
        emitter.unsubscribe(_on_progress)

    if result:
        log_success(result.message)
        console.print(
            f"File Size: [green]{format_size(result.details['output_size'] or 0)}[/green]"
        )


@app.command("audio-convert")
def convert_audio_cmd(
    target: Path = typer.Argument(..., help="Audio or video file."),
    format: str = typer.Option(
        "mp3", "--format", "-f", help="Target format: mp3, aac, flac, wav, ogg."
    ),
    quality: str = typer.Option(
        DEFAULT_AUDIO_CONVERT_QUALITY,
        "--quality",
        "-q",
        help="Quality: s (128k), m (192k), h (320k).",
    ),
    output: Optional[Path] = typer.Option(None, "-o", help="Output file."),
):
    """
    Convert audio between formats (e.g., WAV to MP3).
    """
    console.print(f"[cyan]Converting to {format.upper()}...[/cyan]")
    _report(
        _run(
            video_ops.audio_convert,
            "Conversion failed",
            "[bold green]Converting audio...[/bold green]",
            target=target,
            format=format,
            quality=quality,
            output=output,
        )
    )


@app.command("record")
def screen_record_cmd(
    output: Path = typer.Argument("screen recording.mp4", help="Output video file."),
    duration: Optional[int] = typer.Option(
        None, "--duration", "-d", help="Recording duration in seconds."
    ),
    fps: int = typer.Option(30, "--fps", help="Frames per second."),
    audio: bool = typer.Option(False, "--audio", "-a", help="Include system audio."),
):
    """
    Record screen (Windows/macOS/Linux).

    Press Ctrl+C to stop recording (if no duration specified).
    """
    console.print("[cyan]Starting screen recording...[/cyan]")
    console.print("[yellow]Press Ctrl+C to stop[/yellow]")
    _report(
        _run(
            video_ops.record,
            "Recording failed",
            output=output,
            duration=duration,
            fps=fps,
            audio=audio,
        )
    )


@app.command("stream")
def stream_video_cmd(
    target: Path = typer.Argument(..., help="Video file to stream."),
    rtmp_url: str = typer.Option(
        ..., "--url", "-u", help="RTMP server URL (e.g., rtmp://live.twitch.tv/app)."
    ),
    bitrate: str = typer.Option(
        "4500k", "--bitrate", "-b", help="Video bitrate (e.g., 4500k, 6000k)."
    ),
    preset: str = typer.Option(
        "veryfast", "--preset", "-p", help="Encoding preset: ultrafast to slow."
    ),
):
    """
    Stream video to an RTMP server (Twitch, YouTube, etc.).

    Example: max video stream video.mp4 -u rtmp://live.twitch.tv/app -b 6000k
    """
    console.print(f"[cyan]Streaming to {rtmp_url}...[/cyan]")
    console.print("[yellow]Press Ctrl+C to stop streaming[/yellow]")
    _report(
        _run(
            video_ops.stream,
            "Streaming failed",
            target=target,
            rtmp_url=rtmp_url,
            bitrate=bitrate,
            preset=preset,
        )
    )


@app.command("preview")
def live_preview_cmd(
    target: Path = typer.Argument(..., help="Video file to preview."),
    port: int = typer.Option(8080, "--port", "-p", help="HTTP server port."),
    bitrate: str = typer.Option(
        "2000k", "--bitrate", "-b", help="Transcoding bitrate."
    ),
):
    """
    Start HTTP server for live preview streaming via HLS.

    Open http://localhost:8080/live.m3u8 in a player to watch.
    """
    console.print(f"[cyan]Starting live preview on port {port}...[/cyan]")
    console.print(f"[yellow]Open http://localhost:{port}/live.m3u8 to view[/yellow]")
    console.print("[dim]Press Ctrl+C to stop[/dim]")
    _run(video_ops.preview, "Preview failed", target=target, port=port, bitrate=bitrate)
