"""Modal dialogs shared by dashboard pages: a yes/no confirmation and the help
screen. Browse uses `path_picker.PathPicker`."""

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmDialog(ModalScreen[bool]):
    """Ask before an action moves, overwrites or deletes files. Returns True on yes."""

    DEFAULT_CSS = """
    ConfirmDialog {
        align: center middle;
    }
    #confirm-box {
        width: 60;
        height: auto;
        padding: 1 2;
        border: thick $warning;
        background: $surface;
    }
    #confirm-buttons {
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, question: str) -> None:
        super().__init__()
        self._question = question

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Static(self._question, id="confirm-question")
            with Horizontal(id="confirm-buttons"):
                yield Button("Yes, go ahead", id="confirm-yes", variant="warning")
                yield Button("Cancel", id="confirm-no")

    @on(Button.Pressed, "#confirm-yes")
    def _on_yes(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#confirm-no")
    def _on_no(self) -> None:
        self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)


class HelpScreen(ModalScreen[None]):
    """Every shortcut on one screen. `rows` are (key, what it does) pairs;
    a row with an empty key is a heading."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    #help-box {
        width: 56;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        border: thick $accent;
        background: $surface;
    }
    #help-table {
        height: auto;
        max-height: 30;
    }
    #help-hint {
        margin-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
        ("question_mark", "close", "Close"),
        ("q", "close", "Close"),
    ]

    def __init__(self, rows: list[tuple[str, str]]) -> None:
        super().__init__()
        self._rows = rows

    def compose(self) -> ComposeResult:
        from textual.content import Content

        lines: list[Content] = []
        for key, description in self._rows:
            if not key:
                gap = "\n" if lines else ""  # a blank line between groups
                lines.append(Content.styled(f"{gap}{description}", "bold $accent"))
            else:
                lines.append(
                    Content.assemble((f"  {key:<12}", "bold"), (description, ""))
                )
        with Vertical(id="help-box"):
            yield Static(Content("\n").join(lines), id="help-table")
            yield Static(Content.styled("Esc or ? closes this.", "dim"), id="help-hint")

    def action_close(self) -> None:
        self.dismiss(None)
