from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Input, Label, Static

from max_cli.config import Settings


CONFIG_SECTIONS = {
    "AI": [
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "GOOGLE_API_KEY",
        "GOOGLE_MODEL",
        "AI_PROVIDER",
        "AI_TEMPERATURE",
        "AI_MAX_TOKENS",
    ],
    "Grab": [
        "YTDLP_FORMAT",
        "YTDLP_OUTPUT_DIR",
        "YTDLP_MAX_CONCURRENT",
    ],
    "General": [
        "MAX_THREADS",
        "CACHE_DIR",
        "LOG_LEVEL",
        "TEMP_DIR",
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

    return Horizontal(label, input_widget, classes="config-row")


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
        yield ScrollableContainer(Vertical(id="config-fields"))
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

    @on(Input.Changed, "#config-search")
    def _on_search(self) -> None:
        search_input = self.query_one("#config-search", Input)
        search_text = search_input.value.strip().lower()

        sections = self.query(".config-section")
        for section in sections:
            rows = section.query(".config-row")
            visible_count = 0
            for row in rows:
                label = row.query_one(".config-label", Label)
                if label:
                    field_name = label.renderable.lower()
                    if not search_text or search_text in field_name:
                        row.display = True
                        visible_count += 1
                    else:
                        row.display = False
            section.display = visible_count > 0 or not search_text

    @on(Button.Pressed, "#btn-save-config")
    def _on_save(self) -> None:
        env_path = Path.home() / ".max_config.env"

        lines = []
        for field_name in Settings.model_fields:
            input_widget = self.query_one(f"#cfg-{field_name}", Input)
            if input_widget:
                value = input_widget.value.strip()
                lines.append(f"{field_name}={value}")

        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

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
