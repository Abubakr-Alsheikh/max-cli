import typer
import json
from pathlib import Path
from rich.prompt import Confirm
from rich.table import Table
from rich import box

from max_cli.common.logger import console, log_success, log_error
from max_cli.config import settings

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


@app.command("show")
def show_config():
    """Display where Max is loading settings from."""
    if GLOBAL_CONFIG_PATH.exists():
        console.print(
            f"🌍 [bold green]Global Config Found:[/bold green] {GLOBAL_CONFIG_PATH}"
        )
    else:
        console.print(
            "🌍 [bold red]Global Config Missing[/bold red] (Run 'max config setup')"
        )

    local_env = Path(".env")
    if local_env.exists():
        console.print(
            f"📂 [bold cyan]Local Override Found:[/bold cyan] {local_env.resolve()}"
        )
        console.print("[dim]Local settings take priority over Global settings.[/dim]")

    console.print("\n[bold]Active Configuration:[/bold]")
    console.print(f"Text Model:  [green]{settings.AI_MODEL}[/green]")
    console.print(f"Image Model: [green]{settings.AI_IMAGE_MODEL}[/green]")
    if settings.OPENAI_BASE_URL:
        console.print(f"Base URL:    [dim]{settings.OPENAI_BASE_URL}[/dim]")


@app.command("save")
def save_local_to_global(
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite global config without asking."
    ),
):
    """Promote the current folder's .env file to Global Settings."""
    local_env = Path(".env")

    if not local_env.exists():
        log_error("No .env file found in the current directory.")
        console.print(
            "Run [bold]max config setup[/bold] to create a new configuration."
        )
        raise typer.Exit(1)

    console.print(f"Found local config at: [bold]{local_env.resolve()}[/bold]")
    content = local_env.read_text()

    if GLOBAL_CONFIG_PATH.exists() and not force:
        console.print(
            f"[yellow]Warning: This will overwrite your global settings at {GLOBAL_CONFIG_PATH}[/yellow]"
        )
        if not Confirm.ask("Are you sure?"):
            console.print("[red]Aborted.[/red]")
            raise typer.Exit(1)

    try:
        GLOBAL_CONFIG_PATH.write_text(content)
        log_success("Local .env saved as Global Configuration!")
        console.print(f"[dim]Copied to: {GLOBAL_CONFIG_PATH}[/dim]")
    except Exception as e:
        log_error(f"Failed to copy file: {e}")


@app.command("reset")
def reset_config(
    global_only: bool = typer.Option(
        False, "--global", help="Only reset global config."
    ),
    local_only: bool = typer.Option(False, "--local", help="Only reset local .env."),
):
    """Reset configuration to defaults."""
    if not global_only and not local_only:
        global_only = True
        local_only = True

    if global_only and GLOBAL_CONFIG_PATH.exists():
        if Confirm.ask(f"Delete global config at {GLOBAL_CONFIG_PATH}?"):
            GLOBAL_CONFIG_PATH.unlink()
            log_success("Global config reset to defaults.")

    if local_only:
        local_env = Path(".env")
        if local_env.exists():
            if Confirm.ask(f"Delete local config at {local_env}?"):
                local_env.unlink()
                log_success("Local config reset to defaults.")


@app.command("validate")
def validate_config():
    """Validate current configuration."""
    table = Table(title="Configuration Validation", box=box.ROUNDED)
    table.add_column("Setting", style="cyan")
    table.add_column("Value")
    table.add_column("Status", justify="center")

    issues = []

    table.add_row("MAX_WORKERS", str(settings.MAX_WORKERS), "[green]OK[/green]")
    table.add_row("BATCH_SIZE", str(settings.BATCH_SIZE), "[green]OK[/green]")
    table.add_row(
        "DOWNLOAD_TIMEOUT", str(settings.DOWNLOAD_TIMEOUT), "[green]OK[/green]"
    )
    table.add_row("DEFAULT_QUALITY", str(settings.DEFAULT_QUALITY), "[green]OK[/green]")

    if settings.MAX_WORKERS < 1 or settings.MAX_WORKERS > 16:
        table.add_row("MAX_WORKERS", str(settings.MAX_WORKERS), "[red]Invalid[/red]")
        issues.append("MAX_WORKERS must be between 1 and 16")
    else:
        table.add_row("MAX_WORKERS", str(settings.MAX_WORKERS), "[green]OK[/green]")

    if settings.DEFAULT_QUALITY < 1 or settings.DEFAULT_QUALITY > 100:
        issues.append("DEFAULT_QUALITY must be between 1 and 100")

    if settings.DOWNLOAD_TIMEOUT < 30:
        issues.append("DOWNLOAD_TIMEOUT must be at least 30 seconds")

    if settings.OPENAI_API_KEY:
        table.add_row("OPENAI_API_KEY", "***configured***", "[green]OK[/green]")
    else:
        table.add_row("OPENAI_API_KEY", "[not set]", "[yellow]Warning[/yellow]")

    console.print(table)

    if issues:
        console.print("[bold red]Issues found:[/bold red]")
        for issue in issues:
            console.print(f"  [red]•[/red] {issue}")
    else:
        log_success("Configuration is valid!")


@app.command("export")
def export_config(
    output: Path = typer.Option(Path("max-config.json"), "-o", help="Output file."),
    include_defaults: bool = typer.Option(
        False, "--include-defaults", help="Include default values."
    ),
):
    """Export configuration to JSON file."""
    config_dict = {}

    if include_defaults:
        config_dict = {
            "APP_NAME": settings.APP_NAME,
            "DEFAULT_QUALITY": settings.DEFAULT_QUALITY,
            "MAX_WORKERS": settings.MAX_WORKERS,
            "BATCH_SIZE": settings.BATCH_SIZE,
            "DOWNLOAD_TIMEOUT": settings.DOWNLOAD_TIMEOUT,
            "MAX_RETRIES": settings.MAX_RETRIES,
            "PROGRESS_BAR": settings.PROGRESS_BAR,
            "VERBOSE": settings.VERBOSE,
            "CONFIRM_DESTRUCTIVE": settings.CONFIRM_DESTRUCTIVE,
            "AI_MODEL": settings.AI_MODEL,
            "AI_IMAGE_MODEL": settings.AI_IMAGE_MODEL,
            "GRAB_QUALITY": settings.GRAB_QUALITY,
            "GRAB_AUDIO_FORMAT": settings.GRAB_AUDIO_FORMAT,
            "GRAB_STRIP_PLAYLIST": settings.GRAB_STRIP_PLAYLIST,
            "GRAB_INCLUDE_METADATA": settings.GRAB_INCLUDE_METADATA,
            "GRAB_DEFAULT_TYPE": settings.GRAB_DEFAULT_TYPE,
            "GRAB_DEFAULT_PATH": str(settings.GRAB_DEFAULT_PATH),
            "GRAB_QUEUE_ENABLED": settings.GRAB_QUEUE_ENABLED,
        }
    else:
        non_defaults = {
            "OPENAI_API_KEY": settings.OPENAI_API_KEY,
            "OPENAI_BASE_URL": settings.OPENAI_BASE_URL,
            "AI_MODEL": settings.AI_MODEL,
            "AI_IMAGE_MODEL": settings.AI_IMAGE_MODEL,
            "GRAB_QUALITY": settings.GRAB_QUALITY,
            "GRAB_AUDIO_FORMAT": settings.GRAB_AUDIO_FORMAT,
            "GRAB_STRIP_PLAYLIST": settings.GRAB_STRIP_PLAYLIST,
            "GRAB_INCLUDE_METADATA": settings.GRAB_INCLUDE_METADATA,
            "GRAB_DEFAULT_TYPE": settings.GRAB_DEFAULT_TYPE,
            "GRAB_DEFAULT_PATH": str(settings.GRAB_DEFAULT_PATH),
            "GRAB_QUEUE_ENABLED": settings.GRAB_QUEUE_ENABLED,
        }
        for k, v in non_defaults.items():
            if v is not None and v != "":
                config_dict[k] = v

    try:
        output.write_text(json.dumps(config_dict, indent=2))
        log_success(f"Config exported to {output}")
    except Exception as e:
        log_error(f"Failed to export config: {e}")


@app.command("import")
def import_config(
    input: Path = typer.Argument(..., help="Input JSON file."),
    global_config: bool = typer.Option(
        True, "--global/--local", help="Import to global or local config."
    ),
):
    """Import configuration from JSON file."""
    if not input.exists():
        log_error(f"File not found: {input}")
        raise typer.Exit(1)

    try:
        data = json.loads(input.read_text())
    except Exception as e:
        log_error(f"Invalid JSON: {e}")
        raise typer.Exit(1)

    target = GLOBAL_CONFIG_PATH if global_config else Path(".env")

    if target.exists() and not Confirm.ask(f"Overwrite {target}?"):
        console.print("[red]Aborted.[/red]")
        raise typer.Exit(1)

    try:
        _write_env_file(target, data)
        log_success(f"Config imported to {target}")
    except Exception as e:
        log_error(f"Failed to import config: {e}")
