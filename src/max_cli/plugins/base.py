from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import typer


@dataclass
class PluginMetadata:
    """Metadata for a plugin."""

    name: str
    version: str
    description: str = ""
    author: str = ""
    author_email: str = ""
    url: str = ""
    license: str = ""
    tags: list[str] = field(default_factory=list)
    min_cli_version: Optional[str] = None
    dependencies: list[str] = field(default_factory=list)


@dataclass
class PluginContext:
    """Context passed to plugins during registration."""

    app: typer.Typer
    plugin_dir: Optional["Path"] = None
    config: dict[str, Any] = field(default_factory=dict)


class Plugin(ABC):
    _metadata: PluginMetadata

    @property
    def name(self) -> str:
        return self._metadata.name

    @property
    def version(self) -> str:
        return self._metadata.version

    @property
    def description(self) -> str:
        return self._metadata.description

    @property
    def metadata(self) -> PluginMetadata:
        return self._metadata

    @property
    def author(self) -> str:
        return self._metadata.author

    @property
    def author_email(self) -> str:
        return self._metadata.author_email

    @property
    def url(self) -> str:
        return self._metadata.url

    @property
    def license(self) -> str:
        return self._metadata.license

    @property
    def tags(self) -> list[str]:
        return self._metadata.tags

    @property
    def dependencies(self) -> list[str]:
        return self._metadata.dependencies

    @property
    def priority(self) -> int:
        return 100

    def validate(self) -> tuple[bool, Optional[str]]:
        """Validate plugin requirements. Returns (is_valid, error_message)."""
        return True, None

    def on_load(self, context: PluginContext) -> None:
        """Called when plugin is loaded."""

    def on_unload(self) -> None:
        """Called when plugin is unloaded."""

    @abstractmethod
    def register(self, app: typer.Typer) -> None:
        """Register commands with the CLI app."""
        pass

    def unregister(self, app: typer.Typer) -> None:
        """Unregister commands from the CLI app. Override if cleanup needed."""
        pass


class CLIPlugin(Plugin):
    """Plugin that adds CLI commands."""

    def __init__(
        self,
        name: str,
        version: str,
        description: str = "",
        author: str = "",
        author_email: str = "",
        url: str = "",
        license: str = "",
        tags: Optional[list[str]] = None,
        min_cli_version: Optional[str] = None,
        dependencies: Optional[list[str]] = None,
    ):
        self._metadata = PluginMetadata(
            name=name,
            version=version,
            description=description,
            author=author,
            author_email=author_email,
            url=url,
            license=license,
            tags=tags if tags is not None else [],
            min_cli_version=min_cli_version,
            dependencies=dependencies if dependencies is not None else [],
        )

    @property
    def command_name(self) -> str:
        return self.name.replace("-", "_").replace(" ", "_").lower()

    @property
    def help_text(self) -> str:
        return self.description


class EnginePlugin(Plugin):
    """Plugin that adds business logic/engine functionality."""

    def __init__(
        self,
        name: str,
        version: str,
        description: str = "",
        author: str = "",
        author_email: str = "",
        url: str = "",
        license: str = "",
        tags: Optional[list[str]] = None,
        min_cli_version: Optional[str] = None,
        dependencies: Optional[list[str]] = None,
    ):
        self._metadata = PluginMetadata(
            name=name,
            version=version,
            description=description,
            author=author,
            author_email=author_email,
            url=url,
            license=license,
            tags=tags if tags is not None else [],
            min_cli_version=min_cli_version,
            dependencies=dependencies if dependencies is not None else [],
        )


class PluginValidationError(Exception):
    """Raised when plugin validation fails."""

    pass


class PluginLoadError(Exception):
    """Raised when plugin fails to load."""

    pass
