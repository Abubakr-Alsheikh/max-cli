import typer
from pathlib import Path
from typing import Optional, List

from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn

from max_cli.common.events import EventType, get_emitter
from max_cli.common.logger import console, log_error, log_success
from max_cli.common.utils import format_size

app = typer.Typer()


def _get_engine():
    try:
        from max_cli.core.engines.media_engine import MediaEngine

        return MediaEngine(auto_resolve=True)
    except RuntimeError as e:
        log_error(str(e))
        raise typer.Exit(1)


@app.command("compress")
@app.command("c", hidden=True)
def compress_video(
    target: Path = typer.Argument(..., help="Video file to compress."),
    output: Optional[Path] = typer.Option(None, "-o", help="Output path."),
    level: str = typer.Option(
        "balanced", help="Quality: high, balanced, max (smaller size)."
    ),
    queue: bool = typer.Option(False, "--queue", "-q", help="Add to background queue"),
):
    """
    Compress video files to H.264 MP4.
    """
    _get_engine()

    crf_map = {
        "high": 23,
        "balanced": 28,
        "max": 35,
    }

    if queue:
        from max_cli.core.engines.daemon_manager import DaemonManager
        from max_cli.core.engines.task_queue import TaskItem, TaskType

        dm = DaemonManager()
        if not output:
            output = target.parent / f"{target.stem}_compressed.mp4"
        task = TaskItem(
            type=TaskType.VIDEO_COMPRESS,
            title=f"Compress {target.name}",
            description=f"CRF={crf_map.get(level.lower(), 28)}, preset=medium",
            payload={
                "input_path": str(target),
                "output_path": str(output),
                "crf": crf_map.get(level.lower(), 28),
                "preset": "medium",
            },
        )
        dm.add(task)
        console.print(f"[green]Queued:[/green] {target.name} (ID: {task.id})")
        console.print("[dim]Run 'max queue status' to monitor.[/dim]")
        return

    if not output:
        output = target.parent / f"{target.stem}_compressed.mp4"

    crf = crf_map.get(level.lower(), 28)

    console.print(
        f"[cyan]Compressing video (Level: {level})... This may take time.[/cyan]"
    )

    with console.status("[bold green]Encoding... (CPU working hard)[/bold green]"):
        try:
            eng = _get_engine()
            eng.compress_video(target, output, crf=crf)

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
@app.command("cv", hidden=True)
def convert_format(
    target: Path = typer.Argument(..., help="Input video file."),
    fmt: str = typer.Option(
        "mp4", "--format", "-f", help="Target format (mp4, mkv, avi)."
    ),
):
    """
    Convert video containers (e.g., MKV -> MP4).
    """
    _get_engine()

    output = target.parent / f"{target.stem}.{fmt}"

    console.print(f"[cyan]Converting {target.suffix} -> .{fmt}...[/cyan]")

    try:
        eng = _get_engine()
        eng.convert_format(target, output)
        log_success(f"Converted file: {output}")
    except Exception as e:
        log_error(f"Conversion failed: {e}")


@app.command("to-audio")
@app.command("rip", hidden=True)
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
    _get_engine()

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
            eng = _get_engine()
            eng.extract_audio(target, output, bitrate=bitrate)

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
    _get_engine()

    if not output:
        output = target.parent / f"{target.stem}.gif"

    console.print(f"[cyan]Generating GIF (FPS={fps}, Width={width})...[/cyan]")

    with console.status("[bold green]Rendering palette & GIF...[/bold green]"):
        try:
            eng = _get_engine()
            eng.video_to_gif(target, output, fps, width)
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
    Trim a video file. Provide --end OR --duration, or neither to cut to end of file.
    """
    _get_engine()
    audio_extensions = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"}
    is_audio = target.suffix.lower() in audio_extensions

    if not output:
        output = (
            target.parent / f"{target.stem}_cut.mp3"
            if is_audio
            else target.parent / f"{target.stem}_cut.mp4"
        )

    console.print(
        f"[cyan]Cutting {'audio' if is_audio else 'video'} from {start}...[/cyan]"
    )
    with console.status("[bold green]Processing cut...[/bold green]"):
        try:
            eng = _get_engine()
            eng.trim_video(target, output, start, end, duration)
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
    _get_engine()
    if not output:
        output = target.parent / f"{target.stem}_thumb.jpg"

    try:
        eng = _get_engine()
        eng.get_thumbnail(target, output, time)
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
    _get_engine()
    if not output:
        ext = target.suffix
        output = target.parent / f"{target.stem}_boosted{ext}"

    console.print(f"[cyan]Boosting volume by {db}dB...[/cyan]")

    # This is fast because we copy video stream and only re-encode audio
    with console.status("[bold green]Adjusting audio...[/bold green]"):
        try:
            eng = _get_engine()
            eng.adjust_volume(target, output, db)
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
    _get_engine()
    if not output:
        output = target.parent / f"{target.stem}_mute.mp4"

    console.print("[cyan]Removing audio track...[/cyan]")

    try:
        eng = _get_engine()
        eng.mute_video(target, output)
        log_success(f"Muted video saved: {output}")
    except Exception as e:
        log_error(f"Mute failed: {e}")


@app.command("concat")
def concat_videos(
    target: Path = typer.Argument(
        ...,
        help="Text file with video paths (one per line), or glob pattern (e.g., *.mp4).",
    ),
    output: Optional[Path] = typer.Option(None, "-o", help="Output file."),
    method: str = typer.Option(
        "fast", "--method", "-m", help="Method: fast (stream copy) or safe (re-encode)."
    ),
):
    """
    Concatenate multiple video files into one.

    Use a text file with 'file /path/to/video.mp4' lines, or a glob pattern.
    """
    _get_engine()

    input_files: List[Path] = []

    if "*" in target.name or "?" in target.name:
        parent = target.parent if target.parent != Path(".") else Path.cwd()
        pattern = target.name
        input_files = sorted(parent.glob(pattern))
        if not input_files:
            log_error(f"No files found matching pattern: {pattern}")
            raise typer.Exit(1)
    elif target.is_file() and target.suffix == ".txt":
        with open(target) as f:
            for line in f:
                line = line.strip()
                if line.startswith("file "):
                    line = line[5:].strip().strip("'\"")
                if line:
                    input_files.append(Path(line))
    else:
        log_error(
            "Provide either a .txt file with file paths or a glob pattern (e.g., *.mp4)"
        )
        raise typer.Exit(1)

    if not output:
        ext = input_files[0].suffix if input_files else ".mp4"
        output = target.parent / f"concatenated{ext}"

    console.print(f"[cyan]Concatenating {len(input_files)} videos...[/cyan]")
    console.print(f"[dim]Method: {method}[/dim]")

    with console.status("[bold green]Merging videos...[/bold green]"):
        try:
            concat_method = "concat" if method == "fast" else "filter"
            eng = _get_engine()
            eng.concatenate_videos(input_files, output, method=concat_method)
            log_success(f"Videos merged: {output}")
        except Exception as e:
            log_error(f"Concatenation failed: {e}")


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
    _get_engine()
    if not output:
        output = target.parent / f"{target.stem}_adjusted.mp4"

    console.print(
        f"[cyan]Adjusting brightness={brightness}, contrast={contrast}...[/cyan]"
    )

    with console.status("[bold green]Processing...[/bold green]"):
        try:
            eng = _get_engine()
            eng.adjust_brightness(target, output, brightness, contrast)
            log_success(f"Video saved: {output}")
        except Exception as e:
            log_error(f"Adjustment failed: {e}")


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
    _get_engine()
    if not output:
        output = target.parent / f"{target.stem}_{preset}.mp4"

    console.print(f"[cyan]Applying {preset} color preset...[/cyan]")

    with console.status("[bold green]Processing...[/bold green]"):
        try:
            eng = _get_engine()
            eng.apply_color_preset(target, output, preset)
            log_success(f"Video saved: {output}")
        except Exception as e:
            log_error(f"Color grading failed: {e}")


@app.command("stabilize")
def stabilize_cmd(
    target: Path = typer.Argument(..., help="Video file."),
    output: Optional[Path] = typer.Option(None, "-o", help="Output file."),
):
    """
    Stabilize shaky video footage.
    """
    _get_engine()
    if not output:
        output = target.parent / f"{target.stem}_stabilized.mp4"

    console.print("[cyan]Analyzing video motion...[/cyan]")

    with console.status(
        "[bold green]Stabilizing (this may take a while)...[/bold green]"
    ):
        try:
            eng = _get_engine()
            eng.stabilize_video(target, output)
            log_success(f"Stabilized video saved: {output}")
        except Exception as e:
            log_error(f"Stabilization failed: {e}")


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
    _get_engine()
    if not output:
        ext = target.suffix
        output = target.parent / f"{target.stem}_normalized{ext}"

    console.print(f"[cyan]Normalizing audio to {level} LUFS...[/cyan]")

    with console.status("[bold green]Processing...[/bold green]"):
        try:
            eng = _get_engine()
            eng.normalize_audio(target, output, level)
            log_success(f"Normalized audio saved: {output}")
        except Exception as e:
            log_error(f"Normalization failed: {e}")


@app.command("denoise")
@app.command("dn", hidden=True)
def denoise_audio_cmd(
    target: Path = typer.Argument(..., help="Video or audio file with background noise."),
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

    if not output:
        ext = target.suffix
        output = target.parent / f"{target.stem}_denoised{ext}"

    if mode != "auto":
        valid_strength_modes = {"mild", "medium", "aggressive"}
        if strength in valid_strength_modes:
            strength = "medium"

    if queue:
        from max_cli.core.engines.daemon_manager import DaemonManager
        from max_cli.core.engines.task_queue import TaskItem, TaskType

        dm = DaemonManager()
        task = TaskItem(
            type=TaskType.VIDEO_DENOISE,
            title=f"Denoise {target.name}",
            description=f"mode={mode}, strength={strength}",
            payload={
                "input_path": str(target),
                "output_path": str(output),
                "mode": mode,
                "strength": strength,
            },
        )
        dm.add(task)
        console.print(f"[green]Queued:[/green] {target.name} (ID: {task.id})")
        console.print("[dim]Run 'max queue status' to monitor.[/dim]")
        return

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
            eng = _get_engine()
            eng.denoise_audio(target, output, mode=mode, strength=strength)
            progress.update(task_id, completed=100, description="[green]Complete[/green]")

            final_size = output.stat().st_size
            log_success(f"Denoised audio saved: {output.name}")
            console.print(f"File Size: [green]{format_size(final_size)}[/green]")

        except Exception as e:
            log_error(f"Denoising failed: {e}")
        finally:
            emitter.unsubscribe(_on_progress)


@app.command("audio-convert")
def convert_audio_cmd(
    target: Path = typer.Argument(..., help="Audio or video file."),
    format: str = typer.Option(
        "mp3", "--format", "-f", help="Target format: mp3, aac, flac, wav, ogg."
    ),
    quality: str = typer.Option(
        "h", "--quality", "-q", help="Quality: s (128k), m (192k), h (320k)."
    ),
    output: Optional[Path] = typer.Option(None, "-o", help="Output file."),
):
    """
    Convert audio between formats (e.g., WAV to MP3).
    """
    _get_engine()

    bitrate_map = {"s": "128k", "m": "192k", "h": "320k"}
    bitrate = bitrate_map.get(quality.lower()[0], "192k")

    target_ext = f".{format.lower().lstrip('.')}"
    if not output:
        output = target.parent / f"{target.stem}{target_ext}"
    else:
        if output.suffix.lower() != target_ext:
            output = output.with_suffix(target_ext)

    console.print(f"[cyan]Converting to {format.upper()} ({bitrate})...[/cyan]")

    with console.status("[bold green]Converting audio...[/bold green]"):
        try:
            eng = _get_engine()
            eng.convert_audio(target, output, bitrate=bitrate)
            log_success(f"Audio converted: {output}")
        except Exception as e:
            log_error(f"Conversion failed: {e}")


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
    _get_engine()

    console.print("[cyan]Starting screen recording...[/cyan]")
    console.print("[yellow]Press Ctrl+C to stop[/yellow]")

    try:
        eng = _get_engine()
        eng.screen_record(output, duration=duration, fps=fps, audio=audio)
        log_success(f"Recording saved: {output}")
    except Exception as e:
        log_error(f"Recording failed: {e}")


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

    Example: max media stream video.mp4 -u rtmp://live.twitch.tv/app -b 6000k
    """
    _get_engine()

    if not target.exists():
        log_error(f"File not found: {target}")
        raise typer.Exit(1)

    console.print(f"[cyan]Streaming to {rtmp_url}...[/cyan]")
    console.print("[yellow]Press Ctrl+C to stop streaming[/yellow]")

    try:
        eng = _get_engine()
        eng.stream_to_rtmp(target, rtmp_url, bitrate=bitrate, preset=preset)
        log_success("Streaming completed")
    except Exception as e:
        log_error(f"Streaming failed: {e}")


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
    _get_engine()

    if not target.exists():
        log_error(f"File not found: {target}")
        raise typer.Exit(1)

    console.print(f"[cyan]Starting live preview on port {port}...[/cyan]")
    console.print(f"[yellow]Open http://localhost:{port}/live.m3u8 to view[/yellow]")
    console.print("[dim]Press Ctrl+C to stop[/dim]")

    try:
        eng = _get_engine()
        eng.live_preview(target, port=port, bitrate=bitrate)
    except Exception as e:
        log_error(f"Preview failed: {e}")
