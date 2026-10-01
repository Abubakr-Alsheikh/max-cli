import sys

import typer

from max_cli.common.exceptions import MaxError
from max_cli.core.cli.lazy_group import LazyTyperGroup
from max_cli.core.cli.registry import init_plugins, register

app = typer.Typer(
    cls=LazyTyperGroup,
    name="max",
    help="MAX: The High-Performance CLI Utility.",
    add_completion=True,
    no_args_is_help=True,
)


UTF8_NAMES = frozenset({"utf-8", "utf8"})


def tolerate_unencodable_output() -> None:
    """Print a character the output's encoding lacks as "?" instead of crashing.

    Output redirected to a file or a pipe on Windows uses the code page
    (cp1252, cp1256 ...), which has no spinner frames or emoji. A spinner
    raised UnicodeEncodeError halfway through `max audio organize > log.txt`.
    """
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", "") or "").lower()
        if encoding not in UTF8_NAMES and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def main():
    """Main entry point."""
    tolerate_unencodable_output()
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
