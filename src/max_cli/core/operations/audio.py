"""`max audio` operations: tags (read, write, clear, many files at once),
sorting files into folders by their tags, and compressing.

The CLI, the dashboard and the agent call these through the catalog
(`core/catalog/groups/audio.py`). They never prompt or print. Pass `engine`
to reuse an AudioMetadataEngine, or a MediaEngine for `compress` (the CLI
passes one that asks before downloading FFmpeg). `max audio denoise` runs
`video.denoise`, the same filter.

Inputs that take several files (batch, organize) also take a folder (its
audio files) and wildcard patterns such as `*.mp3`: the CLI's shell may
expand those, the dashboard and the agent don't.
"""

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from max_cli.common.exceptions import (
    ProcessingError,
    ResourceNotFoundError,
    ValidationError,
)
from max_cli.core.operations.result import ActionResult
from max_cli.core.presets import (
    AUDIO_COMPRESS_BITRATES,
    AUDIO_ORGANIZE_PATTERNS,
    DEFAULT_AUDIO_COMPRESS_QUALITY,
    DEFAULT_AUDIO_ORGANIZE_PATTERN,
    bitrate_for_quality,
    sibling_path,
)

if TYPE_CHECKING:
    from max_cli.core.engines.audio_metadata_engine import AudioMetadataEngine
    from max_cli.core.engines.media_engine import MediaEngine

WILDCARDS = frozenset("*?[")
MONO = 1
STREAM_KEYS = ("duration", "bitrate", "sample_rate", "channels")


def _engine(engine: Optional["AudioMetadataEngine"]) -> "AudioMetadataEngine":
    if engine is not None:
        return engine
    from max_cli.core.engines.audio_metadata_engine import AudioMetadataEngine

    return AudioMetadataEngine()


def _media_engine(engine: Optional["MediaEngine"]) -> "MediaEngine":
    if engine is not None:
        return engine
    from max_cli.core.engines.media_engine import MediaEngine

    return MediaEngine()


def _supported() -> frozenset[str]:
    from max_cli.core.engines.audio_metadata_engine import SUPPORTED_EXTENSIONS

    return frozenset(SUPPORTED_EXTENSIONS)


def _require_audio(target: Path) -> None:
    if not target.is_file():
        raise ResourceNotFoundError(f"File not found: {target}")
    if target.suffix.lower() not in _supported():
        raise ValidationError(
            f"Max can't edit tags in {target.suffix or 'this'} files. "
            f"It reads {', '.join(sorted(_supported()))}."
        )


def resolve_audio_files(targets: list[Path]) -> list[Path]:
    """The audio files `targets` name: files, folders (their audio files) and
    wildcard patterns, in the given order, each file once."""
    from max_cli.core.engines.audio_metadata_engine import find_audio_files

    found: list[Path] = []
    for target in targets:
        target = target.expanduser()
        if target.is_dir():
            found += find_audio_files(target)
        elif target.is_file():
            found.append(target)
        elif WILDCARDS & set(target.name):
            found += sorted(
                path
                for path in target.parent.glob(target.name)
                if path.is_file() and path.suffix.lower() in _supported()
            )
        else:
            raise ResourceNotFoundError(f"Not found: {target}")
    unique = list(dict.fromkeys(found))
    if not unique:
        raise ValidationError("No audio files found.")
    return unique


# --- tags -------------------------------------------------------------------


def get(
    target: Path, *, engine: Optional["AudioMetadataEngine"] = None
) -> ActionResult:
    """Read a file's tags and stream info."""
    _require_audio(target)
    metadata = _engine(engine).get_metadata(target)
    tags = {key: value for key, value in metadata.items() if key not in STREAM_KEYS}
    stream = {key: metadata.get(key) for key in STREAM_KEYS}
    message = (
        f"{len(tags)} tags in {target.name}" if tags else f"No tags in {target.name}"
    )
    return ActionResult(True, message, details={"tags": tags, "stream": stream})


def set_tags(
    target: Path,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    album: Optional[str] = None,
    albumartist: Optional[str] = None,
    genre: Optional[str] = None,
    date: Optional[str] = None,
    tracknumber: Optional[str] = None,
    discnumber: Optional[str] = None,
    composer: Optional[str] = None,
    comment: Optional[str] = None,
    output: Optional[Path] = None,
    *,
    engine: Optional["AudioMetadataEngine"] = None,
) -> ActionResult:
    """Write the given tags; tags left out (None) stay as they are. Writes
    into `target` unless `output` names a new file."""
    _require_audio(target)
    fields = {
        "title": title,
        "artist": artist,
        "album": album,
        "albumartist": albumartist,
        "genre": genre,
        "date": date,
        "tracknumber": tracknumber,
        "discnumber": discnumber,
        "composer": composer,
        "comment": comment,
    }
    changes = {name: value for name, value in fields.items() if value is not None}
    if not changes:
        raise ValidationError("No tags given: set at least one, such as --title.")
    saved = _engine(engine).set_metadata(target, output, **changes)
    return ActionResult(
        True,
        f"Metadata saved: {saved}",
        output_files=[saved],
        details={"changed": changes},
    )


def clear(
    target: Path,
    output: Optional[Path] = None,
    *,
    engine: Optional["AudioMetadataEngine"] = None,
) -> ActionResult:
    """Remove every tag. The audio itself, and so its length, never changes."""
    _require_audio(target)
    cleared = _engine(engine).clear_metadata(target, output)
    return ActionResult(True, f"Cleared metadata: {cleared}", output_files=[cleared])


def batch(
    targets: list[Path],
    title: Optional[str] = None,
    artist: Optional[str] = None,
    album: Optional[str] = None,
    albumartist: Optional[str] = None,
    genre: Optional[str] = None,
    date: Optional[str] = None,
    tracknumber: Optional[str] = None,
    start: Optional[int] = None,
    discnumber: Optional[str] = None,
    composer: Optional[str] = None,
    comment: Optional[str] = None,
    *,
    engine: Optional["AudioMetadataEngine"] = None,
) -> ActionResult:
    """Write the same tags into many files. `start` numbers the tracks in
    file order from that number; `tracknumber` without it writes that one
    number into every file. A file that fails is reported; the rest go on."""
    files = resolve_audio_files(targets)
    given = {
        "title": title,
        "artist": artist,
        "album": album,
        "albumartist": albumartist,
        "genre": genre,
        "date": date,
        "discnumber": discnumber,
        "composer": composer,
        "comment": comment,
    }
    shared = {name: value for name, value in given.items() if value is not None}
    if not shared and tracknumber is None and start is None:
        raise ValidationError("No tags given: set at least one, such as --album.")
    from mutagen import MutagenError

    tag_engine = _engine(engine)
    updated: list[Path] = []
    failed: list[dict[str, str]] = []
    for position, path in enumerate(files):
        if start is not None:
            track: Optional[str] = str(start + position)
        else:
            track = tracknumber
        try:
            tag_engine.set_metadata(path, None, tracknumber=track, **shared)
        except (OSError, ValueError, MutagenError) as e:
            failed.append({"file": path.name, "error": str(e)})
            continue
        updated.append(path)
    message = f"Updated {len(updated)} files successfully."
    if failed:
        message = f"Updated {len(updated)} of {len(files)} files."
    return ActionResult(
        bool(updated),
        message,
        output_files=updated,
        details={"failed": failed},
    )


def organize(
    targets: list[Path],
    output: Optional[Path] = None,
    pattern: str = DEFAULT_AUDIO_ORGANIZE_PATTERN,
    filter_value: str = "",
    dry_run: bool = False,
    *,
    engine: Optional["AudioMetadataEngine"] = None,
) -> ActionResult:
    """Move audio files into folders named by their tags (Artist/Album ...),
    each file named by its title. Records the moves, so `max files undo`
    puts them back. `dry_run` only lists where each file would go."""
    if pattern not in AUDIO_ORGANIZE_PATTERNS:
        raise ValidationError(
            f"Unknown pattern '{pattern}'. Use: {', '.join(AUDIO_ORGANIZE_PATTERNS)}."
        )
    files = resolve_audio_files(targets)
    target_dir = output or files[0].parent
    txn = None
    if not dry_run:
        from max_cli.common.transaction_log import TransactionLog

        txn = TransactionLog(command="audio organize")
    result = _engine(engine).organize(
        files,
        target_dir,
        pattern,
        transaction_log=txn,
        filter_value=filter_value or None,
        dry_run=dry_run,
    )
    undo_group = None
    if txn is not None and result["total_moved"]:
        txn.save()
        undo_group = txn.group_id
    verb = "Would move" if dry_run else "Moved"
    return ActionResult(
        ok=not result["total_errors"] or bool(result["total_moved"]),
        message=f"{verb} {result['total_moved']} files into {target_dir}",
        details={
            "moves": result["moved"],
            "skipped": result["skipped"],
            "errors": result["errors"],
            "dry_run": dry_run,
        },
        undo_group=undo_group,
    )


# --- sound ------------------------------------------------------------------


def compress(
    target: Path,
    output: Optional[Path] = None,
    quality: str = DEFAULT_AUDIO_COMPRESS_QUALITY,
    mono: bool = False,
    *,
    engine: Optional["MediaEngine"] = None,
) -> ActionResult:
    """Re-encode to a smaller MP3: quality s, m, h or x (64k to 192k)."""
    if not target.is_file():
        raise ResourceNotFoundError(f"File not found: {target}")
    bitrate = bitrate_for_quality(
        AUDIO_COMPRESS_BITRATES, quality, DEFAULT_AUDIO_COMPRESS_QUALITY
    )
    output = output or sibling_path(target, "_compressed", "mp3")
    _media_engine(engine).compress_audio(
        target, output, bitrate=bitrate, channels=MONO if mono else None
    )
    before = target.stat().st_size
    after = output.stat().st_size if output.exists() else None
    return ActionResult(
        True,
        f"Audio compressed: {output}",
        output_files=[output],
        details={
            "bitrate": bitrate,
            "mono": mono,
            "input_size": before,
            "output_size": after,
        },
    )


# --- describing a file or folder (the dashboard's Audio page) ---------------

MISSING_TAGS_NOTE = "{count} without title or artist: batch or set can fill them."


# How many artists and albums a folder's facts name.
TOP_NAMES = 10


@dataclass
class AudioFacts:
    """What an audio file, or a folder of them, holds, for the Audio page."""

    path: Path
    size_bytes: int
    is_folder: bool = False
    # one file
    tags: dict[str, str] = field(default_factory=dict)
    duration: Optional[float] = None  # seconds
    bitrate: Optional[int] = None  # bits per second
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    cover_art: bool = False
    # a folder
    track_count: int = 0
    total_duration: float = 0.0
    formats: dict[str, int] = field(default_factory=dict)
    untagged: int = 0  # files with no title or no artist
    # the most common artists and albums, with their track counts
    artists: dict[str, int] = field(default_factory=dict)
    albums: dict[str, int] = field(default_factory=dict)
    note: str = ""


def describe(
    target: Path, *, engine: Optional["AudioMetadataEngine"] = None
) -> AudioFacts:
    """A file's tags, length, bitrate and cover art; for a folder, how many
    tracks, their length and size together, their formats, and how many
    lack a title or an artist. Raises ProcessingError for a file mutagen
    can't read."""
    from mutagen import MutagenError

    target = Path(target).expanduser()
    if not target.exists():
        raise ResourceNotFoundError(f"Not found: {target}")
    tag_engine = _engine(engine)
    if target.is_dir():
        from max_cli.core.engines.audio_metadata_engine import find_audio_files

        files = find_audio_files(target)
        total = 0.0
        untagged = 0
        artists: Counter[str] = Counter()
        albums: Counter[str] = Counter()
        for path in files:
            try:
                metadata = tag_engine.get_metadata(path)
            except (OSError, ValueError, MutagenError) as e:
                raise ProcessingError(f"Couldn't read {path.name}: {e}") from e
            total += float(metadata.get("duration") or 0)
            if not (metadata.get("title") and metadata.get("artist")):
                untagged += 1
            if metadata.get("artist"):
                artists[str(metadata["artist"])] += 1
            if metadata.get("album"):
                albums[str(metadata["album"])] += 1
        return AudioFacts(
            path=target,
            size_bytes=sum(path.stat().st_size for path in files),
            is_folder=True,
            track_count=len(files),
            total_duration=total,
            formats=dict(
                Counter(path.suffix.lstrip(".").upper() for path in files).most_common()
            ),
            untagged=untagged,
            artists=dict(artists.most_common(TOP_NAMES)),
            albums=dict(albums.most_common(TOP_NAMES)),
            note=MISSING_TAGS_NOTE.format(count=untagged) if untagged else "",
        )
    _require_audio(target)
    try:
        metadata = tag_engine.get_metadata(target)
        cover = tag_engine.has_cover_art(target)
    except (OSError, ValueError, MutagenError) as e:
        raise ProcessingError(f"Couldn't read this audio file: {e}") from e
    return AudioFacts(
        path=target,
        size_bytes=target.stat().st_size,
        tags={
            key: str(value)
            for key, value in metadata.items()
            if key not in STREAM_KEYS and value
        },
        duration=metadata.get("duration"),
        bitrate=metadata.get("bitrate"),
        sample_rate=metadata.get("sample_rate"),
        channels=metadata.get("channels"),
        cover_art=cover,
    )
