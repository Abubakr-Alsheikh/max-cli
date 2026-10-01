"""Catalog entries for `max audio`. `tests/test_catalog_drift.py` checks them against the CLI."""

from max_cli.core.catalog.spec import Action, Danger, Group, Param, ParamKind
from max_cli.core.presets import (
    AUDIO_COMPRESS_BITRATES,
    AUDIO_ORGANIZE_PATTERNS,
    DEFAULT_AUDIO_COMPRESS_QUALITY,
    DEFAULT_AUDIO_ORGANIZE_PATTERN,
    DENOISE_MODES,
    DENOISE_STRENGTHS,
)

OPS = "max_cli.core.operations.audio"
VIDEO_OPS = "max_cli.core.operations.video"


def _target(help: str = "Audio file.") -> Param:
    return Param("target", ParamKind.FILE, help)


def _targets(help: str) -> Param:
    return Param("targets", ParamKind.FILE, help, multiple=True)


def _output(
    help: str = "Write to this new file instead of changing the original.",
) -> Param:
    return Param("output", ParamKind.OUTPUT, help, default=None, cli=("-o", "--output"))


def _text(name: str, help: str, *cli: str) -> Param:
    return Param(name, ParamKind.TEXT, help, default=None, cli=cli)


def _shared_tags() -> tuple[Param, ...]:
    """The tags `set` and `batch` both write, in their CLI order."""
    return (
        _text("title", "Song title.", "--title", "-t"),
        _text("artist", "Artist name.", "--artist", "-a"),
        _text("album", "Album name.", "--album", "-b"),
        _text("albumartist", "Album artist name.", "--album-artist"),
        _text("genre", "Genre.", "--genre", "-g"),
        _text("date", "Release date or year (2024 or 2024-05-01).", "--date", "-d"),
    )


GROUP = Group(
    name="audio",
    summary="Read, write and clear audio tags, sort music into folders, compress.",
    actions=(
        Action(
            group="audio",
            name="compress",
            summary="Shrink an audio file by re-encoding it as a smaller MP3.",
            operation=f"{OPS}:compress",
            params=(
                _target("Audio file to compress."),
                Param(
                    "output",
                    ParamKind.OUTPUT,
                    "Output file. Default: <name>_compressed.mp3 next to it.",
                    default=None,
                    cli=("-o", "--output"),
                ),
                Param(
                    "quality",
                    ParamKind.CHOICE,
                    "Bitrate: s (64k), m (96k), h (128k), x (192k).",
                    default=DEFAULT_AUDIO_COMPRESS_QUALITY,
                    choices=tuple(AUDIO_COMPRESS_BITRATES),
                    cli=("--quality", "-q"),
                ),
                Param(
                    "mono",
                    ParamKind.BOOL,
                    "Mix down to one channel: about half the size again.",
                    default=False,
                    cli=("--mono", "-m"),
                ),
            ),
        ),
        Action(
            group="audio",
            name="denoise",
            summary="Remove background noise: hiss, hum, fans, room sound.",
            operation=f"{VIDEO_OPS}:denoise",
            params=(
                _target("Audio file with background noise."),
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
                Param(
                    "output",
                    ParamKind.OUTPUT,
                    "Output file. Default: <name>_denoised next to it.",
                    default=None,
                    cli=("-o", "--output"),
                ),
            ),
        ),
        Action(
            group="audio",
            name="get",
            summary="Show a file's tags (title, artist, album ...) and its length and bitrate.",
            operation=f"{OPS}:get",
            params=(_target("Audio file to read."),),
            danger=Danger.NONE,
        ),
        Action(
            group="audio",
            name="set",
            summary="Write tags into an audio file. Tags you leave empty stay as they are.",
            operation=f"{OPS}:set_tags",
            params=(
                _target("Audio file to tag."),
                *_shared_tags(),
                _text("tracknumber", "Track number (3, or 3/12).", "--track", "-n"),
                _text("discnumber", "Disc number.", "--disc"),
                _text("composer", "Composer.", "--composer"),
                _text("comment", "Comment.", "--comment", "-c"),
                _output(),
            ),
            danger=Danger.OVERWRITES,
        ),
        Action(
            group="audio",
            name="clear",
            summary="Remove every tag from an audio file. The sound stays the same.",
            operation=f"{OPS}:clear",
            params=(_target("Audio file to clear."), _output()),
            danger=Danger.OVERWRITES,
        ),
        Action(
            group="audio",
            name="batch",
            summary="Write the same tags into many files, e.g. one album. Can number the tracks.",
            operation=f"{OPS}:batch",
            params=(
                _targets("Audio files, a folder of them, or a pattern such as *.mp3."),
                *_shared_tags(),
                _text(
                    "tracknumber",
                    "One track number for every file. To count up, use --start.",
                    "--track",
                    "-n",
                ),
                Param(
                    "start",
                    ParamKind.INT,
                    "Number the tracks in file order, starting here.",
                    default=None,
                    cli=("--start",),
                ),
                _text("discnumber", "Disc number.", "--disc"),
                _text("composer", "Composer.", "--composer"),
                _text("comment", "Comment.", "--comment", "-c"),
            ),
            danger=Danger.OVERWRITES,
        ),
        Action(
            group="audio",
            name="organize",
            summary="Move audio files into folders by their tags (Artist/Album/Title.mp3).",
            operation=f"{OPS}:organize",
            params=(
                _targets("Audio files, a folder of them, or a pattern such as *.mp3."),
                Param(
                    "output",
                    ParamKind.FOLDER,
                    "Folder to sort into. Default: the files' own folder.",
                    default=None,
                    cli=("-o", "--output"),
                ),
                Param(
                    "pattern",
                    ParamKind.CHOICE,
                    "Folders by: artist, album, genre, artist-album, or "
                    "contributing-artists (album artist, else artist).",
                    default=DEFAULT_AUDIO_ORGANIZE_PATTERN,
                    choices=AUDIO_ORGANIZE_PATTERNS,
                    cli=("--pattern", "-p"),
                ),
                Param(
                    "filter_value",
                    ParamKind.TEXT,
                    "Only move files that would land in this folder, e.g. 'Electronic Gems'.",
                    default="",
                    cli=("--filter", "-f"),
                    advanced=True,
                ),
                Param(
                    "dry_run",
                    ParamKind.BOOL,
                    "Show where each file would go without moving anything.",
                    default=False,
                    cli=("--dry-run",),
                ),
            ),
            danger=Danger.MOVES,
        ),
    ),
)
