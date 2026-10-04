"""Root command group that imports each command group only when it runs.

`max --help` lists every group from the static LAZY_GROUPS table without
importing any of them. `max video compress ...` imports only
`max_cli.interface.cli_media`. This keeps pydantic-settings, Rich prompts
and every engine out of startup (hardening decision D5).

It also routes a bare `max`: a person at a terminal gets the dashboard,
scripts and pipes get the help text (dashboard-first-ai-agent.md, D2). And
`max <text>` whose first word isn't a command goes to the AI agent as one
request (D1): `max "shrink every video in Downloads"`. A first word close to
a command name is a typo instead (`max vidoe compress`): click refuses it and
suggests the name.
"""

import importlib
import sys
from dataclasses import dataclass
from typing import Any, Optional

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


LAZY_GROUPS: dict[str, LazyGroupSpec] = {}

# How alike a first word and a command name must be (difflib ratio, 0 to 1)
# to count as a typo of it. "vidoe" scores 0.8 against "video"; plain words
# like "shrink" or "convert" stay well below.
TYPO_CUTOFF = 0.75


def is_interactive() -> bool:
    """A person is at the keyboard: stdin and stdout are both a terminal."""
    streams = (sys.stdin, sys.stdout)
    return all(stream is not None and stream.isatty() for stream in streams)


def lazy_group(name: str, spec: LazyGroupSpec) -> None:
    """Register a command group that loads on first use."""
    LAZY_GROUPS[name] = spec


def load_group(name: str) -> Any:
    """Import a lazy group's module and build its click command."""
    import typer

    spec = LAZY_GROUPS[name]
    module = importlib.import_module(spec.module)
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
    # What a bare `max` runs at an interactive terminal (D2).
    interactive_default = "dashboard"
    # What `max <text>` runs when <text> isn't a command (D1).
    agent_command = ("ai", "ask")

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        result: list[str] = super().parse_args(ctx, self.route(args))
        return result

    def route(self, args: list[str]) -> list[str]:
        """The command line to run: the dashboard for a bare `max` at a
        terminal (D2), `ai ask "<words>"` for words that aren't a command
        (D1), else the arguments as given."""
        if not args:
            return [self.interactive_default] if is_interactive() else args
        if not self._is_request(args):
            return args
        # Words up to the first option are the request; options such as
        # --dry-run stay options of `ai ask`.
        words = next(
            (index for index, arg in enumerate(args) if arg.startswith("-")),
            len(args),
        )
        return [*self.agent_command, " ".join(args[:words]), *args[words:]]

    def _is_request(self, args: list[str]) -> bool:
        """Words for the agent: not an option, not a command or group, and
        not a typo of one."""
        word = args[0]
        if word.startswith("-") or word in LAZY_GROUPS or word in self.commands:
            return False
        return not self._is_typo(args)

    def _is_typo(self, args: list[str]) -> bool:
        """`vidoe compress`, `vidoe` or `vidoe --help`: a mistyped command.
        `videos are too big` or `image to webp` stay requests: the word after
        them isn't a command of the group they look like."""
        matches = self._close_names(args[0])
        if not matches:
            return False
        if len(args) == 1 or args[1].startswith("-"):
            return True
        return any(args[1] in self._subcommands(name) for name in matches)

    def _subcommands(self, name: str) -> set[str]:
        """The commands of group `name`, loading it (only for a likely typo)."""
        if name not in LAZY_GROUPS:
            return set()
        return set(getattr(load_group(name), "commands", {}))

    def _close_names(self, word: str) -> list[str]:
        """Shown command and group names that `word` looks like a typo of."""
        if any(char.isspace() for char in word):
            return []
        import difflib

        shown = [name for name, spec in LAZY_GROUPS.items() if not spec.hidden]
        shown += [
            name
            for name, command in self.commands.items()
            if not command.hidden and name not in LAZY_GROUPS
        ]
        return difflib.get_close_matches(word.lower(), shown, cutoff=TYPO_CUTOFF)

    def resolve_command(self, ctx: Any, args: list[str]) -> Any:
        """Refuse a mistyped command with the names it looks like."""
        name = args[0] if args else ""
        if (
            name
            and not ctx.resilient_parsing
            and not name.startswith("-")
            and self.get_command(ctx, name) is None
        ):
            suggestions = self._close_names(name)
            if suggestions:
                names = ", ".join(repr(match) for match in suggestions)
                ctx.fail(f"No such command {name!r}. Did you mean {names}?")
        return super().resolve_command(ctx, args)

    def list_commands(self, ctx: Any) -> list[str]:
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
