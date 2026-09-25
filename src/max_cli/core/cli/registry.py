from typing import TYPE_CHECKING, Any

from max_cli.core.cli.lazy_group import LAZY_GROUPS, LazyGroupSpec, lazy_group

if TYPE_CHECKING:
    from typer import Typer


def _link_ai_to_full_app(cli_ai_module: Any) -> None:
    """`max ai ask` builds its command list from a fully registered app."""
    cli_ai_module.MAIN_APP_REF = build_full_app()


# Name -> where the group lives. Order is the order `max --help` lists them.
_GROUPS = {
    "images": LazyGroupSpec(
        "max_cli.interface.cli_images", "Compress, resize, and convert images."
    ),
    "img": LazyGroupSpec("max_cli.interface.cli_images", hidden=True),
    "video": LazyGroupSpec(
        "max_cli.interface.cli_media", "Compress, convert, and process video/audio."
    ),
    "v": LazyGroupSpec("max_cli.interface.cli_media", hidden=True),
    "files": LazyGroupSpec(
        "max_cli.interface.cli_files", "Organize and bulk-rename files."
    ),
    "file": LazyGroupSpec("max_cli.interface.cli_files", hidden=True),
    "pdf": LazyGroupSpec(
        "max_cli.interface.cli_pdf", "Merge, split, and compress PDFs."
    ),
    "grab": LazyGroupSpec(
        "max_cli.interface.cli_network", "Download media from various platforms."
    ),
    # Old name for `max grab`, kept hidden so existing scripts keep working.
    "net": LazyGroupSpec(
        "max_cli.interface.cli_network", "Alias of `max grab`.", hidden=True
    ),
    "ai": LazyGroupSpec(
        "max_cli.interface.cli_ai",
        "Ask AI to run commands.",
        on_load=_link_ai_to_full_app,
    ),
    "tools": LazyGroupSpec(
        "max_cli.interface.cli_tools", "System utilities (Clipboard, QR)."
    ),
    "config": LazyGroupSpec(
        "max_cli.interface.cli_config", "Manage API keys and settings."
    ),
    "audio": LazyGroupSpec(
        "max_cli.interface.cli_audio", "Read, write, and manage audio metadata."
    ),
    "a": LazyGroupSpec("max_cli.interface.cli_audio", hidden=True),
    "queue": LazyGroupSpec(
        "max_cli.interface.cli_queue", "Manage background task queue."
    ),
    "dashboard": LazyGroupSpec(
        "max_cli.interface.tui.dashboard", "Launch the interactive TUI dashboard."
    ),
}


def register(app: "Typer") -> None:
    """Register all CLI commands.

    Built-in groups load lazily through LazyTyperGroup, so this only records
    them. The plugins group stays eager because plugins add commands to it.
    """
    from max_cli.core.cli.commands import plugin_commands

    for name, spec in _GROUPS.items():
        lazy_group(name, spec)
    plugin_commands.register(app)


def build_full_app() -> "Typer":
    """A Typer app with every built-in group imported and registered.

    Only for code that walks the whole command tree (the AI schema); normal
    runs load one group.
    """
    import importlib

    import typer

    full_app = typer.Typer()
    for name, spec in _GROUPS.items():
        module = importlib.import_module(spec.module)
        full_app.add_typer(
            getattr(module, spec.attribute),
            name=name,
            help=spec.help or None,
            hidden=spec.hidden,
        )
    return full_app


def init_plugins(app: "Typer") -> None:
    """Initialize and load plugins."""
    from max_cli.core.cli.plugins import init_plugins as _init_plugins

    _init_plugins(app)


__all__ = ["LAZY_GROUPS", "build_full_app", "init_plugins", "register"]
