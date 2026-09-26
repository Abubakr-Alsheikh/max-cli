from textual import on
from textual.containers import Vertical
from textual.events import Message
from textual.widgets import Button

SECTIONS = [
    ("home", "\u2302", "Home"),
    ("download", "\u2193", "Download"),
    ("queue", "\u2263", "Queue"),
    ("history", "\u21bb", "History"),
    ("files", "\u25a3", "Files"),
    ("tools", "\u2692", "Tools"),
    ("analytics", "\u2248", "Analytics"),
    ("config", "\u2699", "Config"),
    ("system", "\u25c9", "System"),
    ("chat", "\u2726", "Chat"),
]


class Sidebar(Vertical):
    """Vertical icon sidebar for section navigation."""

    compact: bool = False

    DEFAULT_CSS = """
    Sidebar {
        width: 17;
        layout: vertical;
        background: $surface;
        border-right: solid $border;
    }
    Sidebar.-compact {
        width: 6;
    }
    .sidebar-btn {
        height: 3;
        content-align: center middle;
        padding: 0 1;
        min-width: 0;
        border: none;
        background: transparent;
    }
    .sidebar-btn:hover {
        background: $boost;
    }
    .sidebar-btn.-active {
        background: $boost;
        border-left: heavy $accent;
    }
    """

    def compose(self):
        for section_id, icon, label in SECTIONS:
            text = icon if self.compact else f"{icon} {label}"
            btn = Button(text, id=f"nav-{section_id}", classes="sidebar-btn")
            btn.tooltip = label
            yield btn

    class SectionSelected(Message):
        def __init__(self, section_id: str) -> None:
            super().__init__()
            self.section_id = section_id

    @on(Button.Pressed)
    def _on_nav(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("nav-"):
            section_id = event.button.id[4:]
            self.post_message(self.SectionSelected(section_id=section_id))

    def set_active(self, section_id: str) -> None:
        for btn in self.query(Button):
            btn.remove_class("-active")
        active = self.query_one(f"#nav-{section_id}", Button)
        if active:
            active.add_class("-active")

    def focus_active(self) -> None:
        for btn in self.query(Button):
            if btn.has_class("-active"):
                btn.focus()
                return

    def toggle_mode(self) -> None:
        self.compact = not self.compact
        for btn in self.query(Button):
            if btn.id and btn.id.startswith("nav-"):
                section_id = btn.id[4:]
                for sid, icon, label in SECTIONS:
                    if sid == section_id:
                        text = icon if self.compact else f"{icon} {label}"
                        btn.label = text
                        btn.tooltip = label
                        break
        self.toggle_class("-compact")
