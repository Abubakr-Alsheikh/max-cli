"""The AI page: tell Max what you want done, and the agent does it.

The agent (`core/agent`) runs in a thread worker. Its steps show as they
happen: groups it looked up, actions it ran and what they made. Before an
action moves, overwrites or deletes files, the worker waits while the page
asks you (ConfirmDialog). The conversation lasts until New chat.

It replaced the Chat page, which only suggested a command to copy.
"""

import threading
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.widgets import Button, Checkbox, Input, Static

from max_cli.interface.tui.activity_log import ActivityLog
from max_cli.interface.tui.messages import OpenPage
from max_cli.interface.tui.widgets.sidebar import SECTION_KEYS

if TYPE_CHECKING:
    from max_cli.core.agent.agent import ActionCall, Agent, AgentReply, Step

EXAMPLES = (
    "Shrink every video in this folder",
    "Merge the PDFs in my Downloads into one",
    "Sort my Music folder into Artist/Album folders",
    "Find duplicate files here",
)
# How often a waiting question checks that the dashboard is still open.
CONFIRM_POLL_SECONDS = 0.5
DANGER_NOTES = {
    "moves": "moves or renames files",
    "overwrites": "overwrites files in place",
    "deletes": "deletes files",
}
STEP_STYLES = {
    "loaded": ("·", "$text-muted"),
    "ran": ("✓", "$success"),
    "failed": ("✗", "$error"),
    "refused": ("!", "$warning"),
    "declined": ("-", "$text-muted"),
    "planned": ("→", "$primary"),
}


def ai_is_set_up() -> bool:
    from max_cli.config import settings

    return bool(settings.OPENAI_API_KEY) or settings.OLLAMA_ENABLED


class AIPanel(Vertical):
    """A conversation with the agent."""

    DEFAULT_CSS = """
    #ai-header {
        height: 3;
        margin-bottom: 1;
    }
    AIPanel .ai-card {
        height: auto;
        background: $surface;
        border: round $border;
        border-title-color: $primary;
        border-title-style: bold;
        padding: 0 1;
        margin-bottom: 1;
    }
    AIPanel .ai-card:focus-within {
        border: round $primary;
    }
    #ai-setup {
        display: none;
        border: round $warning;
    }
    #ai-setup.-shown {
        display: block;
    }
    #ai-setup-row, #ai-input-row, #ai-options, #ai-examples {
        height: auto;
    }
    #ai-setup-text {
        width: 1fr;
        padding-top: 1;
    }
    #ai-log {
        height: auto;
        min-height: 3;
    }
    AIPanel .ai-you {
        margin-top: 1;
        color: $text;
    }
    AIPanel .ai-step {
        padding-left: 2;
    }
    AIPanel .ai-reply {
        margin-top: 1;
    }
    AIPanel .ai-links {
        height: auto;
        margin-top: 1;
    }
    AIPanel .ai-links Button {
        margin-right: 1;
    }
    #ai-examples Button {
        margin-right: 1;
        margin-top: 1;
    }
    #ai-input {
        width: 1fr;
    }
    #ai-dry-run {
        border: none;
        padding: 0;
        margin-top: 1;
        background: transparent;
    }
    #ai-status {
        width: 1fr;
        padding: 1 2;
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._agent: Optional[Agent] = None
        self._tokens = 0
        self._busy = False
        # The "Thinking..." line of the request in progress; steps go above it.
        self._thinking: Optional[Static] = None

    def compose(self) -> ComposeResult:
        yield Static(self._brand(), id="ai-header")
        with Vertical(id="ai-setup", classes="ai-card") as setup:
            setup.border_title = "SET UP"
            with Horizontal(id="ai-setup-row"):
                yield Static(
                    Content.styled(
                        "No AI is set up yet. Add an API key (OpenAI, OpenRouter, "
                        "Gemini) or turn on Ollama on the Settings page.",
                        "$warning",
                    ),
                    id="ai-setup-text",
                )
                yield Button(
                    f"Settings ({SECTION_KEYS['settings']})", id="ai-open-settings"
                )
        with Vertical(id="ai-chat", classes="ai-card") as chat:
            chat.border_title = "CONVERSATION"
            yield Vertical(id="ai-log")
            with Horizontal(id="ai-examples"):
                for index, example in enumerate(EXAMPLES):
                    yield Button(
                        example, id=f"ai-example-{index}", classes="ai-example"
                    )
            with Horizontal(id="ai-input-row"):
                yield Input(
                    placeholder="Say what you want done, e.g. compress the videos here",
                    id="ai-input",
                )
                yield Button("Send", id="ai-send", variant="success")
            with Horizontal(id="ai-options"):
                yield Checkbox(
                    "Dry run: show the steps, change nothing", id="ai-dry-run"
                )
                yield Static("", id="ai-status")
                yield Button("New chat", id="ai-new")

    @staticmethod
    def _brand() -> Content:
        return Content.assemble(
            ("◢◤ ", "bold $secondary"),
            ("AI", "bold $primary"),
            (" // ASK MAX TO DO IT\n", "bold"),
            (
                "It runs Max's own actions  ·  asks before it moves, overwrites or "
                "deletes  ·  works in this folder and folders you name",
                "$text-muted",
            ),
        )

    def on_mount(self) -> None:
        self._show_status()

    def on_show(self) -> None:
        # Settings may have changed since the page last showed.
        self.query_one("#ai-setup").set_class(not ai_is_set_up(), "-shown")

    # --- the conversation ---------------------------------------------------

    def _log(self) -> Vertical:
        return self.query_one("#ai-log", Vertical)

    def _say(self, content: Content, classes: str) -> Static:
        line = Static(content, classes=classes)
        self._log().mount(line)
        self.call_after_refresh(self.scroll_end, animate=False)
        return line

    def _show_status(self) -> None:
        from max_cli.core.engines.ai_engine import chat_model

        parts = [chat_model()]
        if self._tokens:
            parts.append(f"{self._tokens:,} tokens")
        self.query_one("#ai-status", Static).update("  ·  ".join(parts))

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.query_one("#ai-send", Button).disabled = busy
        for button in self.query(".ai-example"):
            button.disabled = busy

    @on(Input.Submitted, "#ai-input")
    @on(Button.Pressed, "#ai-send")
    def _on_send(self) -> None:
        box = self.query_one("#ai-input", Input)
        request = box.value.strip()
        if not request or self._busy:
            return
        box.value = ""
        self.send(request)

    @on(Button.Pressed, ".ai-example")
    def _on_example(self, event: Button.Pressed) -> None:
        event.stop()
        self.send(str(event.button.label))

    def send(self, request: str) -> None:
        """Show the request and hand it to the agent in a thread."""
        self.query_one("#ai-examples").display = False
        self._say(Content.assemble(("You  ", "bold $secondary"), request), "ai-you")
        thinking = self._say(Content.styled("Thinking...", "$text-muted"), "ai-step")
        self._thinking = thinking
        self._set_busy(True)
        dry_run = self.query_one("#ai-dry-run", Checkbox).value
        self.run_worker(
            partial(self._ask_in_thread, request, thinking, dry_run),
            thread=True,
            exclusive=True,
            group="ai-agent",
        )

    def _ask_in_thread(self, request: str, thinking: Static, dry_run: bool) -> None:
        from max_cli.common.exceptions import MaxError
        from max_cli.core.agent.agent import Agent

        activity = ActivityLog()
        entry = activity.start_entry(
            category="ai", action="agent", details={"prompt": request}
        )
        try:
            if self._agent is None:
                self._agent = Agent.from_settings(
                    confirm=self._confirm_from_thread,
                    on_step=self._step_from_thread,
                )
            self._agent.dry_run = dry_run
            reply = self._agent.ask(request)
        except MaxError as e:
            activity.complete_entry(entry, "failed", {"error": str(e)})
            self.app.call_from_thread(self._show_error, thinking, str(e))
            return
        activity.complete_entry(
            entry, "success", {"message": reply.text, "tokens": reply.tokens}
        )
        for step in reply.steps:
            if step.result is not None:
                group, _, name = step.action_id.partition(".")
                activity.add_entry(
                    category=group,
                    action=name,
                    status="success" if step.result.ok else "failed",
                    details={**step.result.to_dict(), "via": "ai"},
                )
        self.app.call_from_thread(self._show_reply, thinking, reply)

    def _step_from_thread(self, step: "Step") -> None:
        self.app.call_from_thread(self._show_step, step)

    def _show_step(self, step: "Step") -> None:
        mark, style = STEP_STYLES.get(step.kind.value, ("·", "$text-muted"))
        line = Static(
            Content.assemble((f"{mark} ", f"bold {style}"), (step.text, style)),
            classes="ai-step",
        )
        # Steps go above the "Thinking..." line, which stays last until the reply.
        self._log().mount(line, before=self._thinking)
        self.call_after_refresh(self.scroll_end, animate=False)

    def _show_reply(self, thinking: Static, reply: "AgentReply") -> None:
        thinking.remove()
        self._tokens += reply.tokens
        self._say(Content.assemble(("Max  ", "bold $primary"), reply.text), "ai-reply")
        self._offer_links(reply)
        self._show_status()
        self._set_busy(False)
        self.query_one("#ai-input", Input).focus()

    def _show_error(self, thinking: Static, message: str) -> None:
        thinking.remove()
        self._say(Content.styled(message, "$error"), "ai-reply")
        self.query_one("#ai-setup").set_class(not ai_is_set_up(), "-shown")
        self._set_busy(False)

    def _offer_links(self, reply: "AgentReply") -> None:
        """Open folder for what the steps made, Undo for what they changed."""
        results = [step.result for step in reply.steps if step.result is not None]
        outputs = [path for result in results for path in result.output_files]
        changed = any(result.undo_group for result in results)
        if not outputs and not changed:
            return
        buttons = []
        if outputs:
            folder = Path(outputs[-1]).parent
            button = Button("Open folder", classes="ai-open-folder")
            button.tooltip = str(folder)
            buttons.append(button)
        if changed:
            buttons.append(Button("Undo...", classes="ai-undo"))
        self._log().mount(Horizontal(*buttons, classes="ai-links"))
        self.call_after_refresh(self.scroll_end, animate=False)

    @on(Button.Pressed, ".ai-open-folder")
    def _on_open_folder(self, event: Button.Pressed) -> None:
        from max_cli.common.utils import open_in_file_manager

        event.stop()
        open_in_file_manager(Path(str(event.button.tooltip)))

    @on(Button.Pressed, ".ai-undo")
    def _on_undo(self, event: Button.Pressed) -> None:
        event.stop()
        self.post_message(OpenPage("activity", tab="undo"))

    @on(Button.Pressed, "#ai-new")
    def _on_new_chat(self) -> None:
        if self._busy:
            return
        self._agent = None
        self._tokens = 0
        self._log().remove_children()
        self.query_one("#ai-examples").display = True
        self._show_status()

    @on(Button.Pressed, "#ai-open-settings")
    def _on_open_settings(self, event: Button.Pressed) -> None:
        event.stop()
        self.post_message(OpenPage("settings"))

    # --- questions from the worker ---------------------------------------------

    def _confirm_from_thread(self, call: "ActionCall") -> bool:
        """Runs in the worker: ask on the UI thread and wait for the answer.

        No answer counts as no: the dashboard closing stops the wait.
        """
        from max_cli.interface.tui.widgets.dialogs import ConfirmDialog

        answer: list[bool] = []
        answered = threading.Event()

        def done(yes: Optional[bool]) -> None:
            answer.append(bool(yes))
            answered.set()

        note = DANGER_NOTES.get(call.action.danger.value, "changes files")
        question = f"Max wants to run: {call.describe()}\nIt {note}. Go ahead?"
        # Build the dialog on the UI thread: on Python 3.9 a widget made in a
        # worker thread fails, as that thread has no event loop.
        self.app.call_from_thread(
            lambda: self.app.push_screen(ConfirmDialog(question), done)
        )
        while not answered.wait(CONFIRM_POLL_SECONDS):
            if not self.app.is_running:
                return False
        return answer[0]
