"""The AI agent's notes (core/agent/memory.py) on the dashboard: read them,
add one, delete one. The AI page's Notes button opens it; every request the
agent starts reads the notes again, so a change counts from the next one."""

from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from max_cli.common.exceptions import MaxError
from max_cli.core.agent.memory import AgentMemory

NOTE_ID_PREFIX = "note-"


class NotesDialog(ModalScreen[None]):
    DEFAULT_CSS = """
    NotesDialog {
        align: center middle;
    }
    #notes-box {
        width: 80;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #notes-title {
        text-style: bold;
        color: $primary;
    }
    #notes-help {
        color: $text-muted;
        margin-bottom: 1;
    }
    #notes-list {
        height: auto;
        max-height: 20;
    }
    .note-row {
        height: auto;
        margin-bottom: 1;
    }
    .note-text {
        width: 1fr;
    }
    .note-delete {
        height: 1;
        min-width: 8;
        border: none;
        padding: 0 1;
    }
    #notes-empty {
        color: $text-muted;
        margin-bottom: 1;
    }
    #notes-buttons {
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [("escape", "close", "Close")]

    def __init__(self, memory: Optional[AgentMemory] = None) -> None:
        super().__init__()
        self._memory = memory or AgentMemory()

    def compose(self) -> ComposeResult:
        with Vertical(id="notes-box"):
            yield Static("MAX'S NOTES", id="notes-title")
            yield Static(
                "Facts and preferences the agent keeps between chats. It saves one "
                "when you tell it something lasting; you can add or delete them here.",
                id="notes-help",
            )
            yield VerticalScroll(id="notes-list")
            yield Input(placeholder="Add a note, then Enter", id="notes-new")
            with Horizontal(id="notes-buttons"):
                yield Button("Close", id="notes-close")

    async def on_mount(self) -> None:
        await self._fill()
        self.query_one("#notes-new", Input).focus()

    async def _fill(self) -> None:
        notes_list = self.query_one("#notes-list", VerticalScroll)
        await notes_list.remove_children()
        notes = self._memory.notes()
        if not notes:
            await notes_list.mount(
                Static(
                    'No notes yet. Tell the agent something like "remember that my '
                    'music lives in D:/Music", or add one below.',
                    id="notes-empty",
                )
            )
            return
        await notes_list.mount_all(
            Horizontal(
                Static(Content(note.text), classes="note-text"),
                Button(
                    "Delete", id=f"{NOTE_ID_PREFIX}{note.id}", classes="note-delete"
                ),
                classes="note-row",
            )
            for note in notes
        )

    @on(Input.Submitted, "#notes-new")
    async def _on_add(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        try:
            self._memory.remember(text)
        except MaxError as e:
            self.notify(str(e), severity="error")
            return
        event.input.value = ""
        await self._fill()

    @on(Button.Pressed, ".note-delete")
    async def _on_delete(self, event: Button.Pressed) -> None:
        note_id = (event.button.id or "").removeprefix(NOTE_ID_PREFIX)
        self._memory.forget(note_id)
        await self._fill()

    @on(Button.Pressed, "#notes-close")
    def action_close(self) -> None:
        self.dismiss(None)
