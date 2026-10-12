"""One dim line after a command when a newer Max is out.

`start()` runs before the command: when a day has passed since the last
check, it asks PyPI in a background thread. `finish()` runs after the
command, waits for that thread at most NOTICE_WAIT_SECONDS, and prints the
line from the saved answer. Scripts and pipes see nothing; neither do
`max update`, the dashboard (it says so itself) or `--version`.
"""

import sys
import threading
from typing import Optional

NOTICE_WAIT_SECONDS = 1.0
# Commands that say it themselves, or where a line after the output hurts.
QUIET_FOR = frozenset(
    {"update", "dashboard", "--version", "-V", "--help", "--install-completion"}
)


def _is_terminal() -> bool:
    return sys.stdout.isatty()


def _wanted(arguments: list[str]) -> bool:
    from max_cli.config import settings

    if not settings.UPDATE_CHECK or not arguments:
        return False  # off, or a bare `max`, which opens the dashboard
    if arguments[0] in QUIET_FOR:
        return False
    return _is_terminal()


def start(arguments: Optional[list[str]] = None) -> Optional[threading.Thread]:
    """Start a check in the background when one is due; None when no notice
    should show at all."""
    if not _wanted(sys.argv[1:] if arguments is None else arguments):
        return None
    from max_cli.core.engines import updates

    thread = threading.Thread(target=updates.check, daemon=True)
    if updates.check_due():
        thread.start()
    return thread


def finish(thread: Optional[threading.Thread]) -> None:
    if thread is None:
        return
    if thread.is_alive():
        thread.join(NOTICE_WAIT_SECONDS)
    from max_cli.common.logger import console
    from max_cli.core.engines import updates

    status = updates.cached_status()
    if status.available:
        console.print(
            f"\n[dim]Max {status.latest} is out (you have {status.current}). "
            "Run [bold]max update[/bold] to get it.[/dim]"
        )
