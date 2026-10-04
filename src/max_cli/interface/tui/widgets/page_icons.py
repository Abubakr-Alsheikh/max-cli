"""Each page's icon and colour, for the sidebar and Home's launchpad.

The default icons are pixel art: ICON_PIXELS by ICON_PIXELS pixels, two to a
character cell, drawn with the half blocks every terminal font has (top
pixel, bottom pixel, both; two colours through foreground and background).
So they need no special font, and they come out square: a cell is about
twice as tall as it is wide.

A page draws in its own colour, the one Home's BY TYPE chart gives its
command group (home_stats.TYPE_LOOK), so a page looks the same everywhere.
Use only the theme's own colour variables here: a custom one breaks when
you switch themes.

DASHBOARD_ICONS picks the style: "pixel" (the default), "nerd" (a Nerd Font
glyph, which needs a Nerd Font in the terminal) or "emoji".
"""

from textual.content import Content

ICON_PIXELS = 6
ICON_COLUMNS = ICON_PIXELS
ICON_ROWS = ICON_PIXELS // 2  # text rows
PIXEL_STYLE, NERD_STYLE, EMOJI_STYLE = "pixel", "nerd", "emoji"

# "a" is the page's colour, "b" a white highlight, "." empty.
HIGHLIGHT = "$foreground"
# A page that isn't open shows its icon at this strength, so the open one
# stands out and the sidebar stays calm.
DIM = "60%"
PIXEL_ICONS: dict[str, tuple[str, ...]] = {
    "home": (
        "..aa..",
        ".aaaa.",
        "aaaaaa",
        ".aaaa.",
        ".abaa.",
        ".abaa.",
    ),
    "download": (
        "..aa..",
        "..aa..",
        "aaaaaa",
        ".aaaa.",
        "..aa..",
        "bbbbbb",
    ),
    "video": (
        ".aaaa.",
        "aabaaa",
        "aabbaa",
        "aabbaa",
        "aabaaa",
        ".aaaa.",
    ),
    "audio": (
        "..bbbb",
        "..a..a",
        "..a..a",
        ".aa.aa",
        "aaaaaa",
        "aa.aa.",
    ),
    "images": (
        "aaaaaa",
        "a...ba",
        "a.a..a",
        "aaaa.a",
        "aaaaaa",
        "......",
    ),
    "pdf": (
        "aaaa..",
        "a..aa.",
        "abb.aa",
        "a....a",
        "abbbba",
        "aaaaaa",
    ),
    "files": (
        "aaa...",
        "abbbbb",
        "aaaaaa",
        "aaaaaa",
        "aaaaaa",
        "......",
    ),
    "ai": (
        "..a..b",
        "..a...",
        "aabaa.",
        "..a...",
        "..a...",
        "......",
    ),
    "activity": (
        ".....a",
        "...a.a",
        "...a.a",
        ".a.a.a",
        ".a.a.a",
        "bbbbbb",
    ),
    "extras": (
        "..aa..",
        "..aa..",
        "aabbaa",
        "aabbaa",
        "..aa..",
        "..aa..",
    ),
    "settings": (
        "..aa..",
        "aaaaaa",
        ".ab.a.",
        ".a.ba.",
        "aaaaaa",
        "..aa..",
    ),
}
# The same pages in Nerd Font icons (Material Design glyphs).
NERD_ICONS = {
    "home": "\U000f02dc",
    "download": "\U000f01da",
    "video": "\U000f0567",
    "audio": "\U000f0387",
    "images": "\U000f02e9",
    "pdf": "\U000f0226",
    "files": "\U000f024b",
    "ai": "\U000f06a9",
    "activity": "\U000f02da",
    "extras": "\U000f09ac",
    "settings": "\U000f0493",
}
EMOJI_ICONS = {
    "home": "\U0001f3e0",
    "download": "\U0001f4e5",
    "video": "\U0001f3ac",
    "audio": "\U0001f3b5",
    "images": "\U0001f4f7",
    "pdf": "\U0001f4c4",
    "files": "\U0001f4c1",
    "ai": "\U0001f916",
    "activity": "\U0001f4cb",
    "extras": "\U0001f9f0",
    "settings": "\U0001f527",
}
# A page's colour: a command group's comes from home_stats.TYPE_LOOK.
PAGE_KINDS = {
    "download": "download",
    "video": "video",
    "audio": "audio",
    "images": "images",
    "pdf": "pdf",
    "files": "files",
    "ai": "ai",
    "extras": "tools",
}
OTHER_PAGE_COLOURS = {
    "home": "$primary-lighten-2",
    "activity": "$success-darken-1",
    "settings": "$secondary-darken-2",
}
UPPER_HALF, LOWER_HALF, FULL_BLOCK = "▀", "▄", "█"


def page_colour(section_id: str) -> str:
    """The theme colour that marks a page."""
    from max_cli.interface.tui.home_stats import look

    kind = PAGE_KINDS.get(section_id)
    if kind is not None:
        return look(kind).style
    return OTHER_PAGE_COLOURS.get(section_id, "$primary")


def page_icon(section_id: str, dim: bool = False) -> list[Content]:
    """The page's icon in the style DASHBOARD_ICONS picks: ICON_ROWS lines
    of ICON_COLUMNS cells each, whatever the style, so labels line up.
    `dim` draws it at DIM strength."""
    from max_cli.config import settings

    style = settings.DASHBOARD_ICONS
    colour = page_colour(section_id)
    strength = f" {DIM}" if dim else ""
    if style == NERD_STYLE and section_id in NERD_ICONS:
        return _one_glyph(
            Content.styled(NERD_ICONS[section_id], f"bold {colour}{strength}")
        )
    if style == EMOJI_STYLE and section_id in EMOJI_ICONS:
        return _one_glyph(Content(EMOJI_ICONS[section_id]))
    return draw(PIXEL_ICONS.get(section_id, ()), colour, strength)


def draw(pixels: tuple[str, ...], colour: str, strength: str = "") -> list[Content]:
    """Pixel rows as half-block text: each cell shows a top and a bottom
    pixel, in `colour` ("a") or the highlight ("b"); "." stays empty.
    `strength` (" 45%") fades both."""
    palette = {"a": f"{colour}{strength}", "b": f"{HIGHLIGHT}{strength}"}
    rows = list(pixels) + ["." * ICON_COLUMNS] * (ICON_PIXELS - len(pixels))
    lines = []
    for top_row, bottom_row in zip(rows[::2], rows[1::2]):
        cells = [
            _cell(palette.get(top), palette.get(bottom))
            for top, bottom in zip(top_row.ljust(ICON_COLUMNS, "."), bottom_row)
        ]
        lines.append(Content.assemble(*cells))
    return lines


def _cell(top: "str | None", bottom: "str | None") -> "tuple[str, str] | str":
    if top is None and bottom is None:
        return " "
    if bottom is None:
        return (UPPER_HALF, str(top))
    if top is None:
        return (LOWER_HALF, bottom)
    if top == bottom:
        return (FULL_BLOCK, top)
    return (UPPER_HALF, f"{top} on {bottom}")


def _one_glyph(glyph: Content) -> list[Content]:
    """A single glyph on the middle row, centred in the icon's cells."""
    blank = Content(" " * ICON_COLUMNS)
    left = (ICON_COLUMNS - glyph.cell_length) // 2
    middle = Content.assemble(
        " " * left, glyph, " " * (ICON_COLUMNS - left - glyph.cell_length)
    )
    lines = [blank] * ICON_ROWS
    lines[ICON_ROWS // 2] = middle
    return lines
