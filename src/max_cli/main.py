import sys

import typer

from max_cli.common.exceptions import MaxError
from max_cli.core.cli.registry import register, init_plugins
from max_cli.common.logger import console

app = typer.Typer(
    name="max",
    help="MAX: The High-Performance CLI Utility.",
    add_completion=True,
    no_args_is_help=True,
)


def main():
    """Main entry point."""
    register(app)

    try:
        init_plugins(app)
        app()
    except MaxError as e:
        console.print(f"[bold red]X Error:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print("[bold red]!! Critical Error (Unexpected)[/bold red]")
        console.print(f"An error occurred: {e}")
        console.print(
            "[dim]If this persists, please report this to the developer.[/dim]"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
