"""`max video` operations: everything a video command does apart from parsing and printing.

The CLI, the dashboard and the agent all call these functions through the
catalog (`core/catalog/groups/video.py`). They never prompt or print. Pass
`engine` to reuse one that is already resolved (the CLI passes one that can
ask before downloading FFmpeg); otherwise each call builds its own.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

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
    SILENCE_MIN_SECONDS,
    SILENCE_PADDING_SECONDS,
    SILENCE_THRESHOLD_DB,
    VIDEO_TO_AUDIO_BITRATES,
    bitrate_for_quality,
    crf_for_level,
    sibling_path,
)

if TYPE_CHECKING:
    from max_cli.core.engines.ffmpeg_base import FFmpegEngine
    from max_cli.core.engines.media_engine import MediaEngine

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"}
# Under this much silence in all, cut-silence leaves the file alone.
SILENCE_WORTH_CUTTING_SECONDS = 0.5


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
    size: Optional[str] = None,
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    """Compress at a quality level, or to fit `size` ("25MB") when given."""
    _require_file(target)
    output = output or sibling_path(target, "_compressed", "mp4")
    if size:
        return _compress_to_size(target, output, _size_limit(size), _engine(engine))
    _engine(engine).compress_video(
        target, output, crf=crf_for_level(level), preset=DEFAULT_VIDEO_PRESET
    )
    return ActionResult(
        ok=True,
        message=f"Video saved: {output}",
        output_files=[output],
        details={"input_size": _file_size(target), "output_size": _file_size(output)},
    )


# --- compressing to a size ---------------------------------------------------

# The mp4 container and bitrate swings take a few percent: aim below the limit.
SIZE_HEADROOM = 0.95
# Below this the picture is a smear; Max says the size is too small instead.
MIN_VIDEO_KBPS = 50
# The sound's share of a budget: (whole budget in kbps at least, audio kbps).
AUDIO_KBPS_BY_BUDGET = ((1000, 128), (400, 96), (150, 64), (0, 32))
# Fewer pixels look better at a low bitrate: (video kbps below, height).
HEIGHT_BY_VIDEO_KBPS = ((600, 480), (1500, 720))
# A second try at a lower bitrate when the first comes out over the limit.
SIZE_RETRY_MARGIN = 0.97


@dataclass
class Bitrates:
    """How to spend a size budget on one video."""

    video_kbps: int
    audio_kbps: int
    height: Optional[int]  # scale down to this; None keeps the picture size


def _size_limit(size: str) -> int:
    from max_cli.common.utils import parse_size

    try:
        return parse_size(size)
    except ValueError as exc:
        raise ValidationError(str(exc)) from None


def plan_bitrates(
    limit_bytes: int, duration: float, has_audio: bool, height: Optional[int]
) -> Bitrates:
    """Bitrates whose total fills `limit_bytes` over `duration` seconds.

    Raises ValidationError when the size can't hold a watchable video.
    """
    from max_cli.common.utils import format_decimal_size

    budget_kbps = limit_bytes * 8 * SIZE_HEADROOM / duration / 1000
    audio_kbps = 0
    if has_audio:
        audio_kbps = next(
            kbps for floor, kbps in AUDIO_KBPS_BY_BUDGET if budget_kbps >= floor
        )
    video_kbps = int(budget_kbps - audio_kbps)
    if video_kbps < MIN_VIDEO_KBPS:
        smallest_audio = AUDIO_KBPS_BY_BUDGET[-1][1] if has_audio else 0
        smallest = (MIN_VIDEO_KBPS + smallest_audio) * 1000 * duration / 8
        raise ValidationError(
            f"{format_decimal_size(limit_bytes)} is too small for {duration:.0f} "
            f"seconds of video. Give at least "
            f"{format_decimal_size(smallest / SIZE_HEADROOM)}, "
            "or cut the video first."
        )
    height_cap = next(
        (cap for below, cap in HEIGHT_BY_VIDEO_KBPS if video_kbps < below), None
    )
    return Bitrates(
        video_kbps,
        audio_kbps,
        height_cap if height_cap and height and height > height_cap else None,
    )


def _compress_to_size(
    target: Path, output: Path, limit_bytes: int, media: "MediaEngine"
) -> ActionResult:
    from max_cli.common.utils import format_decimal_size

    input_size = target.stat().st_size
    limit_text = format_decimal_size(limit_bytes)
    if input_size <= limit_bytes:
        return ActionResult(
            True,
            f"{target.name} is {format_decimal_size(input_size)}, already under "
            f"{limit_text}: nothing to do.",
            details={"input_size": input_size, "output_size": None},
        )
    try:
        facts = facts_from_probe(target, input_size, media.probe_media(target))
    except RuntimeError as exc:
        raise ValidationError(f"Max couldn't read {target.name}: {exc}") from None
    if not facts.duration:
        raise ValidationError(f"Max couldn't tell how long {target.name} is.")
    plan = plan_bitrates(
        limit_bytes, facts.duration, bool(facts.audio_codec), facts.height
    )
    media.compress_to_bitrate(
        target, output, plan.video_kbps, plan.audio_kbps, plan.height
    )
    output_size = output.stat().st_size
    if output_size > limit_bytes:
        # Two-pass lands close, but a hard scene can push it over: shrink by
        # the miss and encode once more.
        plan.video_kbps = max(
            MIN_VIDEO_KBPS,
            int(plan.video_kbps * limit_bytes / output_size * SIZE_RETRY_MARGIN),
        )
        media.compress_to_bitrate(
            target, output, plan.video_kbps, plan.audio_kbps, plan.height
        )
        output_size = output.stat().st_size
    fits = output_size <= limit_bytes
    message = f"Video saved: {output}"
    if not fits:
        message += f" ({format_decimal_size(output_size)}, over {limit_text})"
    return ActionResult(
        ok=True,
        message=message,
        output_files=[output],
        details={
            "input_size": input_size,
            "output_size": output_size,
            "limit": limit_bytes,
            "fits": fits,
            "video_kbps": plan.video_kbps,
            "audio_kbps": plan.audio_kbps,
            "height": plan.height,
        },
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


def segments_to_keep(
    silences: list[tuple[float, Optional[float]]], duration: float, padding: float
) -> list[tuple[float, float]]:
    """The stretches of a `duration`-second file left after cutting the
    silences, each silence keeping `padding` seconds at both ends so words
    don't start or stop abruptly. Silence shorter than two paddings stays.
    """
    keep: list[tuple[float, float]] = []
    position = 0.0
    for start, end in silences:
        cut_from = start + padding if start > 0 else 0.0
        cut_to = duration if end is None or end >= duration else end - padding
        if cut_to <= cut_from:
            continue
        if cut_from > position:
            keep.append((position, cut_from))
        position = cut_to
    if position < duration:
        keep.append((position, duration))
    return keep


def cut_silence(
    target: Path,
    threshold: float = SILENCE_THRESHOLD_DB,
    min_silence: float = SILENCE_MIN_SECONDS,
    padding: float = SILENCE_PADDING_SECONDS,
    output: Optional[Path] = None,
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    """Remove the pauses from a recording: jump cuts for talks and lectures."""
    _require_file(target)
    if min_silence <= 0 or padding < 0:
        raise ValidationError("min_silence must be above 0, and padding 0 or more.")
    media = _engine(engine)
    try:
        facts = facts_from_probe(
            target, target.stat().st_size, media.probe_media(target)
        )
    except RuntimeError as exc:
        raise ValidationError(f"Max couldn't read {target.name}: {exc}") from None
    if not facts.duration or not facts.audio_codec:
        raise ValidationError(f"{target.name} has no sound to find pauses in.")
    silences = media.find_silences(target, threshold, min_silence)
    keep = segments_to_keep(silences, facts.duration, padding)
    kept_seconds = sum(end - start for start, end in keep)
    removed_seconds = facts.duration - kept_seconds
    details = {
        "pauses": len(silences),
        "original_seconds": round(facts.duration, 2),
        "removed_seconds": round(removed_seconds, 2),
    }
    if not keep:
        raise ValidationError(
            f"{target.name} is all silence at {threshold} dB. Try a lower "
            "threshold, such as -40."
        )
    if removed_seconds < SILENCE_WORTH_CUTTING_SECONDS:
        return ActionResult(
            True,
            f"No pauses of {min_silence:g} s or more in {target.name}: nothing to cut.",
            details=details,
        )
    output = output or sibling_path(target, "_nosilence")
    media.keep_segments(target, output, keep, has_video=bool(facts.video_codec))
    return ActionResult(
        True,
        f"Cut {len(silences)} pauses ({removed_seconds:.1f} s of "
        f"{facts.duration:.1f} s): {output}",
        [output],
        details,
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


# --- describing a file (the dashboard's Video page) --------------------------

NO_FFMPEG_NOTE = "FFmpeg isn't installed yet, so only the size is known."


@dataclass
class MediaFacts:
    """What a video or audio file holds, as ffprobe reports it."""

    path: Path
    size_bytes: int
    duration: Optional[float] = None  # seconds
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    video_codec: str = ""
    audio_codec: str = ""
    audio_channels: Optional[int] = None
    bitrate: Optional[int] = None  # bits per second, the whole file
    note: str = ""  # why some facts are missing


def _number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _frame_rate(rate: Any) -> Optional[float]:
    """ffprobe's "30000/1001" as 29.97."""
    text = str(rate or "")
    if "/" in text:
        top, _, bottom = text.partition("/")
        numerator, denominator = _number(top), _number(bottom)
        if numerator and denominator:
            return round(numerator / denominator, 2)
        return None
    return _number(text)


def facts_from_probe(path: Path, size_bytes: int, probe: dict[str, Any]) -> MediaFacts:
    """Pick the facts the page shows out of ffprobe's JSON."""
    streams = probe.get("streams") or []
    video: dict[str, Any] = next(
        (
            stream
            for stream in streams
            if stream.get("codec_type") == "video"
            # A cover picture in a music file is a one-frame "video" stream.
            and not (stream.get("disposition") or {}).get("attached_pic")
        ),
        {},
    )
    audio: dict[str, Any] = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"), {}
    )
    info = probe.get("format") or {}
    bitrate = _number(info.get("bit_rate"))
    channels = audio.get("channels")
    return MediaFacts(
        path=path,
        size_bytes=size_bytes,
        duration=_number(info.get("duration")),
        width=video.get("width"),
        height=video.get("height"),
        fps=_frame_rate(video.get("avg_frame_rate")) if video else None,
        video_codec=str(video.get("codec_name") or ""),
        audio_codec=str(audio.get("codec_name") or ""),
        audio_channels=int(channels) if isinstance(channels, int) else None,
        bitrate=int(bitrate) if bitrate else None,
    )


def describe(target: Path, *, engine: Optional["FFmpegEngine"] = None) -> MediaFacts:
    """A file's length, picture size, frame rate and codecs, for the Video page.

    Never downloads FFmpeg: without it, only the size comes back, with a note.
    """
    target = Path(target)
    _require_file(target)
    size = target.stat().st_size
    if engine is None:
        from max_cli.core.engines.ffmpeg_base import FFmpegEngine

        try:
            engine = FFmpegEngine(auto_resolve=False)
        except RuntimeError:
            return MediaFacts(path=target, size_bytes=size, note=NO_FFMPEG_NOTE)
    try:
        probe = engine.probe_media(target)
    except RuntimeError as exc:
        return MediaFacts(path=target, size_bytes=size, note=str(exc))
    return facts_from_probe(target, size, probe)
