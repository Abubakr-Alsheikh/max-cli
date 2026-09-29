"""The page list on the left: grouped, numbered, with live badges.

Starts as a strip of icons; the button at the top expands it to show names.
Each page is a large target (3 rows) that you can click, reach with the
arrow keys and open with Enter, or jump to with its number key (the app
binds those). Badges show what needs attention: running downloads, waiting
tasks, failures you haven't seen. See PLANS/active/dashboard-design-system.md.
"""

from dataclasses import dataclass
from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.events import Click
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Static

# (page id, icon, label), in sidebar order. The number keys follow this order.
# Colour emoji: the thin symbols used before were hard to see, or missing, in
# common Windows terminal fonts.
SECTIONS = [
    ("home", "\U0001f3e0", "Home"),
    ("download", "\U0001f4e5", "Download"),
    ("tools", "\U0001f9f0", "Tools"),
    ("files", "\U0001f4c1", "Files"),
    ("chat", "\U0001f4ac", "Chat"),
    ("queue", "\U0001f4cb", "Queue"),
    ("history", "\U0001f558", "History"),
    ("analytics", "\U0001f4ca", "Analytics"),
    ("config", "\U0001f4dd", "Config"),
    ("system", "\U0001f4bb", "System"),
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
EXPAND_LABEL = "»"
COLLAPSE_LABEL = "«"


@dataclass(frozen=True)
class Badge:
    """A small count next to a page: `kind` picks its colour and symbol."""

    kind: str  # "running", "waiting" or "failed"
    count: int


# ASCII only: symbols like a dot have an ambiguous width, and some fonts draw
# them two columns wide, which pushed the badge into the sidebar's edge.
BADGE_SYMBOLS = {"running": "", "waiting": "", "failed": "!"}
BADGE_COLOURS = {"running": "success", "waiting": "warning", "failed": "error"}


class NavItem(Widget, can_focus=True):
    """One page in the sidebar: 3 rows tall, clickable, focusable."""

    DEFAULT_CSS = """
    NavItem {
        height: 3;
        width: 1fr;
        padding: 0 2;
        content-align: left middle;
        color: $text;
    }
    NavItem:hover {
        background: $boost;
    }
    NavItem:focus {
        background: $boost;
        text-style: bold;
    }
    NavItem.-active {
        background: $primary 25%;
        border-left: outer $accent;
        /* Full padding: a lone padding-left dropped the right padding. The
           border takes one column, so the text stays where it was. */
        padding: 0 2 0 1;
        text-style: bold;
    }
    Sidebar.-compact NavItem {
        padding: 0;
        content-align: center middle;
    }
    Sidebar.-compact NavItem.-active {
        padding: 0;
    }
    """

    class Selected(Message):
        def __init__(self, section_id: str) -> None:
            super().__init__()
            self.section_id = section_id

    BINDINGS = [("enter", "open", "Open"), ("space", "open", "Open")]

    def __init__(self, section_id: str, icon: str, label: str) -> None:
        super().__init__(id=f"nav-{section_id}")
        self.section_id = section_id
        self.icon = icon
        self.label = label
        self.compact = False
        self.badge: Optional[Badge] = None
        self.tooltip = f"{label}  ({SECTION_KEYS[section_id]})"

    def render(self) -> Content:
        badge = ""
        badge_style = ""
        if self.badge is not None:
            badge = f"{BADGE_SYMBOLS[self.badge.kind]}{self.badge.count}"
            badge_style = f"bold ${BADGE_COLOURS[self.badge.kind]}"
        if self.compact:
            return Content.assemble(
                self.icon, (f" {badge}" if badge else "", badge_style)
            )
        name = Content.assemble(
            (f"{SECTION_KEYS[self.section_id]}  ", "dim"), f"{self.icon}  {self.label}"
        )
        # The badge sits against the right padding, so the right margin
        # matches the left one whatever the label's length.
        gap = max(1, self.content_size.width - name.cell_length - len(badge))
        return Content.assemble(name, " " * gap, (badge, badge_style))

    def action_open(self) -> None:
        self.post_message(self.Selected(self.section_id))

    def on_click(self, event: Click) -> None:
        event.stop()
        self.action_open()


class Sidebar(Vertical):
    """Grouped page list; posts SectionSelected when a page is opened."""

    DEFAULT_CSS = """
    Sidebar {
        width: 26;
        layout: vertical;
        background: $surface;
        border-right: solid $border;
    }
    Sidebar.-compact {
        width: 11;
    }
    #sidebar-top {
        height: 3;
        padding: 0 0 0 2;
    }
    Sidebar.-compact #sidebar-top {
        padding: 0;
    }
    #sidebar-brand {
        width: 1fr;
        height: 3;
        content-align: left middle;
        text-style: bold;
        color: $accent;
    }
    Sidebar.-compact #sidebar-brand {
        display: none;
    }
    #sidebar-toggle {
        width: 5;
        min-width: 5;
        height: 3;
        border: none;
        background: transparent;
        text-style: bold;
    }
    #sidebar-toggle:hover {
        background: $boost;
    }
    Sidebar.-compact #sidebar-toggle {
        width: 1fr;
    }
    #sidebar-scroll {
        width: 100%;
        height: 1fr;
        scrollbar-size-vertical: 1;
        scrollbar-background: $surface;
        scrollbar-background-hover: $surface;
        scrollbar-color: $boost;
        scrollbar-color-hover: $accent;
    }
    .sidebar-group {
        height: 1;
        margin: 1 0 0 2;
        color: $text-muted;
        text-style: bold;
    }
    Sidebar.-compact .sidebar-group {
        display: none;
    }
    Sidebar.-compact .sidebar-divider {
        display: block;
    }
    .sidebar-divider {
        display: none;
        height: 1;
        color: $border;
        content-align: center middle;
    }
    #sidebar-help {
        height: 1;
        margin: 1 0 1 2;
        color: $text-muted;
    }
    Sidebar.-compact #sidebar-help {
        margin: 1 0;
        content-align: center middle;
    }
    """

    BINDINGS = [
        ("up", "move(-1)", "Previous page"),
        ("down", "move(1)", "Next page"),
    ]

    class SectionSelected(Message):
        def __init__(self, section_id: str) -> None:
            super().__init__()
            self.section_id = section_id

    class ToggleRequested(Message):
        """The expand/collapse button was pressed."""

    def __init__(self, *, version: str = "", id: Optional[str] = None) -> None:
        super().__init__(id=id)
        self.version = version
        self.compact = False
        self.active = SECTIONS[0][0]
        self._badges: dict[str, Badge] = {}
        self._toggle_enabled = True

    def compose(self) -> ComposeResult:
        with Horizontal(id="sidebar-top"):
            yield Static(f"MAX {self.version}".rstrip(), id="sidebar-brand")
            yield Button(COLLAPSE_LABEL, id="sidebar-toggle")
        with VerticalScroll(id="sidebar-scroll"):
            icons = {section_id: (icon, label) for section_id, icon, label in SECTIONS}
            for position, (group, section_ids) in enumerate(SECTION_GROUPS):
                yield Static(group, classes="sidebar-group")
                if position:
                    yield Static("───", classes="sidebar-divider")
                for section_id in section_ids:
                    icon, label = icons[section_id]
                    yield NavItem(section_id, icon, label)
        yield Static(Content("? Help"), id="sidebar-help")

    def on_mount(self) -> None:
        self._apply_compact()
        self._item(self.active).add_class("-active")

    # --- helpers -----------------------------------------------------------

    def _item(self, section_id: str) -> NavItem:
        return self.query_one(f"#nav-{section_id}", NavItem)

    def _items(self) -> list[NavItem]:
        return list(self.query(NavItem))

    def _apply_compact(self) -> None:
        self.set_class(self.compact, "-compact")
        toggle = self.query_one("#sidebar-toggle", Button)
        toggle.label = EXPAND_LABEL if self.compact else COLLAPSE_LABEL
        if not self._toggle_enabled:
            toggle.tooltip = "Widen the window to show page names"
        else:
            toggle.tooltip = "Show page names" if self.compact else "Icons only"
        toggle.disabled = not self._toggle_enabled
        help_hint = self.query_one("#sidebar-help", Static)
        help_hint.update(Content("?" if self.compact else "? Help   ^B Sidebar"))
        for item in self._items():
            item.compact = self.compact
            item.refresh()

    # --- public API --------------------------------------------------------

    def set_active(self, section_id: str) -> None:
        previous, self.active = self.active, section_id
        if not self.is_mounted:
            return
        self._item(previous).remove_class("-active")
        item = self._item(section_id)
        item.add_class("-active")
        item.scroll_visible(animate=False)

    def set_badge(self, section_id: str, badge: Optional[Badge]) -> None:
        """Show or clear a page's badge. Redraws only when it changes."""
        if badge is not None and badge.count <= 0:
            badge = None
        if badge == self._badges.get(section_id):
            return
        if badge is None:
            self._badges.pop(section_id, None)
        else:
            self._badges[section_id] = badge
        if self.is_mounted:
            item = self._item(section_id)
            item.badge = badge
            item.refresh()

    def badge(self, section_id: str) -> Optional[Badge]:
        return self._badges.get(section_id)

    def set_compact(self, compact: bool, can_expand: bool = True) -> None:
        """Icons only, or icons and names. `can_expand` False greys out the button."""
        if compact == self.compact and can_expand == self._toggle_enabled:
            return
        self.compact = compact
        self._toggle_enabled = can_expand
        if self.is_mounted:
            self._apply_compact()

    def focus_nav(self) -> None:
        if self.is_mounted:
            self._item(self.active).focus()

    def action_move(self, step: int) -> None:
        items = self._items()
        focused = self.app.focused
        current = items.index(focused) if isinstance(focused, NavItem) else 0
        target = items[(current + step) % len(items)]
        target.focus()
        target.scroll_visible(animate=False)

    @on(NavItem.Selected)
    def _on_item_selected(self, event: NavItem.Selected) -> None:
        event.stop()
        self.post_message(self.SectionSelected(event.section_id))

    @on(Button.Pressed, "#sidebar-toggle")
    def _on_toggle(self, event: Button.Pressed) -> None:
        event.stop()
        self.post_message(self.ToggleRequested())
