from pathlib import Path
from typing import Any

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Input, Label, Static

from max_cli.common.atomic import atomic_write_text
from max_cli.config import Settings

# Every name must be a Settings field (tests/interface/tui/test_dashboard_bugs.py).
# Fields not listed here land in an "Other" section.
CONFIG_SECTIONS = {
    "AI": [
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "AI_MODEL",
        "AI_IMAGE_MODEL",
        "OLLAMA_ENABLED",
        "OLLAMA_BASE_URL",
        "OLLAMA_MODEL",
    ],
    "Downloads": [
        "GRAB_QUALITY",
        "GRAB_AUDIO_FORMAT",
        "GRAB_DEFAULT_PATH",
        "GRAB_DEFAULT_TYPE",
        "GRAB_STRIP_PLAYLIST",
        "GRAB_INCLUDE_METADATA",
        "GRAB_QUEUE_ENABLED",
    ],
    "General": [
        "DEFAULT_QUALITY",
        "MAX_WORKERS",
        "BATCH_SIZE",
        "DOWNLOAD_TIMEOUT",
        "MAX_RETRIES",
        "PROGRESS_BAR",
        "VERBOSE",
        "CONFIRM_DESTRUCTIVE",
    ],
}


def _build_field_row(field_name: str, value: object) -> Horizontal:
    label = Label(f"{field_name}:", classes="config-label")

    if isinstance(value, bool):
        input_widget = Input(value=str(value), id=f"cfg-{field_name}")
    elif isinstance(value, Path):
        input_widget = Input(value=str(value), id=f"cfg-{field_name}")
    elif isinstance(value, int):
        input_widget = Input(
            value=str(value),
            id=f"cfg-{field_name}",
            type="integer",
        )
    else:
        if "API_KEY" in field_name and value:
            masked = str(value)[:8] + "..." if len(str(value)) > 8 else "***"
            input_widget = Input(value=masked, id=f"cfg-{field_name}")
        else:
            input_widget = Input(
                value=str(value) if value is not None else "",
                id=f"cfg-{field_name}",
            )

    return Horizontal(label, input_widget, classes="config-row", name=field_name)


def _build_section(
    section_name: str, field_names: list[str], settings: Settings
) -> Vertical:
    children: list[object] = [
        Static(f"[bold]{section_name}[/bold]", classes="config-section-title")
    ]
    for field_name in field_names:
        if field_name not in Settings.model_fields:
            continue
        value = getattr(settings, field_name)
        children.append(_build_field_row(field_name, value))
    return Vertical(*children, classes="config-section")


class ConfigPanel(Vertical):
    """Editable configuration panel."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._original_values: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        yield Static("[bold cyan]\u2699 Configuration[/bold cyan]", id="config-title")
        yield Label(
            "[dim]Settings from ~/.max_config.env[/dim]",
            id="config-source",
        )
        yield Input(
            placeholder="\U0001f50d Search settings...",
            id="config-search",
        )
        yield ScrollableContainer(Vertical(id="config-fields"), id="config-scroll")
        with Horizontal(id="config-actions"):
            yield Button(
                "\U0001f4be Save Changes", id="btn-save-config", variant="success"
            )
            yield Button(
                "\u21a9 Reset to Defaults", id="btn-reset-config", variant="error"
            )
        yield Static("", id="config-status")

    def on_mount(self) -> None:
        self._build_fields()

    def _build_fields(self) -> None:
        container = self.query_one("#config-fields", Vertical)
        container.remove_children()

        settings = Settings()
        self._original_values = {}

        for section_name, section_fields in CONFIG_SECTIONS.items():
            container.mount(_build_section(section_name, section_fields, settings))

        remaining_fields = [
            f
            for f in Settings.model_fields
            if f
            not in [field for fields in CONFIG_SECTIONS.values() for field in fields]
        ]
        if remaining_fields:
            container.mount(_build_section("Other", remaining_fields, settings))

        for field_name in Settings.model_fields:
            if field_name not in Settings.model_fields:
                continue
            value = getattr(settings, field_name)
            if "API_KEY" in field_name and value:
                self._original_values[field_name] = str(value)

    @on(Input.Changed, "#config-search")
    def _on_search(self) -> None:
        search_input = self.query_one("#config-search", Input)
        search_text = search_input.value.strip().lower()

        sections = self.query(".config-section")
        for section in sections:
            rows = section.query(".config-row")
            visible_count = 0
            for row in rows:
                field_name = (row.name or "").lower()
                row.display = not search_text or search_text in field_name
                if row.display:
                    visible_count += 1
            section.display = visible_count > 0 or not search_text

    @on(Button.Pressed, "#btn-save-config")
    def _on_save(self) -> None:
        env_path = Path.home() / ".max_config.env"

        lines = []
        for field_name in Settings.model_fields:
            input_widget = self.query_one(f"#cfg-{field_name}", Input)
            if input_widget:
                value = input_widget.value.strip()
                if "API_KEY" in field_name and "..." in value:
                    original = self._original_values.get(field_name, "")
                    if original:
                        value = original
                    else:
                        continue
                lines.append(f"{field_name}={value}")

        atomic_write_text(env_path, "\n".join(lines) + "\n")

        status = self.query_one("#config-status", Static)
        status.update("[green]Configuration saved to ~/.max_config.env[/green]")

    @on(Button.Pressed, "#btn-reset-config")
    def _on_reset(self) -> None:
        env_path = Path.home() / ".max_config.env"
        if env_path.exists():
            env_path.unlink()
        self._build_fields()
        status = self.query_one("#config-status", Static)
        status.update("[yellow]Reset to defaults. Restart CLI to apply.[/yellow]")
