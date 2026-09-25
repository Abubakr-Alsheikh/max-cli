"""`max video` operations: everything a video command does apart from parsing and printing.

The CLI, the dashboard and the agent all call these functions through the
catalog (`core/catalog/groups/video.py`). They never prompt or print. Pass
`engine` to reuse one that is already resolved (the CLI passes one that can
ask before downloading FFmpeg); otherwise each call builds its own.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from max_cli.common.exceptions import ResourceNotFoundError, ValidationError
from max_cli.core.operations.result import ActionResult
from max_cli.core.presets import (
    AUDIO_CONVERT_BITRATES,
    CONCAT_METHODS,
    DEFAULT_AUDIO_CONVERT_QUALITY,
    DEFAULT_CONCAT_METHOD,
    DEFAULT_VIDEO_LEVEL,
    DEFAULT_VIDEO_PRESET,
    DEFAULT_VIDEO_TO_AUDIO_QUALITY,
    VIDEO_TO_AUDIO_BITRATES,
    bitrate_for_quality,
    crf_for_level,
    sibling_path,
)

if TYPE_CHECKING:
    from max_cli.core.engines.media_engine import MediaEngine

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"}


def _engine(engine: Optional["MediaEngine"]) -> "MediaEngine":
    if engine is not None:
        return engine
    from max_cli.core.engines.media_engine import MediaEngine

    return MediaEngine()


def _require_file(target: Path) -> None:
    if not target.exists():
        raise ResourceNotFoundError(f"File not found: {target}")


def _with_extension(output: Optional[Path], target: Path, fmt: str) -> Path:
    """`output` (or `target`'s sibling) with the extension for `fmt`."""
    extension = f".{fmt.lower().lstrip('.')}"
    if output is None:
        return target.parent / f"{target.stem}{extension}"
    if output.suffix.lower() != extension:
        return output.with_suffix(extension)
    return output


def _file_size(path: Path) -> Optional[int]:
    return path.stat().st_size if path.exists() else None


def compress(
    target: Path,
    output: Optional[Path] = None,
    level: str = DEFAULT_VIDEO_LEVEL,
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    _require_file(target)
    output = output or sibling_path(target, "_compressed", "mp4")
    _engine(engine).compress_video(
        target, output, crf=crf_for_level(level), preset=DEFAULT_VIDEO_PRESET
    )
    return ActionResult(
        ok=True,
        message=f"Video saved: {output}",
        output_files=[output],
        details={"input_size": _file_size(target), "output_size": _file_size(output)},
    )


def convert(
    target: Path, format: str = "mp4", *, engine: Optional["MediaEngine"] = None
) -> ActionResult:
    _require_file(target)
    output = target.parent / f"{target.stem}.{format}"
    _engine(engine).convert_format(target, output)
    return ActionResult(True, f"Converted file: {output}", [output])


def to_audio(
    target: Path,
    format: str = "mp3",
    quality: str = DEFAULT_VIDEO_TO_AUDIO_QUALITY,
    output: Optional[Path] = None,
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    _require_file(target)
    bitrate = bitrate_for_quality(
        VIDEO_TO_AUDIO_BITRATES, quality, DEFAULT_VIDEO_TO_AUDIO_QUALITY
    )
    output = _with_extension(output, target, format)
    _engine(engine).extract_audio(target, output, bitrate=bitrate)
    return ActionResult(
        True,
        f"Audio extraction complete: {output.name}",
        [output],
        {"bitrate": bitrate, "output_size": _file_size(output)},
    )


def gif(
    target: Path,
    output: Optional[Path] = None,
    width: int = 480,
    fps: int = 15,
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    _require_file(target)
    output = output or target.parent / f"{target.stem}.gif"
    _engine(engine).video_to_gif(target, output, fps, width)
    return ActionResult(True, f"GIF saved: {output}", [output])


def cut(
    target: Path,
    start: str,
    end: Optional[str] = None,
    duration: Optional[str] = None,
    output: Optional[Path] = None,
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    _require_file(target)
    extension = "mp3" if target.suffix.lower() in AUDIO_EXTENSIONS else "mp4"
    output = output or sibling_path(target, "_cut", extension)
    _engine(engine).trim_video(target, output, start, end, duration)
    return ActionResult(True, f"Clip saved: {output}", [output])


def snap(
    target: Path,
    time: str = "00:00:05",
    output: Optional[Path] = None,
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    _require_file(target)
    output = output or sibling_path(target, "_thumb", "jpg")
    _engine(engine).get_thumbnail(target, output, time)
    return ActionResult(True, f"Thumbnail saved: {output}", [output])


def louder(
    target: Path,
    db: float = 5.0,
    output: Optional[Path] = None,
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    _require_file(target)
    output = output or sibling_path(target, "_boosted")
    _engine(engine).adjust_volume(target, output, db)
    return ActionResult(True, f"Louder file saved: {output}", [output])


def mute(
    target: Path,
    output: Optional[Path] = None,
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    _require_file(target)
    output = output or sibling_path(target, "_mute", "mp4")
    _engine(engine).mute_video(target, output)
    return ActionResult(True, f"Muted video saved: {output}", [output])


def concat(
    target: Path,
    output: Optional[Path] = None,
    method: str = DEFAULT_CONCAT_METHOD,
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    if method not in CONCAT_METHODS:
        raise ValidationError(
            f"Unknown method '{method}'. Use one of: {', '.join(CONCAT_METHODS)}."
        )
    from max_cli.core.engines.video_engine import resolve_concat_inputs

    try:
        input_files = resolve_concat_inputs(target)
    except ValueError as e:
        raise ValidationError(str(e)) from None

    extension = input_files[0].suffix if input_files else ".mp4"
    output = output or target.parent / f"concatenated{extension}"
    _engine(engine).concatenate_videos(
        input_files, output, method=CONCAT_METHODS[method]
    )
    return ActionResult(
        True,
        f"Videos merged: {output}",
        [output],
        {"input_count": len(input_files)},
    )


def brightness(
    target: Path,
    brightness: float = 1.0,
    contrast: float = 1.0,
    output: Optional[Path] = None,
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    _require_file(target)
    output = output or sibling_path(target, "_adjusted", "mp4")
    _engine(engine).adjust_brightness(target, output, brightness, contrast)
    return ActionResult(True, f"Video saved: {output}", [output])


def color(
    target: Path,
    preset: str = "vivid",
    output: Optional[Path] = None,
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    _require_file(target)
    output = output or sibling_path(target, f"_{preset}", "mp4")
    _engine(engine).apply_color_preset(target, output, preset)
    return ActionResult(True, f"Video saved: {output}", [output])


def stabilize(
    target: Path,
    output: Optional[Path] = None,
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    _require_file(target)
    output = output or sibling_path(target, "_stabilized", "mp4")
    _engine(engine).stabilize_video(target, output)
    return ActionResult(True, f"Stabilized video saved: {output}", [output])


def normalize(
    target: Path,
    level: float = -20.0,
    output: Optional[Path] = None,
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    _require_file(target)
    output = output or sibling_path(target, "_normalized")
    _engine(engine).normalize_audio(target, output, level)
    return ActionResult(True, f"Normalized audio saved: {output}", [output])


def denoise(
    target: Path,
    mode: str = "auto",
    strength: str = "medium",
    output: Optional[Path] = None,
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    _require_file(target)
    output = output or sibling_path(target, "_denoised")
    if mode != "auto":
        # Strength only tunes the "auto" filter; the other modes ignore it.
        strength = "medium"
    _engine(engine).denoise_audio(target, output, mode=mode, strength=strength)
    return ActionResult(
        True,
        f"Denoised audio saved: {output.name}",
        [output],
        {"mode": mode, "strength": strength, "output_size": _file_size(output)},
    )


def audio_convert(
    target: Path,
    format: str = "mp3",
    quality: str = DEFAULT_AUDIO_CONVERT_QUALITY,
    output: Optional[Path] = None,
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    _require_file(target)
    bitrate = bitrate_for_quality(
        AUDIO_CONVERT_BITRATES, quality, DEFAULT_AUDIO_CONVERT_QUALITY
    )
    output = _with_extension(output, target, format)
    _engine(engine).convert_audio(target, output, bitrate=bitrate)
    return ActionResult(
        True, f"Audio converted: {output}", [output], {"bitrate": bitrate}
    )


def record(
    output: Path = Path("screen recording.mp4"),
    duration: Optional[int] = None,
    fps: int = 30,
    audio: bool = False,
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    _engine(engine).screen_record(output, duration=duration, fps=fps, audio=audio)
    return ActionResult(True, f"Recording saved: {output}", [output])


def stream(
    target: Path,
    rtmp_url: str,
    bitrate: str = "4500k",
    preset: str = "veryfast",
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    _require_file(target)
    _engine(engine).stream_to_rtmp(target, rtmp_url, bitrate=bitrate, preset=preset)
    return ActionResult(True, "Streaming completed")


def preview(
    target: Path,
    port: int = 8080,
    bitrate: str = "2000k",
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    _require_file(target)
    _engine(engine).live_preview(target, port=port, bitrate=bitrate)
    return ActionResult(True, "Preview stopped")
