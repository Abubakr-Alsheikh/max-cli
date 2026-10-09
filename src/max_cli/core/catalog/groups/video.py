"""Catalog entries for `max video`. `tests/test_catalog_drift.py` checks them against the CLI."""

from max_cli.common import file_kinds
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


EACH_HINT = "Or several files, a folder, or a pattern such as *.mp4."


def _target(help: str = "Video file.") -> Param:
    return Param("target", ParamKind.FILE, help)


def _each_target(kinds: tuple[str, ...], help: str = "Video file.") -> Param:
    """The file param of an action that runs once per file: callers may
    give several files, a folder or a pattern (catalog.batch)."""
    return Param(
        "target", ParamKind.FILE, f"{help} {EACH_HINT}", each=True, kinds=kinds
    )


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
            guide=(
                "Use for: making videos smaller to share, upload or save space. Not "
                "for: changing only the container (video.convert) or audio files "
                "(audio.compress). How: level high keeps the most quality, balanced "
                "is the usual pick, max makes the smallest file; it writes a new "
                "file beside the original."
            ),
            summary="Compress a video to H.264 MP4.",
            operation=f"{OPS}:compress",
            params=(
                _each_target((file_kinds.VIDEO,), "Video file to compress."),
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
            output_name="{stem}_compressed.mp4",
        ),
        Action(
            group="video",
            name="convert",
            guide=(
                "Use for: changing a video's container (mkv, mov or avi to mp4) so "
                "it plays somewhere; fast and keeps the quality. Not for: making it "
                "smaller (video.compress) or audio files (video.audio-convert). "
                "How: format is the new container, mp4 by default."
            ),
            summary="Convert a video container, for example MKV to MP4.",
            operation=f"{OPS}:convert",
            params=(
                _each_target((file_kinds.VIDEO,), "Input video file."),
                Param(
                    "format",
                    ParamKind.TEXT,
                    "Target format (mp4, mkv, avi).",
                    default="mp4",
                    cli=("--format", "-f"),
                ),
            ),
            output_name="{stem}.{format}",
            queueable=True,
        ),
        Action(
            group="video",
            name="to-audio",
            guide=(
                "Use for: saving the sound of a video as an audio file (a talk, a "
                "song from a music video). Not for: files that are already audio "
                "(video.audio-convert). How: format mp3, wav, flac or aac; quality "
                "s, m, h or x, higher is bigger."
            ),
            summary="Extract the audio track into its own file.",
            operation=f"{OPS}:to_audio",
            params=(
                _each_target((file_kinds.VIDEO,), "Source video file."),
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
            output_name="{stem}.{format}",
            queueable=True,
        ),
        Action(
            group="video",
            name="gif",
            guide=(
                "Use for: a short looping clip to share in a chat or a document. "
                "Not for: long clips, which make huge GIFs: cut first (video.cut). "
                "How: width in pixels (480) and fps (15); lower both for a smaller "
                "file."
            ),
            summary="Turn a video clip into a GIF.",
            operation=f"{OPS}:gif",
            params=(
                _each_target((file_kinds.VIDEO,), "Input video."),
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
            output_name="{stem}.gif",
            queueable=True,
        ),
        Action(
            group="video",
            name="cut",
            guide=(
                "Use for: keeping one part of a video or audio file (trim the start "
                "or end, take a clip). Not for: joining files (video.concat). How: "
                "start as 00:01:30 or seconds; end or duration says where it stops, "
                "and without either it runs to the end."
            ),
            summary="Keep part of a video or audio file.",
            operation=f"{OPS}:cut",
            params=(
                _each_target(
                    (file_kinds.VIDEO, file_kinds.AUDIO), "Video or audio file."
                ),
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
            queueable=True,
        ),
        Action(
            group="video",
            name="snap",
            guide=(
                "Use for: a still picture from a video, such as a thumbnail. How: "
                "time is the moment to capture, as 00:00:05 or seconds."
            ),
            summary="Save a JPG screenshot from a video.",
            operation=f"{OPS}:snap",
            params=(
                _each_target((file_kinds.VIDEO,)),
                Param(
                    "time",
                    ParamKind.TEXT,
                    "Timestamp of the screenshot.",
                    default="00:00:05",
                    cli=("--time", "-t"),
                ),
                _output("Output image."),
            ),
            output_name="{stem}_thumb.jpg",
        ),
        Action(
            group="video",
            name="louder",
            guide=(
                "Use for: one quiet file that needs a fixed boost. Not for: making "
                "several files equally loud (video.normalize). How: db is how much "
                "louder, 5 by default; 3 to 10 is usual, more can distort."
            ),
            summary="Raise the volume of a video or audio file.",
            operation=f"{OPS}:louder",
            params=(
                _each_target(
                    (file_kinds.VIDEO, file_kinds.AUDIO), "Video or audio file."
                ),
                Param(
                    "db",
                    ParamKind.FLOAT,
                    "Decibels to add, e.g. 5 or 10.",
                    default=5.0,
                    cli=("--db",),
                ),
                _output(),
            ),
            output_name="{stem}_boosted{suffix}",
            queueable=True,
        ),
        Action(
            group="video",
            name="mute",
            guide=(
                "Use for: removing all sound from a video. Not for: removing only "
                "background noise (video.denoise)."
            ),
            summary="Remove the audio track from a video.",
            operation=f"{OPS}:mute",
            params=(_each_target((file_kinds.VIDEO,)), _output()),
            output_name="{stem}_mute.mp4",
            queueable=True,
        ),
        Action(
            group="video",
            name="concat",
            guide=(
                "Use for: joining several videos into one, in the order given. Not "
                "for: one clip from a longer video (video.cut). How: method fast "
                "joins without re-encoding and needs files with the same format and "
                "size; safe re-encodes, so mixed files work, but it is slower."
            ),
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
            guide=(
                "Use for: footage that is too dark, too bright or flat. Not for: a "
                "style or mood (video.color). How: brightness and contrast are "
                "factors around 1.0 (1.2 is 20% more); small steps look natural."
            ),
            summary="Adjust brightness and contrast.",
            operation=f"{OPS}:brightness",
            params=(
                _each_target((file_kinds.VIDEO,)),
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
            output_name="{stem}_adjusted.mp4",
            queueable=True,
        ),
        Action(
            group="video",
            name="color",
            guide=(
                "Use for: giving a video a look: vivid, vintage, noir (black and "
                "white), warm, cool or fade. Not for: fixing dark footage "
                "(video.brightness)."
            ),
            summary="Apply a colour grading preset.",
            operation=f"{OPS}:color",
            params=(
                _each_target((file_kinds.VIDEO,)),
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
            output_name="{stem}_{preset}.mp4",
            queueable=True,
        ),
        Action(
            group="video",
            name="stabilize",
            guide=(
                "Use for: shaky handheld footage. It is slow on long videos and "
                "crops the edges a little."
            ),
            summary="Stabilize shaky footage.",
            operation=f"{OPS}:stabilize",
            params=(_each_target((file_kinds.VIDEO,)), _output()),
            output_name="{stem}_stabilized.mp4",
            queueable=True,
        ),
        Action(
            group="video",
            name="normalize",
            guide=(
                "Use for: making one or several files equally loud, such as podcast "
                "episodes or a playlist. Not for: one quiet file by a fixed amount "
                "(video.louder). How: level is the target loudness in dB, -20 by "
                "default; -16 is louder."
            ),
            summary="Even out loudness to a target level.",
            operation=f"{OPS}:normalize",
            params=(
                _each_target(
                    (file_kinds.VIDEO, file_kinds.AUDIO), "Audio or video file."
                ),
                Param(
                    "level",
                    ParamKind.FLOAT,
                    "Target loudness in LUFS.",
                    default=-20.0,
                    cli=("--level", "-l"),
                ),
                _output(),
            ),
            output_name="{stem}_normalized{suffix}",
            queueable=True,
        ),
        Action(
            group="video",
            name="denoise",
            guide=(
                "Use for: background noise in the sound of a video. Not for: audio "
                "files (audio.denoise). How: mode auto, hiss, hum (electrical buzz) "
                "or speech (keeps voices clear); strength mild, medium or "
                "aggressive, which can sound robotic."
            ),
            summary="Remove background noise from audio or video.",
            operation=f"{OPS}:denoise",
            params=(
                _each_target(
                    (file_kinds.VIDEO, file_kinds.AUDIO),
                    "Video or audio file with background noise.",
                ),
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
            output_name="{stem}_denoised{suffix}",
        ),
        Action(
            group="video",
            name="audio-convert",
            guide=(
                "Use for: changing an audio file's format (m4a, wav or flac to mp3, "
                "and back) so it plays or fits somewhere. Not for: the sound of a "
                "video (video.to-audio) or making audio smaller in the same format "
                "(audio.compress). How: format mp3, aac, flac, wav or ogg; quality "
                "s, m or h."
            ),
            summary="Convert audio between formats, for example WAV to MP3.",
            operation=f"{OPS}:audio_convert",
            params=(
                _each_target(
                    (file_kinds.AUDIO, file_kinds.VIDEO), "Audio or video file."
                ),
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
            output_name="{stem}.{format}",
            queueable=True,
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
