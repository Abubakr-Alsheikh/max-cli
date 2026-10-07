"""Modal dialogs shared by dashboard pages: a yes/no confirmation, the AI
agent's questions and plans, and the help screen. Browse uses
`path_picker.PathPicker`."""

from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


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


PLAN_GO = "go"  # what QuestionDialog returns when you approve a plan


class QuestionDialog(ModalScreen[Optional[str]]):
    """The AI agent asks: a plan to approve, or a question with choices.

    A plan returns "go", the changes you type, or None for Stop. A question
    returns the option you press, the answer you type, or None for Cancel.
    """

    DEFAULT_CSS = """
    QuestionDialog {
        align: center middle;
    }
    #question-box {
        width: 72;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #question-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #question-options, #question-buttons {
        height: auto;
        margin-top: 1;
    }
    #question-options Button {
        width: 1fr;
    }
    #question-text {
        margin-top: 1;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, text: str, options: tuple[str, ...] = (), plan: bool = False):
        super().__init__()
        self._text = text
        self._options = options
        self._plan = plan

    def compose(self) -> ComposeResult:
        with Vertical(id="question-box"):
            yield Static(
                "MAX'S PLAN" if self._plan else "MAX ASKS", id="question-title"
            )
            yield Static(Content(self._text), id="question-body")
            if self._options:
                with Horizontal(id="question-options"):
                    for number, option in enumerate(self._options):
                        yield Button(
                            Content(option), id=f"option-{number}", classes="option"
                        )
            yield Input(
                placeholder=(
                    "Or say what to change, then Enter"
                    if self._plan
                    else "Or type your answer, then Enter"
                ),
                id="question-text",
            )
            with Horizontal(id="question-buttons"):
                if self._plan:
                    yield Button("Go ahead", id="question-go", variant="success")
                yield Button("Stop" if self._plan else "Cancel", id="question-cancel")

    def on_mount(self) -> None:
        first = self.query("#question-go, .option")
        if first:
            first.first().focus()

    @on(Button.Pressed, ".option")
    def _on_option(self, event: Button.Pressed) -> None:
        number = int((event.button.id or "option-0").removeprefix("option-"))
        self.dismiss(self._options[number])

    @on(Button.Pressed, "#question-go")
    def _on_go(self) -> None:
        self.dismiss(PLAN_GO)

    @on(Input.Submitted, "#question-text")
    def _on_typed(self, event: Input.Submitted) -> None:
        typed = event.value.strip()
        if typed:
            self.dismiss(typed)

    @on(Button.Pressed, "#question-cancel")
    def action_cancel(self) -> None:
        self.dismiss(None)


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
