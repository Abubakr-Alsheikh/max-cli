"""Root command group that imports each command group only when it runs.

`max --help` lists every group from the static LAZY_GROUPS table without
importing any of them. `max video compress ...` imports only
`max_cli.interface.cli_media`. This keeps pydantic-settings, Rich prompts
and every engine out of startup (hardening decision D5).
"""

import importlib
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

# Typer 0.27+ bundles its own click (typer._click), older versions use the
# click package. Build everything from Typer's classes so both work, and
# type click objects as Any because the two click versions differ.
from typer.core import TyperCommand, TyperGroup


@dataclass(frozen=True)
class LazyGroupSpec:
    """Where a command group lives and how `max --help` describes it."""

    module: str
    help: str = ""
    hidden: bool = False
    attribute: str = "app"
    # Called with the loaded module, e.g. to hand it the full app.
    on_load: Optional[Callable[[object], None]] = None


LAZY_GROUPS: Dict[str, LazyGroupSpec] = {}


def lazy_group(name: str, spec: LazyGroupSpec) -> None:
    """Register a command group that loads on first use."""
    LAZY_GROUPS[name] = spec


def load_group(name: str) -> Any:
    """Import a lazy group's module and build its click command."""
    import typer

    spec = LAZY_GROUPS[name]
    module = importlib.import_module(spec.module)
    if spec.on_load is not None:
        spec.on_load(module)
    command = typer.main.get_command(getattr(module, spec.attribute))
    command.name = name
    if spec.help:
        command.help = spec.help
        command.short_help = spec.help
    command.hidden = spec.hidden
    return command


class LazyTyperGroup(TyperGroup):
    """TyperGroup that resolves LAZY_GROUPS entries on demand."""

    _rendering_help = False

    def list_commands(self, ctx: Any) -> List[str]:
        eager = super().list_commands(ctx)
        return [name for name in LAZY_GROUPS if name not in eager] + eager

    def get_command(self, ctx: Any, cmd_name: str) -> Optional[Any]:
        command: Any = super().get_command(ctx, cmd_name)
        if command is not None or cmd_name not in LAZY_GROUPS:
            return command
        if self._rendering_help:
            # The help screen needs only the name and one line of help.
            spec = LAZY_GROUPS[cmd_name]
            return TyperCommand(cmd_name, help=spec.help, hidden=spec.hidden)
        command = load_group(cmd_name)
        self.add_command(command, cmd_name)
        return command

    def format_help(self, ctx: Any, formatter: Any) -> None:
        self._rendering_help = True
        try:
            super().format_help(ctx, formatter)
        finally:
            self._rendering_help = False
