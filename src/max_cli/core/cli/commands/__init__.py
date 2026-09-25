"""Command groups registered eagerly. Built-in groups load lazily (see registry)."""
from max_cli.core.cli.commands import plugins as plugin_commands

__all__ = ["plugin_commands"]
