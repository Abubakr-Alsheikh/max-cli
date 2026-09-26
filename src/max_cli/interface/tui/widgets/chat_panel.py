"""AI chat panel for the TUI dashboard."""

from functools import partial
from typing import Any

from textual import on
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.content import Content
from textual.events import Key
from textual.widgets import Button, Input, Static

from max_cli.interface.tui.activity_log import ActivityLog
from max_cli.interface.tui.text import markup


class ChatPanel(Vertical):
    """AI chat interface with command suggestions."""

    SUGGESTIONS: list[str] = [
        "Compress Videos",
        "Merge PDFs",
        "Organize Files",
        "Convert Images",
        "Extract Audio",
        "Find Duplicates",
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._history: list[str] = []
        self._history_index = -1

    def compose(self):
        yield Static("[bold cyan]AI Assistant[/bold cyan]", id="chat-title")

        yield ScrollableContainer(
            Vertical(id="chat-messages"),
            id="chat-scroll",
        )

        yield Static("[bold]Suggestions[/bold]", id="suggestions-title")
        with Horizontal(id="chat-suggestions"):
            for suggestion in self.SUGGESTIONS:
                btn_id = f"suggest-{suggestion.lower().replace(' ', '-')}"
                yield Button(suggestion, id=btn_id, variant="default")

        with Horizontal(id="chat-input-row"):
            yield Input(placeholder="Type your request...", id="chat-input")
            yield Button("Send", id="btn-send", variant="success")

    def on_mount(self) -> None:
        self._add_message(
            "max",
            "Hello! I can help you with file operations, media processing, and more. What would you like to do?",
        )

    def on_key(self, event: Key) -> None:
        if event.key == "up" and self._history:
            if self._history_index == -1:
                self._history_index = len(self._history) - 1
            elif self._history_index > 0:
                self._history_index -= 1
            input_widget = self.query_one("#chat-input", Input)
            input_widget.value = self._history[self._history_index]
            event.prevent_default()
        elif event.key == "down" and self._history:
            if self._history_index < len(self._history) - 1:
                self._history_index += 1
                input_widget = self.query_one("#chat-input", Input)
                input_widget.value = self._history[self._history_index]
            else:
                self._history_index = -1
                input_widget = self.query_one("#chat-input", Input)
                input_widget.value = ""
            event.prevent_default()

    @on(Button.Pressed, "#btn-send")
    def _on_send(self) -> None:
        input_widget = self.query_one("#chat-input", Input)
        message = input_widget.value.strip()
        if not message:
            return

        input_widget.value = ""
        self._add_message("user", message)
        self._process_request(message)

    @on(Input.Submitted, "#chat-input")
    def _on_submit(self, event: Input.Submitted) -> None:
        self._on_send()

    @on(Button.Pressed)
    def _on_suggestion(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("suggest-"):
            suggestion = event.button.label
            input_widget = self.query_one("#chat-input", Input)
            input_widget.value = suggestion
            self._on_send()
        elif event.button.id and event.button.id.startswith("exec-cmd-"):
            self.notify(
                "Command execution: copy the command from above and run in terminal",
                severity="information",
            )

    @staticmethod
    def _labelled(sender: str, content: "str | Content") -> Content:
        """`Max: ...` or `You: ...`. A plain str is shown as typed, never parsed."""
        color = "cyan" if sender == "max" else "green"
        prefix = "Max" if sender == "max" else "You"
        body = Content(content) if isinstance(content, str) else content
        return Content.assemble((f"{prefix}: ", f"bold {color}"), body)

    def _add_message(self, sender: str, content: "str | Content") -> Static:
        container = self.query_one("#chat-messages", Vertical)
        msg = Static(
            self._labelled(sender, content),
            classes=f"chat-msg chat-msg-{sender}",
        )
        container.mount(msg)
        self.query_one("#chat-scroll").scroll_end()
        return msg

    def _process_request(self, message: str) -> None:
        self._history.append(message)
        self._history_index = -1
        thinking_msg = self._add_message(
            "max", Content.from_markup("[dim]Thinking...[/dim]")
        )
        # The AI call takes seconds; on the UI thread it froze the dashboard
        # and the "Thinking..." line never painted.
        self.run_worker(
            partial(self._ask_ai, message, thinking_msg),
            name="chat-ai",
            thread=True,
        )

    def _ask_ai(self, message: str, thinking_msg: Static) -> None:
        """Runs in a worker thread. UI changes go through call_from_thread."""
        try:
            from max_cli.core.cli.registry import build_full_app
            from max_cli.core.engines.ai_engine import AIEngine

            response: dict[str, Any] = AIEngine().interpret_intent(
                message, app_instance=build_full_app()
            )
        except ImportError:
            self.app.call_from_thread(
                self._show_reply,
                thinking_msg,
                Content.from_markup(
                    "[yellow]AI engine not available. "
                    "Configure your API key in settings.[/yellow]"
                ),
            )
            return
        except Exception as e:
            self.app.call_from_thread(
                self._show_reply,
                thinking_msg,
                markup("[red]Error: $error[/red]", error=e),
            )
            return

        thought = response.get("thought") or "I'm not sure how to help with that."
        command = response.get("command")
        self.app.call_from_thread(
            self._show_reply, thinking_msg, Content(thought), command
        )
        ActivityLog().add_entry(
            category="ai",
            action="chat",
            status="success",
            details={"prompt": message, "response": thought},
        )

    def _show_reply(
        self, thinking_msg: Static, reply: Content, command: "str | None" = None
    ) -> None:
        thinking_msg.update(self._labelled("max", reply))
        if command:
            self._add_message(
                "max",
                markup("Suggested command: [bold]$command[/bold]", command=command),
            )
            container = self.query_one("#chat-messages", Vertical)
            btn_id = f"exec-cmd-{len(container.children)}"
            container.mount(Button("Execute", id=btn_id, variant="success"))
            self.query_one("#chat-scroll").scroll_end()
