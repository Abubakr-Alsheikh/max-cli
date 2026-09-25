"""Modal dialogs shared by dashboard pages: a yes/no confirmation and a path picker."""

from pathlib import Path
from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Input, Static


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


class PathPicker(ModalScreen[Optional[Path]]):
    """Browse for a file or folder. Returns the chosen path, or None on cancel."""

    DEFAULT_CSS = """
    PathPicker {
        align: center middle;
    }
    #picker-box {
        width: 80%;
        height: 80%;
        padding: 1 2;
        border: thick $accent;
        background: $surface;
    }
    #picker-tree {
        height: 1fr;
    }
    #picker-buttons {
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, start: Path, pick_folder: bool = False) -> None:
        super().__init__()
        self._start = start if start.is_dir() else Path.home()
        self._pick_folder = pick_folder

    def compose(self) -> ComposeResult:
        what = "folder" if self._pick_folder else "file"
        with Vertical(id="picker-box"):
            yield Static(f"[bold]Choose a {what}[/bold]  [dim](Esc to cancel)[/dim]")
            yield Input(value=str(self._start), id="picker-path")
            yield DirectoryTree(self._start, id="picker-tree")
            with Horizontal(id="picker-buttons"):
                yield Button("Use this path", id="picker-ok", variant="success")
                yield Button("Cancel", id="picker-cancel")

    @on(DirectoryTree.FileSelected)
    def _on_file(self, event: DirectoryTree.FileSelected) -> None:
        self.query_one("#picker-path", Input).value = str(event.path)

    @on(DirectoryTree.DirectorySelected)
    def _on_folder(self, event: DirectoryTree.DirectorySelected) -> None:
        self.query_one("#picker-path", Input).value = str(event.path)

    @on(Input.Submitted, "#picker-path")
    @on(Button.Pressed, "#picker-ok")
    def _on_ok(self) -> None:
        text = self.query_one("#picker-path", Input).value.strip()
        self.dismiss(Path(text).expanduser() if text else None)

    @on(Button.Pressed, "#picker-cancel")
    def _on_cancel(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
