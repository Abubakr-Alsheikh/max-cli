"""The command-group pages: one ToolPageSpec each (see widgets/tool_page.py).

A test checks that every dashboard action of a page's group sits in exactly
one of its sections, so a new command can't go missing from its page.
"""

from pathlib import Path

from textual.content import Content

from max_cli.common.utils import format_size
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
)

TOOL_PAGES = (VIDEO, PDF)
