"""The page list on the left: grouped, numbered, with live badges.

Arrow keys move, Enter or a click opens a page, and a page's number key jumps
straight to it (the app binds the keys). Badges show what needs attention:
running downloads, waiting tasks, failures you haven't seen.
See PLANS/active/dashboard-design-system.md.
"""

from dataclasses import dataclass
from typing import Optional

from textual import on
from textual.containers import Vertical
from textual.content import Content
from textual.events import Message
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

# (page id, icon, label), in sidebar order. The number keys follow this order.
SECTIONS = [
    ("home", "⌂", "Home"),
    ("download", "↓", "Download"),
    ("tools", "⚒", "Tools"),
    ("files", "▣", "Files"),
    ("chat", "✦", "Chat"),
    ("queue", "≣", "Queue"),
    ("history", "↻", "History"),
    ("analytics", "≈", "Analytics"),
    ("config", "⚙", "Config"),
    ("system", "◉", "System"),
]
SECTION_GROUPS = (
    ("DO", ("home", "download", "tools", "files", "chat")),
    ("TRACK", ("queue", "history", "analytics")),
    ("SETUP", ("config", "system")),
)
# Page id -> its number key: 1 to 9, then 0 for the tenth.
SECTION_KEYS = {
    section_id: str((position + 1) % 10)
    for position, (section_id, _icon, _label) in enumerate(SECTIONS)
}
LABEL_WIDTH = 9
ACTIVE_MARK = "▌"


@dataclass(frozen=True)
class Badge:
    """A small count next to a page: `kind` picks its colour and symbol."""

    kind: str  # "running", "waiting" or "failed"
    count: int


BADGE_SYMBOLS = {"running": "●", "waiting": "", "failed": "!"}
BADGE_COLOURS = {"running": "success", "waiting": "warning", "failed": "error"}


class Sidebar(Vertical):
    """Grouped page list; posts SectionSelected when a page is opened."""

    DEFAULT_CSS = """
    Sidebar {
        width: 22;
        layout: vertical;
        background: $surface;
        border-right: solid $border;
    }
    Sidebar.-compact {
        width: 7;
    }
    #sidebar-brand {
        height: 1;
        margin: 1 1 1 1;
        text-style: bold;
        color: $accent;
    }
    #sidebar-nav {
        height: 1fr;
        border: none;
        background: $surface;
        padding: 0;
    }
    #sidebar-nav > .option-list--option-highlighted {
        background: $boost;
        text-style: none;
    }
    #sidebar-nav:focus > .option-list--option-highlighted {
        background: $boost;
    }
    #sidebar-help {
        height: 1;
        margin: 1 1;
        color: $text-muted;
    }
    """

    class SectionSelected(Message):
        def __init__(self, section_id: str) -> None:
            super().__init__()
            self.section_id = section_id

    def __init__(self, *, version: str = "", id: Optional[str] = None) -> None:
        super().__init__(id=id)
        self.version = version
        self.compact = False
        self.active = SECTIONS[0][0]
        self._badges: dict[str, Badge] = {}

    def compose(self):
        yield Static(self._brand(), id="sidebar-brand")
        yield OptionList(*self._options(), id="sidebar-nav")
        yield Static(self._help_hint(), id="sidebar-help")

    # --- rendering -------------------------------------------------------

    def _brand(self) -> str:
        if self.compact:
            return "MAX"
        return f"MAX {self.version}".rstrip()

    def _help_hint(self) -> Content:
        text = "?" if self.compact else "? Help  ^P Menu"
        return Content(text)

    def _options(self) -> list[Option]:
        options = []
        for position, (group, section_ids) in enumerate(SECTION_GROUPS):
            if position:
                # A blank row between groups.
                options.append(Option("", id=f"gap-{group}", disabled=True))
            heading = "" if self.compact else group
            options.append(
                Option(
                    Content.styled(heading, "dim bold"),
                    id=f"group-{group}",
                    disabled=True,
                )
            )
            options.extend(
                Option(self._prompt(section_id), id=section_id)
                for section_id in section_ids
            )
        return options

    def _prompt(self, section_id: str) -> Content:
        icon, label = next(
            (icon, label) for sid, icon, label in SECTIONS if sid == section_id
        )
        mark = ACTIVE_MARK if section_id == self.active else " "
        parts: list = [(mark, "bold $accent")]
        if self.compact:
            parts.append((icon, "bold" if section_id == self.active else ""))
        else:
            parts.append((f"{SECTION_KEYS[section_id]} ", "dim"))
            parts.append(
                (
                    f"{icon} {label:<{LABEL_WIDTH}}",
                    "bold" if section_id == self.active else "",
                )
            )
        badge = self._badges.get(section_id)
        if badge is not None and badge.count > 0:
            text = f"{BADGE_SYMBOLS[badge.kind]}{badge.count}"
            parts.append(
                (
                    text if self.compact else f" {text}",
                    f"bold ${BADGE_COLOURS[badge.kind]}",
                )
            )
        return Content.assemble(*parts)

    def _redraw(self, section_id: str) -> None:
        nav = self.query_one("#sidebar-nav", OptionList)
        nav.replace_option_prompt(section_id, self._prompt(section_id))

    # --- public API --------------------------------------------------------

    def set_active(self, section_id: str) -> None:
        previous, self.active = self.active, section_id
        if not self.is_mounted:
            return
        self._redraw(previous)
        self._redraw(section_id)
        nav = self.query_one("#sidebar-nav", OptionList)
        nav.highlighted = nav.get_option_index(section_id)

    def set_badge(self, section_id: str, badge: Optional[Badge]) -> None:
        """Show or clear a page's badge. Redraws only when it changes."""
        current = self._badges.get(section_id)
        if badge is not None and badge.count <= 0:
            badge = None
        if badge == current:
            return
        if badge is None:
            self._badges.pop(section_id, None)
        else:
            self._badges[section_id] = badge
        if self.is_mounted:
            self._redraw(section_id)

    def badge(self, section_id: str) -> Optional[Badge]:
        return self._badges.get(section_id)

    def set_compact(self, compact: bool) -> None:
        if compact == self.compact:
            return
        self.compact = compact
        self.set_class(compact, "-compact")
        if not self.is_mounted:
            return
        self.query_one("#sidebar-brand", Static).update(self._brand())
        self.query_one("#sidebar-help", Static).update(self._help_hint())
        nav = self.query_one("#sidebar-nav", OptionList)
        nav.clear_options()
        nav.add_options(self._options())
        nav.highlighted = nav.get_option_index(self.active)

    def focus_nav(self) -> None:
        self.query_one("#sidebar-nav", OptionList).focus()

    @on(OptionList.OptionSelected, "#sidebar-nav")
    def _on_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if event.option.id:
            self.post_message(self.SectionSelected(event.option.id))
