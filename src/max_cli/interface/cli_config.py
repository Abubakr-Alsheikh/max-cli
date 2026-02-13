import typer
from pathlib import Path
from rich.prompt import Prompt, Confirm
from rich.panel import Panel

from max_cli.common.logger import console, log_success, log_error
from max_cli.config import settings

app = typer.Typer()

# Global config location: ~/.max_config.env
GLOBAL_CONFIG_PATH = Path.home() / ".max_config.env"
# Local config location: ./.env
LOCAL_CONFIG_PATH = Path(
    "source.env"
)  # We use a temp var name, logic uses Path(".env")


@app.command("setup")
def setup_config():
    """
    Interactive wizard to configure Global Settings (API Keys, Models, URLs).
    """
    console.print(
        Panel(
            "[bold cyan]Max CLI Configuration Wizard[/bold cyan]", border_style="cyan"
        )
    )
    console.print(f"Settings will be saved to: [dim]{GLOBAL_CONFIG_PATH}[/dim]\n")

    config_data = {}

    # --- 1. Provider Selection ---
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
        config_data["OPENAI_BASE_URL"] = ""  # OpenAI uses default
        default_text_model = "gpt-4o"
        default_img_model = "dall-e-3"
    else:
        # Custom Provider (LocalAI, Ollama, etc.)
        config_data["OPENAI_BASE_URL"] = Prompt.ask("Enter Custom Base URL")
        default_text_model = "gpt-3.5-turbo"
        default_img_model = "dall-e-3"

    # --- 2. API Key ---
    api_key = Prompt.ask(f"Enter {provider.capitalize()} API Key", password=True)
    config_data["OPENAI_API_KEY"] = api_key

    # --- 3. Model Configuration (Override Defaults) ---
    console.print("\n[bold]Model Configuration[/bold] (Press Enter to keep default)")

    config_data["AI_MODEL"] = Prompt.ask("Text/Logic Model", default=default_text_model)

    config_data["AI_IMAGE_MODEL"] = Prompt.ask(
        "Image Generation Model", default=default_img_model
    )

    # --- 4. Write to Global File ---
    try:
        _write_env_file(GLOBAL_CONFIG_PATH, config_data)
        log_success("Configuration updated successfully!")
        console.print(f"[green]Global settings saved to {GLOBAL_CONFIG_PATH}[/green]")
    except Exception as e:
        log_error(f"Failed to save config: {e}")


@app.command("save")
def save_local_to_global(
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite global config without asking."
    ),
):
    """
    Promote the current folder's .env file to Global Settings.
    Useful if you configured a local project perfectly and want to make it the system default.
    """
    local_env = Path(".env")

    if not local_env.exists():
        log_error("No .env file found in the current directory.")
        console.print(
            "Run [bold]max config setup[/bold] to create a new configuration."
        )
        raise typer.Exit(1)

    console.print(f"Found local config at: [bold]{local_env.resolve()}[/bold]")

    # Read local content to preview (optional security check)
    content = local_env.read_text()

    if GLOBAL_CONFIG_PATH.exists() and not force:
        console.print(
            f"[yellow]Warning: This will overwrite your global settings at {GLOBAL_CONFIG_PATH}[/yellow]"
        )
        if not Confirm.ask("Are you sure?"):
            console.print("[red]Aborted.[/red]")
            raise typer.Exit(1)

    try:
        # We simply copy the file content
        GLOBAL_CONFIG_PATH.write_text(content)
        log_success("Local .env saved as Global Configuration!")
        console.print(f"[dim]Copied to: {GLOBAL_CONFIG_PATH}[/dim]")
    except Exception as e:
        log_error(f"Failed to copy file: {e}")


@app.command("show")
def show_config():
    """Display where Max is loading settings from."""

    # Check Global
    if GLOBAL_CONFIG_PATH.exists():
        console.print(
            f"🌍 [bold green]Global Config Found:[/bold green] {GLOBAL_CONFIG_PATH}"
        )
    else:
        console.print(
            "🌍 [bold red]Global Config Missing[/bold red] (Run 'max config setup')"
        )

    # Check Local
    local_env = Path(".env")
    if local_env.exists():
        console.print(
            f"📂 [bold cyan]Local Override Found:[/bold cyan] {local_env.resolve()}"
        )
        console.print("[dim]Local settings take priority over Global settings.[/dim]")

    # Show Active Models
    console.print("\n[bold]Active Configuration:[/bold]")
    console.print(f"Text Model:  [green]{settings.AI_MODEL}[/green]")
    console.print(f"Image Model: [green]{settings.AI_IMAGE_MODEL}[/green]")
    if settings.OPENAI_BASE_URL:
        console.print(f"Base URL:    [dim]{settings.OPENAI_BASE_URL}[/dim]")


def _write_env_file(path: Path, data: dict):
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
