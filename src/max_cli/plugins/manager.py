import importlib
import importlib.util
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type

import typer

from max_cli.plugins.base import (
    Plugin,
    PluginContext,
    PluginLoadError,
    PluginValidationError,
)

if TYPE_CHECKING:
    from max_cli.plugins.base import Plugin

logger = logging.getLogger(__name__)


@dataclass
class LoadedPlugin:
    """Represents a loaded plugin with metadata."""

    plugin: Optional["Plugin"]
    enabled: bool = True
    loaded_from: Optional[Path] = None
    error: Optional[str] = None


class PluginManager:
    def __init__(
        self,
        plugin_dirs: Optional[List[Path]] = None,
        config_dir: Optional[Path] = None,
    ):
        self._plugins: Dict[str, LoadedPlugin] = {}
        self._plugin_dirs = plugin_dirs or self._get_default_plugin_dirs()
        self._config_dir = config_dir or self._get_default_config_dir()
        self._app: Optional[Any] = None
        self._load_config()

    def _get_default_plugin_dirs(self) -> List[Path]:
        dirs = [
            Path.home() / ".max_cli" / "plugins",
            Path.cwd() / "plugins",
        ]
        return [d for d in dirs if d.exists()]

    def _get_default_config_dir(self) -> Path:
        config_dir = Path.home() / ".max_cli"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir

    def _load_config(self) -> None:
        config_file = self._config_dir / "plugins.json"
        if config_file.exists():
            try:
                with open(config_file) as f:
                    self._enabled_plugins = json.load(f).get("enabled", {})
            except Exception:
                self._enabled_plugins = {}
        else:
            self._enabled_plugins = {}

    def _save_config(self) -> None:
        config_file = self._config_dir / "plugins.json"
        config = {"enabled": self._enabled_plugins}
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

    @property
    def app(self) -> Any:
        return self._app

    @app.setter
    def app(self, value: Any) -> None:
        self._app = value

    def discover_plugins(self) -> List[Type[Plugin]]:
        plugins: List[Type[Plugin]] = []
        for plugin_dir in self._plugin_dirs:
            plugins.extend(self._discover_plugins_in_dir(plugin_dir))
        return plugins

    def _discover_plugins_in_dir(self, plugin_dir: Path) -> List[Type[Plugin]]:
        plugins: List[Type[Plugin]] = []
        if not plugin_dir.exists():
            return plugins
        for plugin_file in plugin_dir.glob("*.py"):
            if plugin_file.name.startswith("_"):
                continue
            try:
                module_name = f"max_cli_plugins.{plugin_file.stem}"
                spec = importlib.util.spec_from_file_location(module_name, plugin_file)
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

    def load_plugin(
        self,
        plugin_class: Type[Plugin],
        **kwargs: Any,
    ) -> LoadedPlugin:
        plugin = plugin_class(**kwargs)

        is_valid, error_msg = plugin.validate()
        if not is_valid:
            raise PluginValidationError(f"Plugin validation failed: {error_msg}")

        is_enabled = self._enabled_plugins.get(plugin.name, True)

        loaded_plugin = LoadedPlugin(
            plugin=plugin,
            enabled=is_enabled,
        )
        self._plugins[plugin.name] = loaded_plugin
        return loaded_plugin

    def load_all(self, context: Optional[PluginContext] = None) -> None:
        plugin_classes = self.discover_plugins()
        plugin_classes.sort(
            key=lambda p: p().priority if hasattr(p(), "priority") else 100
        )

        for plugin_class in plugin_classes:
            try:
                self.load_plugin(plugin_class)
            except (PluginValidationError, PluginLoadError) as e:
                logger.warning(f"Failed to load plugin {plugin_class.__name__}: {e}")
                loaded_plugin = LoadedPlugin(
                    plugin=None,
                    enabled=False,
                    error=str(e),
                )
                self._plugins[plugin_class.__name__.lower().replace("plugin", "")] = (
                    loaded_plugin
                )

        if context:
            for name, loaded in self._plugins.items():
                if loaded.plugin and loaded.enabled:
                    try:
                        context.plugin_dir = self._find_plugin_dir(name)
                        loaded.plugin.on_load(context)
                    except Exception as e:
                        logger.warning(f"Plugin {name} on_load failed: {e}")

    def register_all(self, app: typer.Typer) -> None:
        self._app = app
        for name, loaded in sorted(
            self._plugins.items(),
            key=lambda x: x[1].plugin.priority if x[1].plugin else 100,
        ):
            if loaded.plugin and loaded.enabled:
                try:
                    loaded.plugin.register(app)
                    logger.info(f"Registered plugin: {loaded.plugin.name}")
                except Exception as e:
                    logger.error(f"Failed to register plugin {name}: {e}")
                    loaded.error = str(e)
                    loaded.enabled = False

    def unregister_all(self, app: typer.Typer) -> None:
        for name, loaded in self._plugins.items():
            if loaded.plugin and loaded.enabled:
                try:
                    loaded.plugin.unregister(app)
                    loaded.plugin.on_unload()
                except Exception as e:
                    logger.warning(f"Error unloading plugin {name}: {e}")

    def _find_plugin_dir(self, plugin_name: str) -> Optional[Path]:
        for plugin_dir in self._plugin_dirs:
            if plugin_dir.exists():
                for f in plugin_dir.glob("*.py"):
                    if plugin_name.lower() in f.stem.lower():
                        return f.parent
        return None

    def register_plugin(self, plugin: Plugin) -> None:
        is_enabled = self._enabled_plugins.get(plugin.name, True)
        self._plugins[plugin.name] = LoadedPlugin(
            plugin=plugin,
            enabled=is_enabled,
        )

    def unregister_plugin(self, name: str) -> None:
        if name in self._plugins:
            del self._plugins[name]

    def enable_plugin(self, name: str) -> bool:
        if name not in self._plugins:
            return False
        self._plugins[name].enabled = True
        self._enabled_plugins[name] = True
        self._save_config()
        return True

    def disable_plugin(self, name: str) -> bool:
        if name not in self._plugins:
            return False
        self._plugins[name].enabled = False
        self._enabled_plugins[name] = False
        self._save_config()
        return True

    def is_plugin_enabled(self, name: str) -> bool:
        return self._plugins.get(name, LoadedPlugin(plugin=None)).enabled

    def get_plugin(self, name: str) -> Optional[Plugin]:
        loaded = self._plugins.get(name)
        return loaded.plugin if loaded else None

    def list_plugins(self, include_disabled: bool = False) -> List[str]:
        if include_disabled:
            return list(self._plugins.keys())
        return [
            name
            for name, loaded in self._plugins.items()
            if loaded.enabled and loaded.plugin
        ]

    def get_all_plugins(self) -> Dict[str, LoadedPlugin]:
        return self._plugins.copy()

    def get_plugin_info(self, name: str) -> Optional[Dict[str, Any]]:
        loaded = self._plugins.get(name)
        if not loaded or not loaded.plugin:
            return None
        plugin = loaded.plugin
        return {
            "name": plugin.name,
            "version": plugin.version,
            "description": plugin.description,
            "author": plugin.author,
            "author_email": plugin.author_email,
            "url": plugin.url,
            "license": plugin.license,
            "tags": plugin.tags,
            "dependencies": plugin.dependencies,
            "enabled": loaded.enabled,
            "error": loaded.error,
        }
