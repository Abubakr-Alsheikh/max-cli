"""Several files, a folder or a pattern for a one-file command (catalog.batch).

A command whose catalog param is `each` takes `target` as a list. It calls
`run_batch` first: that queues the work (`--queue`) or runs a batch, and
returns True when it did. For one plain file it returns False and the
command goes on with its own code, so one file looks exactly as before.
"""

import time
from pathlib import Path
from typing import Any, Callable, Optional

import typer
from rich.markup import escape
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn

from max_cli.common.exceptions import MaxError
from max_cli.common.logger import console, log_error, log_success

RECURSIVE_OPTION = typer.Option(
    False, "--recursive", help="With a folder or pattern: look in subfolders too."
)
REDO_OPTION = typer.Option(
    False,
    "--redo",
    help="With a folder or pattern: also run files whose result exists already.",
)
# No short flag: -q means --quality in several commands.
QUEUE_OPTION = typer.Option(
    False, "--queue", help="Run in the background; 'max queue status' shows it."
)
# How many failed files the summary names before "... and N more".
LISTED_FAILURES = 10


def run_batch(
    action_id: str,
    values: dict[str, Any],
    *,
    queue: bool = False,
    recursive: bool = False,
    redo: bool = False,
    force: bool = False,
    prepare: Optional[Callable[[], Any]] = None,
) -> bool:
    """Queue or run a batch; False for one plain file the command runs itself.

    `prepare` runs before a batch starts, e.g. to find (or offer to
    download) FFmpeg once instead of in every file's run.
    """
    from max_cli.core.catalog import get_action
    from max_cli.core.catalog.batch import enqueue_each, expand_each, is_batch

    action = get_action(action_id)
    raw = {name: _plain(value) for name, value in values.items()}
    try:
        if queue:
            if prepare is not None:
                prepare()
            tasks, found = enqueue_each(action, raw, recursive, redo)
            _say_clashes(found.clashes)
            _say_queued(len(tasks), found.done_already)
            return True
        if not is_batch(action, raw):
            return False
        found = expand_each(action, raw, recursive, redo)
    except MaxError as e:
        log_error(escape(str(e)))
        raise typer.Exit(1) from None
    _say_clashes(found.clashes)
    _say_found(len(found.files), found.done_already)
    if not found.files:
        return True
    if not _confirmed(action, len(found.files), force):
        console.print("[dim]Cancelled.[/dim]")
        return True
    if prepare is not None:
        prepare()
    _run(action, raw, found)
    return True


def _run(action: Any, raw: dict[str, Any], found: Any) -> None:
    from max_cli.core.catalog.activity import record
    from max_cli.core.catalog.batch import run_each

    with Progress(
        TextColumn("[cyan]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        bar = progress.add_task(f"{action.group} {action.name}", total=len(found.files))

        def on_file(path: Path, result: Any, error: str) -> None:
            mark = "[red]✗[/red]" if error else "[green]✓[/green]"
            progress.console.print(f"  {mark} {escape(path.name)}")
            progress.advance(bar)

        started = time.monotonic()
        result = run_each(action, raw, on_file=on_file, batch=found)
    record(action, raw, result, seconds=time.monotonic() - started, via="cli")
    failed = result.details.get("failed", [])
    if failed:
        log_error(escape(result.message))
        for item in failed[:LISTED_FAILURES]:
            console.print(
                f"  [red]{escape(Path(item['file']).name)}[/red]: {escape(item['error'])}"
            )
        if len(failed) > LISTED_FAILURES:
            console.print(f"  [dim]... and {len(failed) - LISTED_FAILURES} more[/dim]")
        raise typer.Exit(1)
    log_success(escape(result.message))


def _confirmed(action: Any, count: int, force: bool) -> bool:
    from rich.prompt import Confirm

    from max_cli.core.catalog.spec import Danger
    from max_cli.interface.confirm import skip_confirmation

    if action.danger == Danger.DELETES:
        if force:  # like one shred: asks whatever CONFIRM_DESTRUCTIVE says
            return True
        return Confirm.ask(
            f"[red]{action.name.capitalize()} {count} files? This can't be undone.[/red]"
        )
    if action.danger in (Danger.MOVES, Danger.OVERWRITES) and not skip_confirmation(
        force
    ):
        return Confirm.ask(
            f"[yellow]{action.group} {action.name} changes {count} files in place. "
            "Go on?[/yellow]"
        )
    return True


def _say_clashes(clashes: list[Path]) -> None:
    """Files left out because their result would overwrite another's."""
    if not clashes:
        return
    names = ", ".join(path.name for path in clashes[:LISTED_FAILURES])
    more = (
        f" and {len(clashes) - LISTED_FAILURES} more"
        if len(clashes) > LISTED_FAILURES
        else ""
    )
    console.print(
        f"[yellow]Left out {escape(names)}{more}: its result would have the same "
        "name as another file's. Run it on its own with -o.[/yellow]"
    )


def _say_found(count: int, done_already: list[Path]) -> None:
    if done_already:
        console.print(
            f"[dim]{len(done_already)} file{'s' if len(done_already) != 1 else ''} "
            "had their result already; --redo runs them again.[/dim]"
        )
    if count:
        console.print(f"[cyan]{count} file{'s' if count != 1 else ''} to do.[/cyan]")
    else:
        console.print("[green]Nothing to do.[/green]")


def _say_queued(count: int, done_already: list[Path]) -> None:
    from max_cli.core.engines.background_worker import start_background_worker

    if done_already:
        console.print(
            f"[dim]{len(done_already)} had their result already; "
            "--redo queues them too.[/dim]"
        )
    if not count:
        console.print("[green]Nothing to queue.[/green]")
        return
    start_background_worker()
    console.print(
        f"[green]Queued {count} job{'s' if count != 1 else ''}.[/green] "
        "[dim]They run in the background; 'max queue status' shows progress.[/dim]"
    )


def _plain(value: Any) -> Any:
    """Typer's Paths as text, the way the dashboard and the agent pass them."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value
