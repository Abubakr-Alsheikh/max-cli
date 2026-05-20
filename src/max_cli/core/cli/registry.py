from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typer import Typer

from max_cli.core.cli import commands
from max_cli.core.cli import plugins


def register(app: "Typer") -> None:
    """Register all CLI commands."""
    commands.media.register(app)
    commands.files.register(app)
    commands.network.register(app)
    commands.ai.register(app)
    commands.tools.register(app)
    commands.config.register(app)
    commands.plugin_commands.register(app)
    commands.audio.register(app)
    commands.queue.register(app)
    commands.tui.register(app)


init_plugins = plugins.init_plugins
