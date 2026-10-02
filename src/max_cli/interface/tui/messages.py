"""Messages any dashboard page can post to the app."""

from pathlib import Path

from textual.message import Message


class OpenPage(Message):
    """Ask the app to show a page, e.g. from a quick-launch or tool button."""

    def __init__(self, section_id: str, tab: str = "") -> None:
        super().__init__()
        self.section_id = section_id
        self.tab = tab  # a page with tabs (Activity) opens this one


class OpenFile(Message):
    """Ask the app to show a command-group page with `path` picked there."""

    def __init__(self, page_id: str, path: Path) -> None:
        super().__init__()
        self.page_id = page_id
        self.path = path
