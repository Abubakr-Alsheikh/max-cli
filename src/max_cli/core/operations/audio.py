"""`max audio` operations: tags (read, write, clear, many files at once),
sorting files into folders by their tags, compressing, and transcripts
through Google Gemini.

The CLI, the dashboard and the agent call these through the catalog
(`core/catalog/groups/audio.py`). They never prompt or print. Pass `engine`
to reuse an AudioMetadataEngine, or a MediaEngine for `compress` (the CLI
passes one that asks before downloading FFmpeg). `max audio denoise` runs
`video.denoise`, the same filter.

Inputs that take several files (batch, organize) also take a folder (its
audio files) and wildcard patterns such as `*.mp3`: the CLI's shell may
expand those, the dashboard and the agent don't.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from max_cli.common.exceptions import (
    AIError,
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
    DEFAULT_TRANSCRIBE_MODEL,
    DEFAULT_TRANSCRIPT_FORMAT,
    TRANSCRIPT_FORMATS,
    bitrate_for_quality,
    sibling_path,
)

if TYPE_CHECKING:
    from max_cli.core.engines.audio_metadata_engine import AudioMetadataEngine
    from max_cli.core.engines.gemini_files import GeminiFiles
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


# --- transcripts through Google Gemini ---------------------------------------

TRANSCRIPT_PROMPT = (
    "Transcribe the speech in this audio word for word, in the language that is "
    "spoken. Start a new paragraph when the speaker or the topic changes. When "
    "more than one person speaks, begin each turn with a label such as "
    "'Speaker 1:', or the person's name when the recording says it. Mark sounds "
    "that matter to the meaning in brackets, such as [laughter] or [music]. "
    "Reply with the transcript only: no title, introduction or notes."
)
SUBTITLE_PROMPT = (
    "Transcribe the speech in this audio as subtitle cues, in the language that "
    "is spoken. The recording is {seconds:.1f} seconds long. Give each cue's start "
    "and end in seconds from the beginning of the recording, matching when its "
    "words are spoken, never past the end. Keep each cue 1 to 7 seconds long and "
    "under about 80 characters; split long sentences into several cues."
)
EXTRA_INSTRUCTIONS = (
    "\n\nExtra instructions from the user. Follow them, and where they "
    "differ from the above, they win:\n{prompt}"
)
# Gemini answers subtitles as JSON in this shape, and Max writes the SRT:
# the model's own SRT text got the timings wrong.
CUES_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "start": {"type": "NUMBER"},
            "end": {"type": "NUMBER"},
            "text": {"type": "STRING"},
        },
        "required": ["start", "end", "text"],
    },
}
SPEECH_MIME_TYPE = "audio/mp3"
CODE_FENCE = re.compile(r"^```[\w-]*\n(.*?)\n?```$", re.DOTALL)
CUT_OFF_NOTE = (
    "Gemini stopped at its output limit, so the end is missing. Cut the "
    "recording into parts (max video cut) and transcribe each."
)
# A subtitle line, and the shortest time a cue stays on screen.
SUBTITLE_LINE_CHARS = 42
MIN_CUE_SECONDS = 0.5
MILLISECONDS = 1000


def transcript_prompt(format: str, prompt: Optional[str], seconds: float = 0.0) -> str:
    """The request Gemini gets: the default for the format, plus the user's
    own instructions (a translation, a summary, names to spell) when given."""
    base = (
        SUBTITLE_PROMPT.format(seconds=seconds)
        if format == "srt"
        else TRANSCRIPT_PROMPT
    )
    extra = (prompt or "").strip()
    return base + EXTRA_INSTRUCTIONS.format(prompt=extra) if extra else base


def _clean_answer(text: str) -> str:
    """The answer without a Markdown code fence around it."""
    text = text.strip()
    fenced = CODE_FENCE.match(text)
    return (fenced.group(1) if fenced else text).strip() + "\n"


def _srt_time(seconds: float) -> str:
    milliseconds = int(round(seconds * MILLISECONDS))
    hours, rest = divmod(milliseconds, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    whole, fraction = divmod(rest, MILLISECONDS)
    return f"{hours:02}:{minutes:02}:{whole:02},{fraction:03}"


def _two_lines(text: str) -> str:
    """Long cue text split at the space nearest the middle, as players show
    two short lines better than one long one."""
    text = " ".join(text.split())
    if len(text) <= SUBTITLE_LINE_CHARS:
        return text
    middle = len(text) // 2
    spaces = [index for index, char in enumerate(text) if char == " "]
    if not spaces:
        return text
    split = min(spaces, key=lambda index: abs(index - middle))
    return f"{text[:split]}\n{text[split + 1 :]}"


def cues_to_srt(cues: list[dict], seconds: float) -> str:
    """SRT text from Gemini's cues: in time order, inside the recording, each
    at least MIN_CUE_SECONDS long and ending before the next starts.

    Raises AIError when no cue has text and a usable time.
    """
    timed = []
    for cue in cues:
        try:
            start, end = float(cue["start"]), float(cue["end"])
        except (KeyError, TypeError, ValueError):
            continue
        words = str(cue.get("text", "")).strip()
        if words and 0 <= start < (seconds or float("inf")):
            timed.append((start, end, words))
    if not timed:
        raise AIError("Gemini's subtitles had no usable cues, so Max saved nothing.")
    timed.sort(key=lambda cue: cue[0])
    blocks = []
    for number, (start, end, words) in enumerate(timed, 1):
        following = timed[number][0] if number < len(timed) else None
        end = max(end, start + MIN_CUE_SECONDS)
        if following is not None:
            end = min(end, following)
        if seconds:
            end = min(end, seconds)
        blocks.append(
            f"{number}\n{_srt_time(start)} --> {_srt_time(end)}\n{_two_lines(words)}\n"
        )
    return "\n".join(blocks)


def _subtitles(answer_text: str, seconds: float) -> str:
    import json

    try:
        cues = json.loads(_clean_answer(answer_text))
    except json.JSONDecodeError:
        raise AIError(
            "Gemini's subtitles weren't in the expected shape, so Max saved nothing."
        ) from None
    if not isinstance(cues, list):
        raise AIError("Gemini's subtitles had no list of cues, so Max saved nothing.")
    return cues_to_srt([cue for cue in cues if isinstance(cue, dict)], seconds)


def _gemini_client() -> "GeminiFiles":
    from max_cli.config import settings
    from max_cli.core.engines.gemini_files import GeminiFiles

    return GeminiFiles(settings.GEMINI_API_KEY)


def _transcribe_model(model: Optional[str]) -> str:
    from max_cli.config import settings

    return (model or settings.GEMINI_MODEL or DEFAULT_TRANSCRIBE_MODEL).strip()


def _seconds(media: "MediaEngine", speech: Path) -> float:
    try:
        return float(media.probe_media(speech)["format"]["duration"])
    except (RuntimeError, KeyError, TypeError, ValueError):
        return 0.0


def transcribe(
    target: Path,
    format: str = DEFAULT_TRANSCRIPT_FORMAT,
    prompt: Optional[str] = None,
    model: Optional[str] = None,
    output: Optional[Path] = None,
    *,
    engine: Optional["MediaEngine"] = None,
    client: Optional["GeminiFiles"] = None,
) -> ActionResult:
    """A transcript (txt) or subtitles (srt) of an audio or video file.

    FFmpeg makes a small speech MP3 first (a video's sound only), which goes to
    Google Gemini's Files API; Gemini answers the prompt about it, and the
    upload is deleted afterwards. `prompt` adds instructions to the default
    one, such as "translate to Arabic" or "summarise it in 5 points".
    Subtitles come back as JSON cues (CUES_SCHEMA), and Max writes the SRT.
    """
    import tempfile

    from max_cli.common.atomic import atomic_write_text

    if not target.is_file():
        raise ResourceNotFoundError(f"File not found: {target}")
    if format not in TRANSCRIPT_FORMATS:
        raise ValidationError(
            f"Unknown format '{format}'. Use one of: {', '.join(TRANSCRIPT_FORMATS)}."
        )
    gemini = client or _gemini_client()
    chosen_model = _transcribe_model(model)
    output = output or target.with_suffix(f".{format}")
    subtitles = format == "srt"
    media = _media_engine(engine)
    with tempfile.TemporaryDirectory(prefix="max-transcribe-") as folder:
        speech = Path(folder) / f"{target.stem}.mp3"
        try:
            media.speech_audio(target, speech)
        except RuntimeError as exc:
            raise ProcessingError(f"Max couldn't read the sound: {exc}") from None
        seconds = _seconds(media, speech)
        uploaded = gemini.upload(speech, SPEECH_MIME_TYPE)
        try:
            uploaded = gemini.wait_until_ready(uploaded)
            answer = gemini.ask(
                chosen_model,
                transcript_prompt(format, prompt, seconds),
                uploaded,
                schema=CUES_SCHEMA if subtitles else None,
            )
        finally:
            gemini.delete(uploaded)
    if answer.cut_off and subtitles:
        raise AIError(CUT_OFF_NOTE)
    text = _subtitles(answer.text, seconds) if subtitles else _clean_answer(answer.text)
    atomic_write_text(output, text)
    message = f"{'Subtitles' if subtitles else 'Transcript'} saved: {output}"
    if answer.cut_off:
        message += f". {CUT_OFF_NOTE}"
    return ActionResult(
        True,
        message,
        [output],
        details={
            "model": chosen_model,
            "seconds": round(seconds, 1),
            "characters": len(text),
            "cut_off": answer.cut_off,
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
