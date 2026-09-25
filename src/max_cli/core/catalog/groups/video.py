"""Catalog entries for `max video`. `tests/test_catalog_drift.py` checks them against the CLI."""

from max_cli.core.catalog.spec import (
    CLI_ONLY,
    Action,
    Danger,
    Group,
    Param,
    ParamKind,
)
from max_cli.core.presets import (
    AUDIO_CONVERT_BITRATES,
    COLOR_PRESETS,
    CONCAT_METHODS,
    DEFAULT_AUDIO_CONVERT_QUALITY,
    DEFAULT_CONCAT_METHOD,
    DEFAULT_VIDEO_LEVEL,
    DEFAULT_VIDEO_TO_AUDIO_QUALITY,
    DENOISE_MODES,
    DENOISE_STRENGTHS,
    VIDEO_CRF_BY_LEVEL,
    VIDEO_TO_AUDIO_BITRATES,
)

OPS = "max_cli.core.operations.video"


def _target(help: str = "Video file.") -> Param:
    return Param("target", ParamKind.FILE, help)


def _output(help: str = "Output file. Default: next to the input.") -> Param:
    return Param("output", ParamKind.OUTPUT, help, default=None, cli=("-o",))


def _output_long(help: str = "Output file. Default: next to the input.") -> Param:
    return Param("output", ParamKind.OUTPUT, help, default=None, cli=("-o", "--output"))


GROUP = Group(
    name="video",
    summary="Video and audio tools powered by FFmpeg.",
    actions=(
        Action(
            group="video",
            name="compress",
            summary="Compress a video to H.264 MP4.",
            operation=f"{OPS}:compress",
            params=(
                _target("Video file to compress."),
                Param(
                    "output",
                    ParamKind.OUTPUT,
                    "Output path.",
                    default=None,
                    cli=("-o",),
                ),
                Param(
                    "level",
                    ParamKind.CHOICE,
                    "Quality: high, balanced, max (smaller size).",
                    default=DEFAULT_VIDEO_LEVEL,
                    choices=tuple(VIDEO_CRF_BY_LEVEL),
                    cli=("--level",),
                ),
            ),
            queueable=True,
        ),
        Action(
            group="video",
            name="convert",
            summary="Convert a video container, for example MKV to MP4.",
            operation=f"{OPS}:convert",
            params=(
                _target("Input video file."),
                Param(
                    "format",
                    ParamKind.TEXT,
                    "Target format (mp4, mkv, avi).",
                    default="mp4",
                    cli=("--format", "-f"),
                ),
            ),
        ),
        Action(
            group="video",
            name="to-audio",
            summary="Extract the audio track into its own file.",
            operation=f"{OPS}:to_audio",
            params=(
                _target("Source video file."),
                Param(
                    "format",
                    ParamKind.CHOICE,
                    "Target audio format.",
                    default="mp3",
                    choices=("mp3", "wav", "flac", "aac"),
                    cli=("--format", "-f"),
                ),
                Param(
                    "quality",
                    ParamKind.CHOICE,
                    "Bitrate: s (96k), m (128k), h (192k), x (320k).",
                    default=DEFAULT_VIDEO_TO_AUDIO_QUALITY,
                    choices=tuple(VIDEO_TO_AUDIO_BITRATES),
                    cli=("--quality", "-q"),
                ),
                _output_long("Output path."),
            ),
        ),
        Action(
            group="video",
            name="gif",
            summary="Turn a video clip into a GIF.",
            operation=f"{OPS}:gif",
            params=(
                _target("Input video."),
                _output("Output GIF."),
                Param(
                    "width",
                    ParamKind.INT,
                    "Width in pixels; height follows.",
                    default=480,
                    cli=("--width",),
                    advanced=True,
                ),
                Param(
                    "fps",
                    ParamKind.INT,
                    "Frames per second.",
                    default=15,
                    cli=("--fps",),
                    advanced=True,
                ),
            ),
        ),
        Action(
            group="video",
            name="cut",
            summary="Keep part of a video or audio file.",
            operation=f"{OPS}:cut",
            params=(
                _target("Video or audio file."),
                Param(
                    "start",
                    ParamKind.TEXT,
                    "Start time, e.g. 00:01:00 or 60.",
                    cli=("--start", "-s"),
                ),
                Param(
                    "end",
                    ParamKind.TEXT,
                    "End time. Leave empty to cut to the end.",
                    default=None,
                    cli=("--end", "-e"),
                ),
                Param(
                    "duration",
                    ParamKind.TEXT,
                    "Length to keep, e.g. 10. Use instead of the end time.",
                    default=None,
                    cli=("--duration", "-d"),
                ),
                _output(),
            ),
        ),
        Action(
            group="video",
            name="snap",
            summary="Save a JPG screenshot from a video.",
            operation=f"{OPS}:snap",
            params=(
                _target(),
                Param(
                    "time",
                    ParamKind.TEXT,
                    "Timestamp of the screenshot.",
                    default="00:00:05",
                    cli=("--time", "-t"),
                ),
                _output("Output image."),
            ),
        ),
        Action(
            group="video",
            name="louder",
            summary="Raise the volume of a video or audio file.",
            operation=f"{OPS}:louder",
            params=(
                _target("Video or audio file."),
                Param(
                    "db",
                    ParamKind.FLOAT,
                    "Decibels to add, e.g. 5 or 10.",
                    default=5.0,
                    cli=("--db",),
                ),
                _output(),
            ),
        ),
        Action(
            group="video",
            name="mute",
            summary="Remove the audio track from a video.",
            operation=f"{OPS}:mute",
            params=(_target(), _output()),
        ),
        Action(
            group="video",
            name="concat",
            summary="Join several videos into one.",
            operation=f"{OPS}:concat",
            params=(
                Param(
                    "target",
                    ParamKind.FILE,
                    "A .txt list of video paths, or a pattern such as clips/*.mp4.",
                ),
                _output(),
                Param(
                    "method",
                    ParamKind.CHOICE,
                    "fast copies the streams; safe re-encodes.",
                    default=DEFAULT_CONCAT_METHOD,
                    choices=tuple(CONCAT_METHODS),
                    cli=("--method", "-m"),
                ),
            ),
        ),
        Action(
            group="video",
            name="brightness",
            summary="Adjust brightness and contrast.",
            operation=f"{OPS}:brightness",
            params=(
                _target(),
                Param(
                    "brightness",
                    ParamKind.FLOAT,
                    "0.0 to 2.0; 1.0 is unchanged.",
                    default=1.0,
                    cli=("--brightness", "-b"),
                ),
                Param(
                    "contrast",
                    ParamKind.FLOAT,
                    "0.0 to 2.0; 1.0 is unchanged.",
                    default=1.0,
                    cli=("--contrast", "-c"),
                ),
                _output(),
            ),
        ),
        Action(
            group="video",
            name="color",
            summary="Apply a colour grading preset.",
            operation=f"{OPS}:color",
            params=(
                _target(),
                Param(
                    "preset",
                    ParamKind.CHOICE,
                    "Colour preset.",
                    default="vivid",
                    choices=COLOR_PRESETS,
                    cli=("--preset", "-p"),
                ),
                _output(),
            ),
        ),
        Action(
            group="video",
            name="stabilize",
            summary="Stabilize shaky footage.",
            operation=f"{OPS}:stabilize",
            params=(_target(), _output()),
        ),
        Action(
            group="video",
            name="normalize",
            summary="Even out loudness to a target level.",
            operation=f"{OPS}:normalize",
            params=(
                _target("Audio or video file."),
                Param(
                    "level",
                    ParamKind.FLOAT,
                    "Target loudness in LUFS.",
                    default=-20.0,
                    cli=("--level", "-l"),
                ),
                _output(),
            ),
        ),
        Action(
            group="video",
            name="denoise",
            summary="Remove background noise from audio or video.",
            operation=f"{OPS}:denoise",
            params=(
                _target("Video or audio file with background noise."),
                Param(
                    "mode",
                    ParamKind.CHOICE,
                    "auto (general), hiss, hum (low rumble), speech (best for voice).",
                    default="auto",
                    choices=DENOISE_MODES,
                    cli=("--mode", "-m"),
                ),
                Param(
                    "strength",
                    ParamKind.CHOICE,
                    "How hard to filter. Only used by auto mode.",
                    default="medium",
                    choices=DENOISE_STRENGTHS,
                    cli=("--strength", "-s"),
                ),
                _output_long(),
            ),
            queueable=True,
        ),
        Action(
            group="video",
            name="audio-convert",
            summary="Convert audio between formats, for example WAV to MP3.",
            operation=f"{OPS}:audio_convert",
            params=(
                _target("Audio or video file."),
                Param(
                    "format",
                    ParamKind.CHOICE,
                    "Target format.",
                    default="mp3",
                    choices=("mp3", "aac", "flac", "wav", "ogg"),
                    cli=("--format", "-f"),
                ),
                Param(
                    "quality",
                    ParamKind.CHOICE,
                    "Bitrate: s (128k), m (192k), h (320k).",
                    default=DEFAULT_AUDIO_CONVERT_QUALITY,
                    choices=tuple(AUDIO_CONVERT_BITRATES),
                    cli=("--quality", "-q"),
                ),
                _output(),
            ),
        ),
        Action(
            group="video",
            name="record",
            summary="Record the screen until the time runs out or you press Ctrl+C.",
            operation=f"{OPS}:record",
            params=(
                Param(
                    "output",
                    ParamKind.OUTPUT,
                    "Output video file.",
                    default="screen recording.mp4",
                ),
                Param(
                    "duration",
                    ParamKind.INT,
                    "Seconds to record.",
                    default=None,
                    cli=("--duration", "-d"),
                ),
                Param(
                    "fps",
                    ParamKind.INT,
                    "Frames per second.",
                    default=30,
                    cli=("--fps",),
                ),
                Param(
                    "audio",
                    ParamKind.BOOL,
                    "Include system audio.",
                    default=False,
                    cli=("--audio", "-a"),
                ),
            ),
            surfaces=CLI_ONLY,
        ),
        Action(
            group="video",
            name="stream",
            summary="Stream a video to an RTMP server.",
            operation=f"{OPS}:stream",
            params=(
                _target("Video file to stream."),
                Param(
                    "rtmp_url", ParamKind.URL, "RTMP server URL.", cli=("--url", "-u")
                ),
                Param(
                    "bitrate",
                    ParamKind.TEXT,
                    "Video bitrate, e.g. 4500k.",
                    default="4500k",
                    cli=("--bitrate", "-b"),
                ),
                Param(
                    "preset",
                    ParamKind.TEXT,
                    "Encoding preset, ultrafast to slow.",
                    default="veryfast",
                    cli=("--preset", "-p"),
                ),
            ),
            danger=Danger.NONE,
            surfaces=CLI_ONLY,
        ),
        Action(
            group="video",
            name="preview",
            summary="Serve a live HLS preview over HTTP.",
            operation=f"{OPS}:preview",
            params=(
                _target("Video file to preview."),
                Param(
                    "port",
                    ParamKind.INT,
                    "HTTP server port.",
                    default=8080,
                    cli=("--port", "-p"),
                ),
                Param(
                    "bitrate",
                    ParamKind.TEXT,
                    "Transcoding bitrate.",
                    default="2000k",
                    cli=("--bitrate", "-b"),
                ),
            ),
            danger=Danger.NONE,
            surfaces=CLI_ONLY,
        ),
    ),
)
