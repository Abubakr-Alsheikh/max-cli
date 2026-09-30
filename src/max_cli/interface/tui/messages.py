"""Messages any dashboard page can post to the app."""

from textual.message import Message


class OpenPage(Message):
    """Ask the app to show a page, e.g. from a quick-launch or tool button."""

    def __init__(self, section_id: str) -> None:
        super().__init__()
        self.section_id = section_id
