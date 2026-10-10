"""The types every catalog entry is built from (PLANS/active/command-catalog.md).

A catalog entry describes one action once. The CLI is checked against it, the
dashboard builds its forms from it, and the AI agent gets its tools from it.
Nothing in this module imports an engine or a heavy library.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


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
    SECRET = "secret"  # text the dashboard masks, e.g. a password


PATH_KINDS = frozenset({ParamKind.FILE, ParamKind.FOLDER, ParamKind.OUTPUT})
# Separates the values of a `multiple` param typed into one form field.
LIST_SEPARATOR = ";"


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
class Setting:
    """A default read from the user's config when the action runs, e.g. Setting("GRAB_QUALITY")."""

    name: str

    def value(self) -> Any:
        from max_cli.config import settings

        return getattr(settings, self.name)


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
    # Takes a list: repeated options (-f a -f b) or several arguments on the
    # CLI, a JSON array from the agent, LIST_SEPARATOR-separated form text.
    multiple: bool = False
    # One file per run, but callers may give several files, a folder or a
    # pattern: catalog.batch runs the action once per file. The operation
    # still takes one path.
    each: bool = False
    # For an `each` param: the file kinds (common.file_kinds) a folder
    # gives; empty gives every file.
    kinds: tuple[str, ...] = ()

    @property
    def required(self) -> bool:
        return self.default is REQUIRED

    def resolved_default(self) -> Any:
        """The default with any Setting read from the config."""
        if isinstance(self.default, Setting):
            return self.default.value()
        return self.default


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
    # The default output's name, from the input's {stem} and {suffix} and
    # any argument ({format}), e.g. "{stem}_compressed.mp4". A batch skips
    # inputs whose output exists. Empty: no single output file per input.
    output_name: str = ""
    # When to use this action rather than a similar one, by action id
    # ("Not for track numbers: audio.batch"). The agent reads it in
    # load_group; tests/test_catalog.py checks the ids it names exist.
    guide: str = ""

    def each_param(self) -> Optional[Param]:
        """The param a batch fills with one file per run, if any."""
        return next((param for param in self.params if param.each), None)

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
