"""AI chat panel for the TUI dashboard."""

from typing import Any

from textual import on
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Input, Static

from max_cli.interface.tui.activity_log import ActivityLog


class ChatPanel(Vertical):
    """AI chat interface with command suggestions."""

    SUGGESTIONS: list[str] = [
        "Compress videos",
        "Merge PDFs",
        "Organize files",
        "Convert images",
        "Extract audio",
        "Find duplicates",
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
            suggestion = (
                event.button.id.replace("suggest-", "").replace("-", " ").title()
            )
            input_widget = self.query_one("#chat-input", Input)
            input_widget.value = suggestion
            self._on_send()

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
        try:
            from max_cli.core.engines.ai_engine import AIEngine

            engine = AIEngine()
            response: dict[str, Any] = engine.interpret_intent(
                message, app_instance=None
            )

            thought = response.get("thought", "I'm not sure how to help with that.")
            self._add_message("max", thought)

            command = response.get("command")
            if command:
                self._add_message("max", f"Suggested command: [bold]{command}[/bold]")

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
