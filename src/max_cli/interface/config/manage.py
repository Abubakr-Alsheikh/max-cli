import json
from pathlib import Path

import typer
from rich import box
from rich.prompt import Confirm
from rich.table import Table

from max_cli.common.atomic import atomic_write_json, atomic_write_text
from max_cli.common.logger import console, log_error, log_success
from max_cli.config import settings

app = typer.Typer()

GLOBAL_CONFIG_PATH = Path.home() / ".max_config.env"
# API keys: an export leaves them out unless --include-secrets.
SECRET_SETTINGS = ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY")


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

    atomic_write_text(path, "\n".join(lines) + "\n")


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

    from max_cli.core.engines.ai_providers import fallback_provider, main_provider

    console.print("\n[bold]Active Configuration:[/bold]")
    for role, provider in (
        ("Main AI", main_provider()),
        ("Fallback", fallback_provider()),
    ):
        if provider is None:
            console.print(f"{role + ':':<13}[dim]none[/dim]")
            continue
        key = "" if provider.is_set_up() else "  [yellow](no API key)[/yellow]"
        console.print(
            f"{role + ':':<13}[green]{provider.label}[/green]  "
            f"[dim]{provider.model()}[/dim]{key}"
        )
    console.print(f"{'Image model:':<13}[green]{settings.AI_IMAGE_MODEL}[/green]")
    if settings.OPENAI_BASE_URL:
        console.print(f"{'Custom URL:':<13}[dim]{settings.OPENAI_BASE_URL}[/dim]")


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
    content = local_env.read_text(encoding="utf-8")

    if GLOBAL_CONFIG_PATH.exists() and not force:
        console.print(
            f"[yellow]Warning: This will overwrite your global settings at {GLOBAL_CONFIG_PATH}[/yellow]"
        )
        if not Confirm.ask("Are you sure?"):
            console.print("[red]Aborted.[/red]")
            raise typer.Exit(1)

    try:
        atomic_write_text(GLOBAL_CONFIG_PATH, content)
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

    table.add_row(
        "DOWNLOAD_TIMEOUT", str(settings.DOWNLOAD_TIMEOUT), "[green]OK[/green]"
    )
    table.add_row("MAX_RETRIES", str(settings.MAX_RETRIES), "[green]OK[/green]")
    table.add_row(
        "CONFIRM_DESTRUCTIVE", str(settings.CONFIRM_DESTRUCTIVE), "[green]OK[/green]"
    )
    table.add_row("DEFAULT_QUALITY", str(settings.DEFAULT_QUALITY), "[green]OK[/green]")

    if settings.MAX_WORKERS < 1 or settings.MAX_WORKERS > 16:
        table.add_row("MAX_WORKERS", str(settings.MAX_WORKERS), "[red]Invalid[/red]")
        issues.append("MAX_WORKERS must be between 1 and 16")
    else:
        table.add_row("MAX_WORKERS", str(settings.MAX_WORKERS), "[green]OK[/green]")

    if settings.DEFAULT_QUALITY < 1 or settings.DEFAULT_QUALITY > 100:
        issues.append("DEFAULT_QUALITY must be between 1 and 100")

    from max_cli.common.settings_file import removed_settings_in_file

    for name in removed_settings_in_file(GLOBAL_CONFIG_PATH):
        issues.append(
            f"{name} is no longer a setting; remove it from {GLOBAL_CONFIG_PATH}"
        )

    from max_cli.core.engines.ai_providers import fallback_provider, main_provider

    for setting, provider in (
        ("AI_PROVIDER", main_provider()),
        ("AI_FALLBACK_PROVIDER", fallback_provider()),
    ):
        if provider is None:
            continue
        if provider.is_set_up():
            table.add_row(setting, provider.label, "[green]OK[/green]")
        else:
            table.add_row(setting, provider.label, "[yellow]No API key[/yellow]")
            issues.append(f"{provider.label} needs {provider.key_setting}")

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
    include_secrets: bool = typer.Option(
        False,
        "--include-secrets",
        help="Also write API keys. Keep the file private if you use this.",
    ),
):
    """Export configuration to JSON file. API keys are left out by default."""
    config_dict = {}

    if include_defaults:
        config_dict = {
            name: str(value) if isinstance(value, Path) else value
            for name, value in settings.model_dump().items()
            if name not in SECRET_SETTINGS
        }
    else:
        non_defaults = {
            "AI_PROVIDER": settings.AI_PROVIDER,
            "AI_FALLBACK_PROVIDER": settings.AI_FALLBACK_PROVIDER,
            "OPENAI_BASE_URL": settings.OPENAI_BASE_URL,
            "AI_MODEL": settings.AI_MODEL,
            "OPENROUTER_MODEL": settings.OPENROUTER_MODEL,
            "GEMINI_MODEL": settings.GEMINI_MODEL,
            "AI_IMAGE_MODEL": settings.AI_IMAGE_MODEL,
            "GRAB_QUALITY": settings.GRAB_QUALITY,
            "GRAB_STRIP_PLAYLIST": settings.GRAB_STRIP_PLAYLIST,
            "GRAB_INCLUDE_METADATA": settings.GRAB_INCLUDE_METADATA,
            "GRAB_DEFAULT_TYPE": settings.GRAB_DEFAULT_TYPE,
            "GRAB_DEFAULT_PATH": str(settings.GRAB_DEFAULT_PATH),
        }
        for k, v in non_defaults.items():
            if v is not None and v != "":
                config_dict[k] = v

    secrets = {
        name: getattr(settings, name)
        for name in SECRET_SETTINGS
        if getattr(settings, name)
    }
    if include_secrets and secrets:
        config_dict.update(secrets)
        console.print(
            "[yellow]Warning: the export contains your API keys in plain text. "
            "Don't share or commit the file.[/yellow]"
        )

    try:
        atomic_write_json(output, config_dict)
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
        data = json.loads(input.read_text(encoding="utf-8"))
    except Exception as e:
        log_error(f"Invalid JSON: {e}")
        raise typer.Exit(1) from None

    target = GLOBAL_CONFIG_PATH if global_config else Path(".env")

    if target.exists() and not Confirm.ask(f"Overwrite {target}?"):
        console.print("[red]Aborted.[/red]")
        raise typer.Exit(1)

    try:
        _write_env_file(target, data)
        log_success(f"Config imported to {target}")
    except Exception as e:
        log_error(f"Failed to import config: {e}")
