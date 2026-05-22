"""AI chat panel for the TUI dashboard."""

from typing import Any

from textual import on
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.events import Key
from textual.widgets import Button, Input, Static

from max_cli.interface.tui.activity_log import ActivityLog


class ChatPanel(Vertical):
    """AI chat interface with command suggestions."""

    _history: list[str] = []
    _history_index: int = -1

    SUGGESTIONS: list[str] = [
        "Compress Videos",
        "Merge PDFs",
        "Organize Files",
        "Convert Images",
        "Extract Audio",
        "Find Duplicates",
    ]

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

    def _add_message(self, sender: str, content: str) -> None:
        container = self.query_one("#chat-messages", Vertical)
        color = "cyan" if sender == "max" else "green"
        prefix = "Max" if sender == "max" else "You"
        msg = Static(
            f"[bold {color}]{prefix}:[/bold {color}] {content}",
            classes=f"chat-msg chat-msg-{sender}",
        )
        container.mount(msg)
        self.query_one("#chat-scroll").scroll_end()

    def _process_request(self, message: str) -> None:
        self._history.append(message)
        self._history_index = -1
        try:
            from max_cli.core.engines.ai_engine import AIEngine

            self._add_message("max", "[dim]Thinking...[/dim]")
            thinking_msg = self.query_one("#chat-messages", Vertical).children[-1]

            engine = AIEngine()
            response: dict[str, Any] = engine.interpret_intent(
                message, app_instance=self.app
            )

            thought = response.get("thought", "I'm not sure how to help with that.")
            thinking_msg.update(f"[bold cyan]Max:[/bold cyan] {thought}")

            command = response.get("command")
            if command:
                self._add_message("max", f"Suggested command: [bold]{command}[/bold]")
                container = self.query_one("#chat-messages", Vertical)
                btn_id = f"exec-cmd-{len(list(container.children))}"
                exec_btn = Button("Execute", id=btn_id, variant="success")
                container.mount(exec_btn)

            activity = ActivityLog()
            activity.add_entry(
                category="ai",
                action="chat",
                status="success",
                details={"prompt": message, "response": thought},
            )

        except ImportError:
            self._add_message(
                "max",
                "[yellow]AI engine not available. Configure your API key in settings.[/yellow]",
            )
        except Exception as e:
            self._add_message("max", f"[red]Error: {e}[/red]")
