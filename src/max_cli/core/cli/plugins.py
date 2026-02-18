from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typer import Typer

from max_cli.plugins.base import PluginContext
from max_cli.plugins.manager import PluginManager

_plugin_manager: PluginManager | None = None


def init_plugins(app: "Typer") -> None:
    """Initialize and load plugins."""
    global _plugin_manager
    _plugin_manager = PluginManager()
    _plugin_manager.load_all(PluginContext(app=app))
    _plugin_manager.register_all(app)


def get_plugin_manager() -> PluginManager:
    """Get or initialize the plugin manager."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager
