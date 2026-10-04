"""The AI page: tell Max what you want done, and the agent does it.

The agent (`core/agent`) runs in a thread worker. The conversation scrolls
on its own, so the input below it stays in view. Each answer is an
`AgentTurn`: a status line with a spinner while it works, one `ToolCard`
per action (running, then done or failed; expand it for the arguments, the
result and the files it made), then the reply rendered as Markdown. Before
an action moves, overwrites or deletes files, the worker waits while the
page asks you (ConfirmDialog). The conversation lasts until New chat.

It replaced the Chat page, which only suggested a command to copy.
"""

import threading
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.events import Key
from textual.timer import Timer
from textual.widgets import Button, Checkbox, Collapsible, Input, Markdown, Static

from max_cli.interface.tui.messages import OpenPage
from max_cli.interface.tui.widgets.sidebar import SECTION_KEYS

if TYPE_CHECKING:
    from max_cli.core.agent.agent import ActionCall, Agent, AgentReply, Step

EXAMPLES = (
    "Shrink the videos in this folder",
    "Merge the PDFs in my Downloads",
    "Sort my Music into Artist/Album",
    "Find duplicate files here",
)
# How often a waiting question checks that the dashboard is still open.
CONFIRM_POLL_SECONDS = 0.5
SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
SPINNER_SECONDS = 0.1
# Quicker actions don't show how long they took.
MIN_SHOWN_SECONDS = 0.1
# Below this width the examples stack in one column.
TWO_COLUMN_MIN_WIDTH = 70
DANGER_NOTES = {
    "moves": "moves or renames files",
    "overwrites": "overwrites files in place",
    "deletes": "deletes files",
}
# Step kind -> (mark, ToolCard class) for the action cards.
CARD_STATES = {
    "started": ("", "-running"),
    "ran": ("✓", "-ok"),
    "failed": ("✗", "-failed"),
    "refused": ("!", "-refused"),
    "declined": ("-", "-skipped"),
    "planned": ("→", "-planned"),
    "queued": ("⧗", "-queued"),
}
CARD_NOTES = {
    "refused": "outside the folders Max may use",
    "declined": "you said no",
    "planned": "dry run, not run",
    "queued": "queued, J shows its progress",
}


def ai_is_set_up() -> bool:
    """The main provider or the fallback has a key (Ollama needs none)."""
    from max_cli.core.engines.ai_providers import provider_chain

    return bool(provider_chain())


class ToolCard(Collapsible):
    """One action the agent ran: its name and outcome on the title line;
    expanded, its arguments, its result and the files it made."""

    DEFAULT_CSS = """
    ToolCard {
        height: auto;
        background: $boost;
        border: none;
        border-left: wide $primary 50%;
        padding: 0;
        margin: 0 0 1 0;
    }
    ToolCard > CollapsibleTitle {
        padding: 0 1;
        text-style: bold;
    }
    ToolCard > Contents {
        padding: 0 2 1 3;
    }
    ToolCard.-running { border-left: wide $accent; }
    ToolCard.-running > CollapsibleTitle { color: $accent; }
    ToolCard.-ok { border-left: wide $success; }
    ToolCard.-ok > CollapsibleTitle { color: $success; }
    ToolCard.-failed { border-left: wide $error; }
    ToolCard.-failed > CollapsibleTitle { color: $error; }
    ToolCard.-refused, ToolCard.-planned { border-left: wide $warning; }
    ToolCard.-refused > CollapsibleTitle { color: $warning; }
    ToolCard.-planned > CollapsibleTitle { color: $primary; }
    ToolCard.-queued { border-left: wide $primary; }
    ToolCard.-queued > CollapsibleTitle { color: $primary; }
    ToolCard.-skipped { border-left: wide $text-muted; }
    ToolCard.-skipped > CollapsibleTitle { color: $text-muted; }
    """

    def __init__(self, step: "Step") -> None:
        self._body = Static("", classes="tool-body")
        super().__init__(self._body, title=step.label, collapsed=True)
        self.action_id = step.action_id
        self.label = step.label
        self.state = ""
        self.show(step)

    def show(self, step: "Step", spinner: str = "") -> None:
        kind = step.kind.value
        mark, state = CARD_STATES.get(kind, ("·", ""))
        if self.state:
            self.remove_class(self.state)
        self.state = state
        self.add_class(state)
        self.title = self._title_text(step, spinner or mark)
        self._body.update(self._details_text(step))

    def spin(self, frame: str) -> None:
        """The running card's title with the spinner's next frame."""
        if self.state == "-running":
            self.title = f"{frame} {self.label}  running…"

    @staticmethod
    def _title_text(step: "Step", mark: str) -> str:
        kind = step.kind.value
        if kind == "started":
            return f"{mark} {step.label}  running…"
        if kind in CARD_NOTES:
            return f"{mark} {step.label}  ·  {CARD_NOTES[kind]}"
        message = (
            step.result.message
            if step.result is not None
            else step.text.removeprefix(f"{step.label}: ")
        )
        took = f"  ·  {step.seconds:.1f}s" if step.seconds >= MIN_SHOWN_SECONDS else ""
        return f"{mark} {step.label}  ·  {message}{took}"

    @staticmethod
    def _details_text(step: "Step") -> Content:
        lines = [
            Content.assemble((f"{name:<10} ", "$text-muted"), value)
            for name, value in step.arguments.items()
        ]
        # The outcome is on the title line; the body adds what it made.
        if step.result is not None:
            lines += [
                Content.assemble(("→ ", "$text-muted"), str(path))
                for path in step.result.output_files
            ]
        return Content("\n").join(lines) if lines else Content("")


class AgentTurn(Vertical):
    """Max's answer to one request: status, action cards, then the reply."""

    DEFAULT_CSS = """
    AgentTurn {
        height: auto;
        margin: 1 0 0 0;
        padding: 0 0 0 1;
        border-left: thick $primary;
    }
    AgentTurn .turn-status {
        height: 1;
        margin-bottom: 1;
    }
    AgentTurn .turn-lookups {
        color: $text-muted;
        margin-bottom: 1;
    }
    AgentTurn .turn-tools {
        height: auto;
    }
    AgentTurn Markdown {
        margin: 0;
        padding: 0 1 0 0;
        background: transparent;
    }
    AgentTurn .turn-error {
        color: $error;
    }
    AgentTurn .turn-links {
        height: auto;
        margin-top: 1;
    }
    AgentTurn .turn-links Button {
        margin-right: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._frame = 0
        self._doing = "Thinking"
        self._timer: Optional[Timer] = None
        self._cards: dict[str, ToolCard] = {}
        self._lookups: list[str] = []

    def compose(self) -> ComposeResult:
        yield Static("", classes="turn-status")
        yield Static("", classes="turn-lookups")
        yield Vertical(classes="turn-tools")

    def on_mount(self) -> None:
        self.query_one(".turn-lookups").display = False
        self._timer = self.set_interval(SPINNER_SECONDS, self._tick)
        self._tick()

    def _tick(self) -> None:
        frame = SPINNER_FRAMES[self._frame % len(SPINNER_FRAMES)]
        self._frame += 1
        self.query_one(".turn-status", Static).update(
            Content.assemble(
                ("Max  ", "bold $primary"),
                (f"{frame} {self._doing}…", "$text-muted"),
            )
        )
        for card in self._cards.values():
            card.spin(frame)

    def waiting(self, doing: str) -> None:
        self._doing = doing

    def add_step(self, step: "Step") -> None:
        kind = step.kind.value
        if kind in ("loaded", "looked"):
            # What it read before acting: folders, files, a group's actions.
            self._lookups.append(
                f"{step.action_id} actions" if kind == "loaded" else step.text
            )
            lookups = self.query_one(".turn-lookups", Static)
            lookups.update("· " + "  ·  ".join(self._lookups))
            lookups.display = True
            return
        # By tool call: actions run side by side and finish in any order.
        key = step.call_id or step.action_id
        card = self._cards.get(key)
        if kind == "started" or card is None or card.state != "-running":
            card = ToolCard(step)
            self._cards[key] = card
            self.query_one(".turn-tools").mount(card)
        else:
            card.show(step)
        running = sum(card.state == "-running" for card in self._cards.values())
        self._doing = {0: "Thinking", 1: f"Running {step.label}"}.get(
            running, f"Running {running} actions"
        )

    def _stop(self, summary: Content) -> None:
        if self._timer is not None:
            self._timer.stop()
        self.query_one(".turn-status", Static).update(summary)

    def finish(self, reply: "AgentReply") -> None:
        self._stop(
            Content.assemble(
                ("Max  ", "bold $primary"),
                (reply.facts().replace(" · ", "  ·  "), "$text-muted"),
            )
        )
        self.mount(Markdown(reply.text))
        self._offer_links(reply)

    def fail(self, message: str) -> None:
        self._stop(Content.styled("Max", "bold $primary"))
        self.mount(Static(Content(message), classes="turn-error"))

    def _offer_links(self, reply: "AgentReply") -> None:
        """Open folder for what the steps made, Undo for what they changed."""
        results = [step.result for step in reply.steps if step.result is not None]
        outputs = [path for result in results for path in result.output_files]
        changed = any(result.undo_group for result in results)
        buttons = []
        if outputs:
            button = Button("Open folder", classes="ai-open-folder")
            button.tooltip = str(Path(outputs[-1]).parent)
            buttons.append(button)
        if changed:
            buttons.append(Button("Undo...", classes="ai-undo"))
        if buttons:
            self.mount(Horizontal(*buttons, classes="turn-links"))


class AIPanel(Vertical):
    """A conversation with the agent."""

    DEFAULT_CSS = """
    #ai-header {
        height: 3;
        margin-bottom: 1;
    }
    AIPanel .ai-card {
        background: $surface;
        border: round $border;
        border-title-color: $primary;
        border-title-style: bold;
        padding: 0 1;
    }
    AIPanel .ai-card:focus-within {
        border: round $primary;
    }
    #ai-setup {
        display: none;
        height: auto;
        margin-bottom: 1;
        border: round $warning;
    }
    #ai-setup.-shown {
        display: block;
    }
    #ai-setup-row, #ai-input-row, #ai-options {
        height: auto;
    }
    #ai-setup-text {
        width: 1fr;
        padding-top: 1;
    }
    #ai-chat {
        height: 1fr;
    }
    #ai-log {
        height: 1fr;
        scrollbar-size-vertical: 1;
    }
    #ai-empty {
        height: auto;
        padding: 1 0;
    }
    #ai-empty-text {
        color: $text-muted;
        margin-bottom: 1;
    }
    #ai-examples {
        height: auto;
        grid-size: 2;
        grid-gutter: 0 1;
        grid-rows: 3;
    }
    #ai-examples Button {
        width: 100%;
    }
    AIPanel .ai-you {
        height: auto;
        margin-top: 1;
        padding: 0 1;
        background: $boost;
        border-left: thick $secondary;
    }
    #ai-input-row {
        margin-top: 1;
    }
    #ai-input {
        width: 1fr;
    }
    #ai-dry-run {
        border: none;
        padding: 0;
        background: transparent;
    }
    #ai-status {
        width: 1fr;
        padding: 0 2;
        color: $text-muted;
        content-align: right middle;
    }
    #ai-new {
        height: 1;
        min-width: 12;
        border: none;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._agent: Optional[Agent] = None
        self._tokens = 0
        self._busy = False
        self._turn: Optional[AgentTurn] = None
        self._sent: list[str] = []  # requests, for up and down in the input
        self._recall = -1

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
            with VerticalScroll(id="ai-log"):
                with Vertical(id="ai-empty"):
                    yield Static(
                        "Say what you want done in your own words. Max picks its "
                        "own actions, shows each one as it runs, and asks before "
                        "it moves, overwrites or deletes anything. For example:",
                        id="ai-empty-text",
                    )
                    with Grid(id="ai-examples"):
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
                yield Checkbox("Dry run (change nothing)", id="ai-dry-run")
                yield Static("", id="ai-status")
                yield Button("New chat", id="ai-new")

    @staticmethod
    def _brand() -> Content:
        return Content.assemble(
            ("◢◤ ", "bold $secondary"),
            ("AI", "bold $primary"),
            (" // ASK MAX TO DO IT\n", "bold"),
            (
                "Runs Max's own actions  ·  asks before changing files  ·  "
                "stays in folders you name",
                "$text-muted",
            ),
        )

    def on_mount(self) -> None:
        self._show_status()

    def on_show(self) -> None:
        # Settings may have changed since the page last showed.
        self.query_one("#ai-setup").set_class(not ai_is_set_up(), "-shown")
        self.query_one("#ai-input", Input).focus()

    def on_resize(self) -> None:
        columns = 2 if self.size.width >= TWO_COLUMN_MIN_WIDTH else 1
        grid = self.query_one("#ai-examples", Grid)
        if grid.styles.grid_size_columns != columns:
            grid.styles.grid_size_columns = columns

    # --- the conversation ---------------------------------------------------

    def _log(self) -> VerticalScroll:
        return self.query_one("#ai-log", VerticalScroll)

    def _to_bottom(self) -> None:
        self.call_after_refresh(self._log().scroll_end, animate=False)

    def _show_status(self) -> None:
        from max_cli.core.engines.ai_providers import chat_model

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

    def on_key(self, event: Key) -> None:
        """Up and down in the input bring back earlier requests."""
        box = self.query_one("#ai-input", Input)
        if self.app.focused is not box or not self._sent:
            return
        if event.key == "up":
            self._recall = (
                len(self._sent) - 1 if self._recall < 0 else max(0, self._recall - 1)
            )
        elif event.key == "down" and self._recall >= 0:
            self._recall += 1
            if self._recall >= len(self._sent):
                self._recall = -1
                box.value = ""
                event.stop()
                return
        else:
            return
        event.stop()
        box.value = self._sent[self._recall]
        box.cursor_position = len(box.value)

    @on(Button.Pressed, ".ai-example")
    def _on_example(self, event: Button.Pressed) -> None:
        event.stop()
        self.send(str(event.button.label))

    def ask_from(self, request: str) -> None:
        """A request typed on another page (Home): send it now, or, when the
        AI isn't set up or is busy, leave it in the box to send later."""
        if self._busy or not ai_is_set_up():
            box = self.query_one("#ai-input", Input)
            box.value = request
            box.cursor_position = len(request)
            box.focus()
            return
        self.send(request)

    def send(self, request: str) -> None:
        """Show the request and hand it to the agent in a thread."""
        self._sent.append(request)
        self._recall = -1
        self.query_one("#ai-empty").display = False
        log = self._log()
        log.mount(
            Static(
                Content.assemble(("You\n", "bold $secondary"), request),
                classes="ai-you",
            )
        )
        turn = AgentTurn()
        self._turn = turn
        log.mount(turn)
        self._to_bottom()
        self._set_busy(True)
        dry_run = self.query_one("#ai-dry-run", Checkbox).value
        self.run_worker(
            partial(self._ask_in_thread, request, turn, dry_run),
            thread=True,
            exclusive=True,
            group="ai-agent",
        )

    def _ask_in_thread(self, request: str, turn: AgentTurn, dry_run: bool) -> None:
        from max_cli.common.exceptions import MaxError
        from max_cli.core.agent.agent import Agent

        try:
            if self._agent is None:
                # The dashboard runs the queue, so long jobs may wait there.
                self._agent = Agent.from_settings(
                    confirm=self._confirm_from_thread,
                    on_step=self._step_from_thread,
                    can_queue=True,
                )
            self._agent.dry_run = dry_run
            reply = self._agent.ask(request)
        except MaxError as e:
            self.app.call_from_thread(self._show_error, turn, str(e))
            return
        # The agent logs the request and each action to Activity itself.
        self.app.call_from_thread(self._show_reply, turn, reply)

    def _step_from_thread(self, step: "Step") -> None:
        self.app.call_from_thread(self._show_step, step)

    def _show_step(self, step: "Step") -> None:
        if self._turn is not None:
            self._turn.add_step(step)
            self._to_bottom()

    def _show_reply(self, turn: AgentTurn, reply: "AgentReply") -> None:
        self._tokens += reply.tokens
        turn.finish(reply)
        self._to_bottom()
        self._show_status()
        self._set_busy(False)
        self.query_one("#ai-input", Input).focus()

    def _show_error(self, turn: AgentTurn, message: str) -> None:
        turn.fail(message)
        self._to_bottom()
        self.query_one("#ai-setup").set_class(not ai_is_set_up(), "-shown")
        self._set_busy(False)

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
        self._turn = None
        self._tokens = 0
        self.query(".ai-you, AgentTurn").remove()
        self.query_one("#ai-empty").display = True
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

        def ask() -> None:
            if self._turn is not None:
                self._turn.waiting("Waiting for your answer")
            # Built here on the UI thread: on Python 3.9 a widget made in a
            # worker thread fails, as that thread has no event loop.
            self.app.push_screen(ConfirmDialog(question), done)

        note = DANGER_NOTES.get(call.action.danger.value, "changes files")
        question = f"Max wants to run: {call.describe()}\nIt {note}. Go ahead?"
        self.app.call_from_thread(ask)
        while not answered.wait(CONFIRM_POLL_SECONDS):
            if not self.app.is_running:
                return False
        return answer[0]
