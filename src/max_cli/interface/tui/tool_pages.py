"""The command-group pages: one ToolPageSpec each (see widgets/tool_page.py).

A test checks that every dashboard action of a page's group sits in exactly
one of its sections, so a new command can't go missing from its page.
"""

from pathlib import Path

from textual.content import Content

from max_cli.common import file_kinds
from max_cli.common.utils import format_size
from max_cli.core.presets import TUI_AUDIO_ORGANIZE_PATTERN
from max_cli.interface.tui.widgets.tool_page import ToolPageSpec, ToolSection

SEPARATOR = "  ·  "
MONO = 1
STEREO = 2


def _clock(seconds: float) -> str:
    whole = int(seconds)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes}:{secs:02}"


def _channels(count: "int | None") -> str:
    if count == MONO:
        return "mono"
    if count == STEREO:
        return "stereo"
    return f"{count} channels" if count else ""


def describe_video(path: Path) -> Content:
    """clip.mp4 · 1:02:05 · 1920x1080 · 29.97 fps · h264 + aac stereo · 412 MB"""
    from max_cli.core.operations import video

    facts = video.describe(path)
    parts = [
        _clock(facts.duration) if facts.duration else "",
        f"{facts.width}x{facts.height}" if facts.width and facts.height else "",
        f"{facts.fps:g} fps" if facts.fps else "",
        " + ".join(
            part
            for part in (
                facts.video_codec,
                " ".join(
                    p for p in (facts.audio_codec, _channels(facts.audio_channels)) if p
                ),
            )
            if part
        ),
        format_size(facts.size_bytes),
        f"{facts.bitrate / 1_000_000:.1f} Mb/s" if facts.bitrate else "",
    ]
    lines = [
        Content.assemble(
            (facts.path.name, "bold $primary"),
            (SEPARATOR + SEPARATOR.join(part for part in parts if part), ""),
        )
    ]
    if not facts.video_codec and facts.audio_codec:
        lines.append(
            Content.styled("Audio only: the Sound actions fit it.", "$text-muted")
        )
    if facts.note:
        lines.append(Content.styled(facts.note, "$warning"))
    return Content("\n").join(lines)


VIDEO = ToolPageSpec(
    page_id="video",
    group="video",
    title="VIDEO",
    tagline="FFMPEG STUDIO",
    hint="Compress, cut, convert and fix videos and audio  ·  "
    "long jobs can go to the queue",
    file_prompt="Pick a video or audio file, or paste its path",
    sections=(
        ToolSection("SHRINK & CONVERT", ("compress", "convert", "gif")),
        ToolSection("CUT & JOIN", ("cut", "concat", "snap")),
        ToolSection(
            "SOUND",
            ("to-audio", "audio-convert", "louder", "mute", "normalize", "denoise"),
        ),
        ToolSection("PICTURE", ("brightness", "color", "stabilize")),
    ),
    describe=describe_video,
    kinds=(file_kinds.VIDEO,),
)


def describe_pdf(path: Path) -> Content:
    """report.pdf · 12 pages · A4 portrait · 2.40 MB · "Q3 report" by Ana · 8 form fields"""
    from max_cli.core.operations import pdf

    facts = pdf.describe(path)
    pages = facts.pages
    byline = " by ".join(
        part
        for part in (f'"{facts.title}"' if facts.title else "", facts.author)
        if part
    )
    parts = [
        f"{pages} page{'s' if pages != 1 else ''}" if pages is not None else "",
        facts.page_size,
        format_size(facts.size_bytes),
        byline,
        f"{facts.form_fields} form fields" if facts.form_fields else "",
    ]
    lines = [
        Content.assemble(
            (facts.path.name, "bold $primary"),
            (SEPARATOR + SEPARATOR.join(part for part in parts if part), ""),
        )
    ]
    if facts.note:
        lines.append(
            Content.styled(facts.note, "$warning" if facts.encrypted else "$text-muted")
        )
    return Content("\n").join(lines)


PDF = ToolPageSpec(
    page_id="pdf",
    group="pdf",
    title="PDF",
    tagline="DOCUMENT DESK",
    hint="Merge, split, shrink, lock and read PDFs  ·  every action writes a new file",
    file_prompt="Pick a PDF, or paste its path",
    sections=(
        ToolSection("SHRINK", ("compress", "optimize")),
        ToolSection("COMBINE & SPLIT", ("merge", "bundle", "split", "compare")),
        ToolSection("PROTECT & MARK", ("lock", "stamp")),
        ToolSection("EXTRACT", ("rip", "ocr")),
        ToolSection("FORMS", ("form-data", "form-fill", "form-flatten")),
    ),
    describe=describe_pdf,
    kinds=(file_kinds.PDF,),
)

KILOBIT = 1000
KILOHERTZ = 1000
# Tags shown on the facts line, in order, and what goes before each value.
SHOWN_TAGS = (("album", ""), ("date", ""), ("tracknumber", "track "), ("genre", ""))


def describe_audio(path: Path) -> Content:
    """song.mp3 · 3:45 · 320 kbps · 44.1 kHz stereo · 8.60 MB · cover art
    "My Song" by Ana  ·  Album X  ·  2024  ·  track 3  ·  Pop

    A folder: Album · 12 tracks · 48:20 · 120 MB · 12 MP3"""
    from max_cli.core.operations import audio

    facts = audio.describe(path)
    lines = []
    if facts.is_folder:
        parts = [
            f"{facts.track_count} track{'s' if facts.track_count != 1 else ''}",
            _clock(facts.total_duration) if facts.total_duration else "",
            format_size(facts.size_bytes) if facts.track_count else "",
            ", ".join(f"{count} {kind}" for kind, count in facts.formats.items()),
        ]
    else:
        sound = " ".join(
            part
            for part in (
                f"{facts.sample_rate / KILOHERTZ:g} kHz" if facts.sample_rate else "",
                _channels(facts.channels),
            )
            if part
        )
        parts = [
            _clock(facts.duration) if facts.duration else "",
            f"{facts.bitrate // KILOBIT} kbps" if facts.bitrate else "",
            sound,
            format_size(facts.size_bytes),
            "cover art" if facts.cover_art else "",
        ]
    lines.append(
        Content.assemble(
            (facts.path.name or str(facts.path), "bold $primary"),
            (SEPARATOR + SEPARATOR.join(part for part in parts if part), ""),
        )
    )
    if not facts.is_folder:
        tags = facts.tags
        heading = " by ".join(
            part
            for part in (
                f'"{tags["title"]}"' if tags.get("title") else "",
                tags.get("artist", ""),
            )
            if part
        )
        rest = [
            f"{prefix}{tags[name]}" for name, prefix in SHOWN_TAGS if tags.get(name)
        ]
        if heading or rest:
            lines.append(
                Content(SEPARATOR.join(part for part in (heading, *rest) if part))
            )
        else:
            lines.append(
                Content.styled(
                    "No tags yet: set adds a title, artist and album.", "$text-muted"
                )
            )
    if facts.note:
        lines.append(Content.styled(facts.note, "$warning"))
    return Content("\n").join(lines)


def prefill_audio(action: str, path: Path) -> dict[str, str]:
    """The `set` form starts from the file's current tags, so you edit them
    instead of typing them all again."""
    from max_cli.common.exceptions import MaxError
    from max_cli.core.operations import audio

    if action != "set" or not path.is_file():
        return {}
    try:
        tags = audio.get(path).details["tags"]
    except (MaxError, OSError, ValueError):
        return {}  # the facts line reports what's wrong with the file
    from max_cli.core.engines.audio_metadata_engine import TAG_FIELDS

    return {name: str(tags[name]) for name in TAG_FIELDS if tags.get(name)}


AUDIO = ToolPageSpec(
    page_id="audio",
    group="audio",
    title="AUDIO",
    tagline="TAG STUDIO",
    hint="Edit tags, sort music into folders, shrink and clean recordings",
    file_prompt="Pick a song or a folder of music, or paste its path",
    sections=(
        ToolSection("TAGS", ("set", "get", "batch", "clear")),
        ToolSection("SORT", ("organize",)),
        ToolSection("SOUND", ("compress", "denoise")),
    ),
    describe=describe_audio,
    file_title="FILE OR FOLDER",
    kinds=(file_kinds.AUDIO,),
    action_defaults={"organize": {"pattern": TUI_AUDIO_ORGANIZE_PATTERN}},
    prefill=prefill_audio,
)

MEGAPIXEL = 1_000_000
# Pillow's colour modes, in words. Others show as Pillow names them (CMYK ...).
COLOUR_MODES = {
    "RGB": "colour",
    "RGBA": "colour with transparency",
    "L": "greyscale",
    "LA": "greyscale with transparency",
    "1": "black and white",
    "P": "palette colours",
}


def _image_count(count: int) -> str:
    return f"{count} image{'s' if count != 1 else ''}"


def describe_images(path: Path) -> Content:
    """photo.jpg · 4032x3024 (12.2 MP) · JPEG · colour · 3.10 MB · taken
    2024-05-01 on Pixel 7. A folder: photos · 48 images · 312 MB · 30 JPG, 18 PNG"""
    from max_cli.core.operations import images

    facts = images.describe(path)
    if facts.is_folder:
        parts = [
            _image_count(facts.image_count),
            format_size(facts.size_bytes) if facts.image_count else "",
            ", ".join(f"{count} {kind}" for kind, count in facts.formats.items()),
        ]
    else:
        pixels = (facts.width or 0) * (facts.height or 0)
        dimensions = f"{facts.width}x{facts.height}" if pixels else ""
        if pixels >= MEGAPIXEL:
            dimensions += f" ({pixels / MEGAPIXEL:.1f} MP)"
        shot = " on ".join(
            part
            for part in (f"taken {facts.taken}" if facts.taken else "", facts.camera)
            if part
        )
        parts = [
            dimensions,
            facts.format,
            COLOUR_MODES.get(facts.mode, facts.mode),
            f"{facts.frames} frames" if facts.frames > 1 else "",
            format_size(facts.size_bytes),
            shot,
        ]
    lines = [
        Content.assemble(
            (facts.path.name, "bold $primary"),
            (SEPARATOR + SEPARATOR.join(part for part in parts if part), ""),
        )
    ]
    if facts.is_folder and facts.output_dir is not None and facts.image_count:
        where = facts.output_dir.name
        lines.append(
            Content.styled(
                f"Actions run on each image here; results go to {where}.",
                "$text-muted",
            )
        )
    if facts.note:
        lines.append(Content.styled(facts.note, "$warning"))
    return Content("\n").join(lines)


IMAGES = ToolPageSpec(
    page_id="images",
    group="images",
    title="IMAGES",
    tagline="PIXEL LAB",
    hint="Shrink, resize, convert and clean images  ·  one image or a whole folder",
    file_prompt="Pick an image or a folder of images, or paste its path",
    sections=(
        ToolSection("SHRINK", ("compress", "resize")),
        ToolSection("CONVERT & CLEAN", ("convert", "strip")),
    ),
    describe=describe_images,
    file_title="FILE OR FOLDER",
    kinds=(file_kinds.IMAGE,),
)

# A kind of file in words: (one, several).
KIND_NAMES = {
    file_kinds.VIDEO: ("video", "videos"),
    file_kinds.AUDIO: ("audio file", "audio files"),
    file_kinds.IMAGE: ("image", "images"),
    file_kinds.PDF: ("PDF", "PDFs"),
    file_kinds.DOCUMENT: ("document", "documents"),
    file_kinds.ARCHIVE: ("archive", "archives"),
    file_kinds.OTHER: ("other file", "other"),
}


def _sentence_case(text: str) -> str:
    """First letter up, the rest as is: "PDF" stays "PDF"."""
    return text[:1].upper() + text[1:]


def _count(count: int, one: str, several: str) -> str:
    return f"{count} {one if count == 1 else several}"


def describe_files(path: Path) -> Content:
    """report.pdf · PDF · 2.40 MB · modified 2024-05-01. A folder:
    Downloads · 48 files · 12 folders · 1.20 GB · 30 images, 10 videos, 8 other"""
    from max_cli.core.operations import files

    facts = files.describe(path)
    lines = []
    if facts.is_folder:
        parts = [
            _count(facts.file_count, "file", "files"),
            _count(facts.folder_count, "folder", "folders")
            if facts.folder_count
            else "",
            format_size(facts.size_bytes) if facts.file_count else "",
            ", ".join(
                _count(count, *KIND_NAMES[kind]) for kind, count in facts.kinds.items()
            ),
        ]
    else:
        parts = [
            _sentence_case(KIND_NAMES[facts.kind][0])
            if facts.kind != file_kinds.OTHER
            else "",
            format_size(facts.size_bytes),
            f"modified {facts.modified:%Y-%m-%d %H:%M}" if facts.modified else "",
        ]
    lines.append(
        Content.assemble(
            (facts.path.name or str(facts.path), "bold $primary"),
            (SEPARATOR + SEPARATOR.join(part for part in parts if part), ""),
        )
    )
    if facts.biggest is not None and facts.file_count > 1:
        lines.append(
            Content.assemble(
                ("Biggest: ", "$text-muted"),
                (facts.biggest.name, ""),
                (f" ({format_size(facts.biggest_bytes)})", "$text-muted"),
            )
        )
    if facts.note:
        lines.append(Content.styled(facts.note, "$text-muted"))
    return Content("\n").join(lines)


FILES = ToolPageSpec(
    page_id="files",
    group="files",
    title="FILES",
    tagline="FOLDER CONTROL",
    hint="Sort, clean, back up and undo  ·  Max records what it moves or deletes",
    file_prompt="Pick a folder or a file, or paste its path",
    sections=(
        ToolSection("ORGANIZE", ("order", "smart-sort", "duplicates")),
        ToolSection("LOOK", ("preview", "history")),
        ToolSection("BACKUP & UNDO", ("backup", "backups", "backup-cleanup", "undo")),
        ToolSection("DESTROY", ("shred",)),
    ),
    describe=describe_files,
    file_title="FILE OR FOLDER",
    no_fill=("backups",),
)

TOOL_PAGES = (VIDEO, AUDIO, IMAGES, PDF, FILES)
