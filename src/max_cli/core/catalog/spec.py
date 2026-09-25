"""The types every catalog entry is built from (PLANS/active/command-catalog.md).

A catalog entry describes one action once. The CLI is checked against it, the
dashboard builds its forms from it, and the AI agent gets its tools from it.
Nothing in this module imports an engine or a heavy library.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ParamKind(str, Enum):
    TEXT = "text"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    CHOICE = "choice"
    FILE = "file"  # an existing input file (or a glob pattern, where noted)
    FOLDER = "folder"
    OUTPUT = "output"  # a file the action writes
    URL = "url"


PATH_KINDS = frozenset({ParamKind.FILE, ParamKind.FOLDER, ParamKind.OUTPUT})


class Danger(str, Enum):
    """What an action does to your files. Callers confirm before MOVES and up."""

    NONE = "none"
    WRITES_NEW = "writes_new"
    MOVES = "moves"
    OVERWRITES = "overwrites"
    DELETES = "deletes"


class Surface(str, Enum):
    CLI = "cli"
    DASHBOARD = "dashboard"
    AGENT = "agent"


ALL_SURFACES = frozenset(Surface)
CLI_ONLY = frozenset({Surface.CLI})


class _Required:
    def __repr__(self) -> str:
        return "REQUIRED"


REQUIRED: Any = _Required()


@dataclass(frozen=True)
class Param:
    name: str  # the operation's argument name
    kind: ParamKind
    help: str
    default: Any = REQUIRED
    choices: tuple[str, ...] = ()
    cli: tuple[
        str, ...
    ] = ()  # CLI spellings such as ("--format", "-f"); empty = positional
    advanced: bool = False

    @property
    def required(self) -> bool:
        return self.default is REQUIRED


@dataclass(frozen=True)
class Action:
    group: str
    name: str  # the CLI command name
    summary: str
    operation: str  # "module.path:function", imported when the action runs
    params: tuple[Param, ...]
    danger: Danger = Danger.WRITES_NEW
    queueable: bool = False
    surfaces: frozenset[Surface] = ALL_SURFACES

    @property
    def id(self) -> str:
        return f"{self.group}.{self.name}"

    def param(self, name: str) -> Param:
        for param in self.params:
            if param.name == name:
                return param
        raise KeyError(f"{self.id} has no parameter '{name}'")


@dataclass(frozen=True)
class Group:
    name: str
    summary: str
    actions: tuple[Action, ...]

    def action(self, name: str) -> Action:
        for action in self.actions:
            if action.name == name:
                return action
        raise KeyError(f"Group '{self.name}' has no action '{name}'")
