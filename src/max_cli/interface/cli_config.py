import typer
from pathlib import Path
from rich.prompt import Prompt
from rich.panel import Panel
from max_cli.common.logger import console, log_success, log_error

app = typer.Typer()

CONFIG_PATH = Path.home() / ".max_config.env"


@app.command("setup")
def setup_config():
    """
    Interactive setup to save API keys globally.
    """
    console.print(
        Panel("[bold cyan]Max CLI Configuration[/bold cyan]", border_style="cyan")
    )
    console.print(f"Settings will be saved to: [dim]{CONFIG_PATH}[/dim]\n")

    # 1. Ask for Provider
    provider = Prompt.ask(
        "Which AI Provider are you using?",
        choices=["openai", "gemini", "skip"],
        default="gemini",
    )

    if provider == "skip":
        console.print("[yellow]Skipping AI setup.[/yellow]")
        return

    new_lines = []

    # 2. Collect Keys
    if provider == "gemini":
        key = Prompt.ask("Enter your Google Gemini API Key", password=True)
        new_lines.append(f"OPENAI_API_KEY={key}")
        new_lines.append(
            "OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        new_lines.append("AI_MODEL=gemini-1.5-flash")
        new_lines.append("AI_IMAGE_MODEL=gemini-2.5-flash-image")

    elif provider == "openai":
        key = Prompt.ask("Enter your OpenAI API Key", password=True)
        new_lines.append(f"OPENAI_API_KEY={key}")
        # OpenAI doesn't need a Base URL usually
        new_lines.append("AI_MODEL=gpt-4o")
        new_lines.append("AI_IMAGE_MODEL=dall-e-3")

    # 3. Save to Global File
    try:
        # Read existing content to preserve other settings if needed
        existing_content = ""
        if CONFIG_PATH.exists():
            existing_content = CONFIG_PATH.read_text()

        # Simple overwrite logic for cleaner setup (or append if you prefer)
        # Here we overwrite to ensure the keys are fresh and correct.
        with open(CONFIG_PATH, "w") as f:
            f.write("\n".join(new_lines) + "\n")

        log_success("Configuration saved successfully!")
        console.print("[green]You can now use Max from any terminal window.[/green]")

    except Exception as e:
        log_error(f"Failed to save config: {e}")


@app.command("show")
def show_config():
    """Show current configuration location."""
    if CONFIG_PATH.exists():
        console.print(f"Config file found at: [bold]{CONFIG_PATH}[/bold]")
        console.print(
            "[dim](Use 'cat' to view contents if needed, but keep your keys safe!)[/dim]"
        )
    else:
        console.print(
            "[yellow]No global configuration found. Run 'max config setup'.[/yellow]"
        )
