from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.prompt import Prompt

from max_cli.common.logger import console, log_error, log_success
from max_cli.config import settings

app = typer.Typer()

GLOBAL_CONFIG_PATH = Path.home() / ".max_config.env"


# Per provider: the model to suggest.
DEFAULT_MODELS = {
    "openai": "gpt-5-nano",
    "openrouter": "openrouter/free",
    "gemini": "gemini-2.5-flash",
    "ollama": "llama3.1",
}
NO_FALLBACK = "none"


def _ask_provider(changes: dict[str, Optional[str]], name: str) -> None:
    """A provider's key (or Ollama's URL) and model, into `changes`."""
    from max_cli.core.engines.ai_providers import PROVIDERS

    provider = PROVIDERS[name]
    if name == "ollama":
        changes["OLLAMA_BASE_URL"] = Prompt.ask(
            "Ollama URL", default=settings.OLLAMA_BASE_URL
        )
    else:
        hint = "keeps the saved one" if provider.key() else "required"
        key = Prompt.ask(
            f"{provider.label} API key ({hint})", password=True, default=""
        )
        if key:
            changes[provider.key_setting] = key
        if name == "openai":
            url = Prompt.ask(
                "Custom URL (empty for OpenAI)", default=settings.OPENAI_BASE_URL or ""
            )
            changes["OPENAI_BASE_URL"] = url or None
    current = provider.model()
    default = current if settings.AI_PROVIDER else DEFAULT_MODELS[name]
    changes[provider.model_setting] = Prompt.ask(
        f"{provider.label} model", default=default or DEFAULT_MODELS[name]
    )


@app.command("setup")
def setup_config():
    """Pick the AI Max uses and a fallback, with each one's API key and model.

    Only these settings change; the rest of ~/.max_config.env stays.
    """
    from max_cli.common.settings_file import update_settings_file
    from max_cli.core.engines.ai_providers import PROVIDERS, main_provider

    console.print(
        Panel(
            "[bold cyan]Max CLI Configuration Wizard[/bold cyan]", border_style="cyan"
        )
    )
    console.print(f"Settings will be saved to: [dim]{GLOBAL_CONFIG_PATH}[/dim]\n")
    console.print(
        "[dim]Gemini has a free API key: https://aistudio.google.com/apikey[/dim]\n"
    )

    changes: dict[str, Optional[str]] = {}
    names = list(PROVIDERS)
    main = Prompt.ask("Main AI", choices=names, default=main_provider().name)
    changes["AI_PROVIDER"] = main
    _ask_provider(changes, main)

    others = [name for name in names if name != main]
    fallback = Prompt.ask(
        "Fallback when the main AI fails",
        choices=[NO_FALLBACK, *others],
        default=settings.AI_FALLBACK_PROVIDER or NO_FALLBACK,
    )
    changes["AI_FALLBACK_PROVIDER"] = "" if fallback == NO_FALLBACK else fallback
    if fallback != NO_FALLBACK:
        _ask_provider(changes, fallback)

    changes["AI_IMAGE_MODEL"] = Prompt.ask(
        "Image model (create and edit)", default=settings.AI_IMAGE_MODEL
    )
    try:
        update_settings_file(changes, GLOBAL_CONFIG_PATH)
    except OSError as e:
        log_error(f"Failed to save config: {e}")
        return
    log_success("Configuration updated successfully!")
    console.print(f"[green]Global settings saved to {GLOBAL_CONFIG_PATH}[/green]")
    console.print("[dim]Check them with: max config validate[/dim]")
