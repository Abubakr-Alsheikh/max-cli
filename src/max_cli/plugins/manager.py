import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from max_cli.plugins.base import Plugin

logger = logging.getLogger(__name__)


class PluginManager:
    def __init__(self, plugin_dirs: Optional[List[Path]] = None):
        self._plugins: Dict[str, Plugin] = {}
        self._plugin_dirs = plugin_dirs or self._get_default_plugin_dirs()

    def _get_default_plugin_dirs(self) -> List[Path]:
        dirs = [
            Path.home() / ".max_cli" / "plugins",
            Path.cwd() / "plugins",
        ]
        return [d for d in dirs if d.exists()]

    def discover_plugins(self) -> List[Type[Plugin]]:
        plugins: List[Type[Plugin]] = []
        for plugin_dir in self._plugin_dirs:
            if not plugin_dir.exists():
                continue
            for plugin_file in plugin_dir.glob("*.py"):
                if plugin_file.name.startswith("_"):
                    continue
                try:
                    module_name = f"max_cli_plugins.{plugin_file.stem}"
                    spec = importlib.util.spec_from_file_location(
                        module_name, plugin_file
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[module_name] = module
                        spec.loader.exec_module(module)
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if (
                                isinstance(attr, type)
                                and issubclass(attr, Plugin)
                                and attr is not Plugin
                            ):
                                plugins.append(attr)
                except Exception as e:
                    logger.warning(f"Failed to load plugin from {plugin_file}: {e}")
        return plugins

    def load_plugin(self, plugin_class: Type[Plugin], **kwargs: Any) -> Plugin:
        plugin = plugin_class(**kwargs)
        self._plugins[plugin.name] = plugin
        return plugin

    def register_plugin(self, plugin: Plugin) -> None:
        self._plugins[plugin.name] = plugin

    def unregister_plugin(self, name: str) -> None:
        if name in self._plugins:
            del self._plugins[name]

    def get_plugin(self, name: str) -> Optional[Plugin]:
        return self._plugins.get(name)

    def list_plugins(self) -> List[str]:
        return list(self._plugins.keys())

    def get_all_plugins(self) -> Dict[str, Plugin]:
        return self._plugins.copy()

    def load_all(self) -> None:
        plugin_classes = self.discover_plugins()
        for plugin_class in plugin_classes:
            try:
                self.load_plugin(plugin_class)
            except Exception as e:
                logger.warning(f"Failed to load plugin {plugin_class}: {e}")
