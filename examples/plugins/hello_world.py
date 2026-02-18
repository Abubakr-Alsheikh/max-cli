"""
Example plugin demonstrating best practices for max-cli plugins.

This plugin shows:
- Proper metadata definition
- Command aliases
- Lifecycle hooks
- Error handling
- Configuration support

To use this plugin:
1. Copy this file to ~/.max_cli/plugins/hello_world.py
2. Run: max plugins list
3. Run: max hello --name "Your Name"
"""

import typer
from pathlib import Path
from typing import Optional

from max_cli.plugins.base import CLIPlugin, PluginContext


class HelloWorldPlugin(CLIPlugin):
    """A simple hello world plugin for demonstration."""

    def __init__(self) -> None:
        super().__init__(
            name="hello-world",
            version="1.0.0",
            description="A simple hello world plugin for demonstration",
            author="MAX CLI Team",
            author_email="team@max-cli.dev",
            url="https://github.com/max-cli/max-cli",
            license="MIT",
            tags=["demo", "example", "greeting"],
            min_cli_version="0.1.0",
            dependencies=[],
        )
        self.greeting_count = 0
        self.plugin_dir: Optional[Path] = None

    @property
    def priority(self) -> int:
        """Lower priority = registered earlier. Default is 100."""
        return 100

    def validate(self) -> tuple[bool, Optional[str]]:
        """Validate plugin requirements before loading."""
        return True, None

    def on_load(self, context: PluginContext) -> None:
        """Called when plugin is loaded."""
        self.plugin_dir = context.plugin_dir

    def on_unload(self) -> None:
        """Called when plugin is unloaded."""
        self.greeting_count = 0

    def register(self, app: typer.Typer) -> None:
        """Register commands with the CLI app."""

        @app.command("hello")
        @app.command("hi")  # Alias for convenience
        def hello(
            name: str = typer.Option("World", "--name", "-n", help="Name to greet"),
            verbose: bool = typer.Option(
                False, "--verbose", "-v", help="Verbose output"
            ),
        ) -> None:
            """Say hello to someone.

            Examples:
                max hello
                max hello --name Alice
                max hello -n Bob -v
            """
            self.greeting_count += 1
            greeting = f"Hello, {name}!"

            if verbose:
                greeting += f" This is greeting #{self.greeting_count}."
                greeting += " Welcome to Max CLI plugins!"

            typer.echo(greeting)

        @app.command("goodbye")
        @app.command("bye")  # Alias
        def goodbye(
            name: str = typer.Option(
                "World", "--name", "-n", help="Name to say goodbye to"
            ),
            see_you: bool = typer.Option(
                True, "--see-you/--no-see-you", help="Add 'See you soon!'"
            ),
        ) -> None:
            """Say goodbye to someone.

            Examples:
                max goodbye
                max goodbye --name Alice
                max goodbye -n Bob --no-see-you
            """
            message = f"Goodbye, {name}!"

            if see_you:
                message += " See you soon!"

            typer.echo(message)

        @app.command("greet-count")
        def greet_count() -> None:
            """Show how many times greetings have been used."""
            typer.echo(f"Total greetings: {self.greeting_count}")


plugin = HelloWorldPlugin()
