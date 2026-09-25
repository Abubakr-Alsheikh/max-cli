import sys

import typer

from max_cli.common.exceptions import MaxError
from max_cli.core.cli.lazy_group import LazyTyperGroup
from max_cli.core.cli.registry import register, init_plugins

app = typer.Typer(
    cls=LazyTyperGroup,
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
    except SystemExit as exit_signal:
        # Commands often report a failure with log_error and then return, so
        # click exits 0. Exit 1 instead, so scripts can detect the failure.
        from max_cli.common.exit_status import error_reported

        if exit_signal.code in (0, None) and error_reported():
            sys.exit(1)
        raise
    except MaxError as e:
        from max_cli.common.logger import console

        console.print(f"[bold red]X Error:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        from max_cli.common.logger import console

        console.print("[bold red]!! Critical Error (Unexpected)[/bold red]")
        console.print(f"An error occurred: {e}")
        console.print(
            "[dim]If this persists, please report this to the developer.[/dim]"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
