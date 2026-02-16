import typer

from max_cli.plugins.base import CLIPlugin


class HelloWorldPlugin(CLIPlugin):
    @property
    def name(self) -> str:
        return "hello-world"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "A simple hello world plugin for demonstration"

    def register(self, app: typer.Typer) -> None:
        @app.command("hello")
        def hello(
            name: str = typer.Option("World", "--name", "-n", help="Name to greet"),
            verbose: bool = typer.Option(
                False, "--verbose", "-v", help="Verbose output"
            ),
        ) -> None:
            """Say hello to someone."""
            greeting = f"Hello, {name}!"
            if verbose:
                greeting += " Welcome to Max CLI plugins!"
            typer.echo(greeting)

        @app.command("goodbye")
        def goodbye(
            name: str = typer.Option(
                "World", "--name", "-n", help="Name to say goodbye to"
            ),
        ) -> None:
            """Say goodbye to someone."""
            typer.echo(f"Goodbye, {name}!")
