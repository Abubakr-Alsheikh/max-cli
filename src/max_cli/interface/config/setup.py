import typer
from pathlib import Path
from rich.prompt import Prompt
from rich.panel import Panel

from max_cli.common.logger import console, log_success, log_error

app = typer.Typer()

GLOBAL_CONFIG_PATH = Path.home() / ".max_config.env"


def _write_env_file(path: Path, data: dict) -> None:
    """Helper to write a clean .env file."""
    lines = [
        "# Max CLI Global Configuration",
        "# Created automatically via 'max config setup'",
        "",
    ]
    for key, value in data.items():
        if value is not None:
            lines.append(f"{key}={value}")

    path.write_text("\n".join(lines) + "\n")


@app.command("setup")
def setup_config():
    """Interactive wizard to configure Global Settings (API Keys, Models, URLs)."""
    console.print(
        Panel(
            "[bold cyan]Max CLI Configuration Wizard[/bold cyan]", border_style="cyan"
        )
    )
    console.print(f"Settings will be saved to: [dim]{GLOBAL_CONFIG_PATH}[/dim]\n")

    config_data = {}

    provider = Prompt.ask(
        "Select your AI Provider",
        choices=["gemini", "openai", "custom"],
        default="gemini",
    )

    if provider == "gemini":
        config_data["OPENAI_BASE_URL"] = (
            "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        default_text_model = "gemini-1.5-flash"
        default_img_model = "gemini-2.5-flash-image"
    elif provider == "openai":
        config_data["OPENAI_BASE_URL"] = ""
        default_text_model = "gpt-4o"
        default_img_model = "dall-e-3"
    else:
        config_data["OPENAI_BASE_URL"] = Prompt.ask("Enter Custom Base URL")
        default_text_model = "gpt-3.5-turbo"
        default_img_model = "dall-e-3"

    api_key = Prompt.ask(f"Enter {provider.capitalize()} API Key", password=True)
    config_data["OPENAI_API_KEY"] = api_key

    console.print("\n[bold]Model Configuration[/bold] (Press Enter to keep default)")
    config_data["AI_MODEL"] = Prompt.ask("Text/Logic Model", default=default_text_model)
    config_data["AI_IMAGE_MODEL"] = Prompt.ask(
        "Image Generation Model", default=default_img_model
    )

    try:
        _write_env_file(GLOBAL_CONFIG_PATH, config_data)
        log_success("Configuration updated successfully!")
        console.print(f"[green]Global settings saved to {GLOBAL_CONFIG_PATH}[/green]")
    except Exception as e:
        log_error(f"Failed to save config: {e}")
