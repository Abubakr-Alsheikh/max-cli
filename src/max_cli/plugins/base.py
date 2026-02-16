from abc import ABC, abstractmethod
from typing import Any


class Plugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        pass

    @property
    def description(self) -> str:
        return ""

    @abstractmethod
    def register(self, app: Any) -> None:
        pass

    def unregister(self, app: Any) -> None:
        pass


class CLIPlugin(Plugin):
    @property
    def command_name(self) -> str:
        return self.name.replace("-", "_").replace(" ", "_").lower()

    @property
    def help_text(self) -> str:
        return self.description


class EnginePlugin(Plugin):
    pass
