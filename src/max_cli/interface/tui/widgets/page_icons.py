"""How a page shows in the sidebar and on Home's launchpad: neon codes.

Each page has a colour (the one Home's BY TYPE chart gives its command
group, home_stats.TYPE_LOOK), shown as a thin bar, and a two-digit code
from the key that opens it: `02 DOWNLOAD`. No pictures by default: emoji
clashed with the theme and thin symbols were hard to read, while text and
a bar render the same in every font.

DASHBOARD_ICONS adds a glyph before the name: "nerd" (needs a Nerd Font in
the terminal) or "emoji". "codes", the default, adds none.

Use only the theme's own colour variables here: a custom one breaks when
you switch themes.
"""

from typing import Optional

from textual.content import Content

CODES_STYLE, NERD_STYLE, EMOJI_STYLE = "codes", "nerd", "emoji"
BAR = "▍"  # left three-eighths block: a thin bar in the page's colour
# A page that isn't open shows its bar at this strength, so the open one
# stands out.
DIM = "40%"

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


def page_colour(section_id: str) -> str:
    """The theme colour that marks a page."""
    from max_cli.interface.tui.home_stats import look

    kind = PAGE_KINDS.get(section_id)
    if kind is not None:
        return look(kind).style
    return OTHER_PAGE_COLOURS.get(section_id, "$primary")


def page_code(key: str) -> str:
    """The key as a two-digit code: "2" is "02", "0" is "00", "," is " ,"."""
    return f"0{key}" if key.isdigit() else key.rjust(2)


def page_bar(section_id: str, lit: bool = True) -> Content:
    """The page's colour bar; faded when `lit` is false."""
    colour = page_colour(section_id)
    return Content.styled(BAR, colour if lit else f"{colour} {DIM}")


def page_glyph(section_id: str) -> Optional[Content]:
    """The glyph DASHBOARD_ICONS adds before a page's name, if any."""
    from max_cli.config import settings

    style = settings.DASHBOARD_ICONS
    if style == NERD_STYLE and section_id in NERD_ICONS:
        return Content.styled(NERD_ICONS[section_id], page_colour(section_id))
    if style == EMOJI_STYLE and section_id in EMOJI_ICONS:
        return Content(EMOJI_ICONS[section_id])
    return None
