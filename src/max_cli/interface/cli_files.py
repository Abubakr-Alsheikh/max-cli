"""`max files`: parse options, ask before destructive steps, call
core/operations/files.py, print the result.

The catalog entries in core/catalog/groups/files.py describe the same
commands; tests/test_catalog_drift.py fails when the two disagree.
"""

from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

import typer
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm
from rich.text import Text

from max_cli.common.exceptions import MaxError, ResourceNotFoundError, ValidationError
from max_cli.common.logger import console, log_error, log_success
from max_cli.core.operations import files as files_ops

app = typer.Typer()

Result = TypeVar("Result")

ACTION_LIST_LIMIT = 20
ACTION_LIST_HEAD = 10
UNDO_HINT = "[dim]Undo with: max files undo[/dim]"


def _get_organizer():
    from max_cli.core.engines.file_organizer import FileOrganizer

    return FileOrganizer()


def _get_ai_engine():
    from max_cli.core.engines.ai_engine import AIEngine

    return AIEngine()


def _run(
    operation: Callable[..., Result],
    fail_message: Optional[str] = None,
    **kwargs: Any,
) -> Optional[Result]:
    """Call a files operation and report its errors.

    Bad input (a missing file, not a folder) exits 1. Other failures print
    `fail_message` and return None; with no fail_message they exit 1.
    """
    try:
        return operation(**kwargs)
    except (ResourceNotFoundError, ValidationError) as e:
        log_error(escape(str(e)))
        raise typer.Exit(1) from None
    except MaxError as e:
        if fail_message is None:
            log_error(escape(str(e)))
            raise typer.Exit(1) from None
        log_error(escape(f"{fail_message}: {e}"))
        return None


def _print_actions(actions: list[str]) -> None:
    shown = actions[:ACTION_LIST_HEAD] if len(actions) > ACTION_LIST_LIMIT else actions
    for action in shown:
        console.print(f"  {escape(action)}")
    if len(shown) < len(actions):
        console.print(f"  ... and {len(actions) - len(shown)} more.")


@app.command("order")
@app.command("ord", hidden=True)
def order_files(
    folder: Path = typer.Argument(..., help="The folder containing files to order."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Simulate the rename without changing files."
    ),
    force: bool = typer.Option(
        False, "-f", "--force", help="Skip confirmation prompt."
    ),
    start: int = typer.Option(
        1, "--start", help="Number to start counting from (default 1)."
    ),
):
    """
    Rename all files in a folder with a number prefix (e.g. 1_file.txt).
    Skips files that are already numbered.
    """
    organizer = _get_organizer()
    found = _run(files_ops.files_to_order, folder=folder, organizer=organizer)
    if not found:
        console.print("[yellow]Folder is empty. Nothing to do.[/yellow]")
        return

    if not dry_run and not force:
        console.print(
            Panel(
                Text(f"Target: {folder}\nFiles found: {len(found)}", justify="center"),
                title="[bold yellow]⚠ Bulk Rename Warning[/bold yellow]",
                border_style="yellow",
            )
        )
        if not Confirm.ask("Are you sure you want to rename these files?"):
            console.print("[red]Aborted.[/red]")
            raise typer.Exit()

    console.print(
        f"[bold cyan]Processing files starting at index {start}...[/bold cyan]"
    )
    result = _run(
        files_ops.order,
        folder=folder,
        dry_run=dry_run,
        start=start,
        organizer=organizer,
    )
    if result is None:
        return
    details = result.details
    _print_actions(details["actions"])

    summary_color = "yellow" if dry_run else "green"
    console.print(f"\n[{summary_color}]Summary:[/{summary_color}]")
    console.print(f"  Files Processed: {details['renamed']}")
    console.print(f"  Files Skipped:   {details['skipped']}")
    if dry_run:
        console.print(
            "\n[bold yellow]This was a Dry Run. No files were changed.[/bold yellow]"
        )
    else:
        log_success(escape(result.message))
        console.print(UNDO_HINT)


@app.command("smart-sort")
@app.command("ss", hidden=True)
def smart_sort(
    path: Path = typer.Argument(".", help="Folder to organize."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show changes without moving."
    ),
):
    """
    AI-powered file organization. Groups files by content/meaning, not just extension.
    """
    with console.status("[cyan]Analyzing files with AI...[/cyan]"):
        result = _run(
            files_ops.smart_sort,
            "Smart sort failed",
            path=path,
            dry_run=dry_run,
            organizer=_get_organizer(),
            ai_engine=_LazyAIEngine(),
        )
    if result is None:
        return
    details = result.details
    if not details["actions"] and not details["moved"]:
        console.print(f"[yellow]{escape(result.message)}[/yellow]")
        return
    for action in details["actions"]:
        console.print(f"  {escape(action)}")
    if dry_run:
        console.print(f"[yellow]{escape(result.message)}[/yellow]")
    else:
        log_success(escape(result.message))
        console.print(UNDO_HINT)


class _LazyAIEngine:
    """Builds the AI engine only if the folder has files to sort."""

    def categorize_files(self, files: list[str]) -> dict[str, str]:
        categories: dict[str, str] = _get_ai_engine().categorize_files(files)
        return categories


@app.command("duplicates")
@app.command("dup", hidden=True)
def find_duplicates(
    folder: Path = typer.Argument(".", help="Folder to scan for duplicates."),
    recursive: bool = typer.Option(
        False, "-r", "--recursive", help="Scan subdirectories as well."
    ),
    delete: bool = typer.Option(
        False, "-d", "--delete", help="Delete duplicates (keeps one copy)."
    ),
    force: bool = typer.Option(
        False, "-f", "--force", help="Delete without asking for confirmation."
    ),
):
    """
    Find and optionally remove duplicate files based on content.
    """
    console.print(f"[cyan]Scanning for duplicates in {escape(str(folder))}...[/cyan]")
    organizer = _get_organizer()
    try:
        groups = files_ops.find_duplicates(folder, recursive, organizer=organizer)
    except ValidationError as e:
        log_error(escape(str(e)))
        raise typer.Exit(code=1) from None
    except MaxError as e:
        log_error(escape(f"Error finding duplicates: {e}"))
        return

    found = files_ops.duplicates(folder, recursive, organizer=organizer, groups=groups)
    if not groups:
        console.print(f"[green]{escape(found.message)}[/green]")
        return
    console.print(f"[yellow]{escape(found.message)}:[/yellow]\n")
    for paths in found.details["groups"]:
        console.print("[bold]Duplicate group:[/bold]")
        for path in paths:
            console.print(f"  {escape(path)}")
        console.print()

    if not delete:
        console.print("[dim]Run with --delete to remove duplicates[/dim]")
        return
    count = found.details["duplicate_count"]
    if not force and not Confirm.ask(
        f"Delete {count} duplicate(s)? A backup is kept for undo."
    ):
        console.print("[dim]Cancelled. Nothing was deleted.[/dim]")
        return

    result = _run(
        files_ops.duplicates,
        "Error deleting duplicates",
        folder=folder,
        recursive=recursive,
        delete=True,
        organizer=organizer,
        groups=groups,
    )
    if result is None:
        return
    log_success(escape(result.message))
    for error in result.details["errors"]:
        console.print(f"  [red]{escape(str(error))}[/red]")
    console.print(UNDO_HINT)


@app.command("shred")
def secure_delete(
    target: Path = typer.Argument(..., help="File to securely delete."),
    passes: int = typer.Option(
        3, "--passes", "-p", help="Number of overwrite passes (default 3)."
    ),
    force: bool = typer.Option(False, "-f", "--force", help="Skip confirmation."),
):
    """
    Securely delete a file by overwriting with random data before deletion.
    """
    _run(files_ops.check_shred_target, target=target)
    if not force:
        console.print(
            f"[red]⚠ This will PERMANENTLY destroy: {escape(target.name)}. "
            "No backup is kept, and `max files undo` can't restore it.[/red]"
        )
        if not Confirm.ask("Are you sure?"):
            console.print("[yellow]Aborted.[/yellow]")
            return

    console.print(f"[cyan]Shredding {escape(target.name)} ({passes} passes)...[/cyan]")
    result = _run(
        files_ops.shred,
        "Secure delete failed",
        target=target,
        passes=passes,
        organizer=_get_organizer(),
    )
    if result:
        log_success(escape(result.message))


@app.command("preview")
def file_preview(
    target: Path = typer.Argument(..., help="File to preview."),
    lines: int = typer.Option(
        20, "-n", "--lines", help="Number of lines to show for text files."
    ),
):
    """
    Show file metadata and preview content.
    """
    from max_cli.common.utils import format_size

    result = _run(files_ops.preview, target=target, lines=lines)
    assert result is not None  # preview raises instead of returning None
    info = result.details

    console.print(Panel(Text(info["name"], style="bold cyan"), border_style="cyan"))
    console.print(Text.assemble(("Path: ", "bold"), info["path"]))
    console.print(Text.assemble(("Type: ", "bold"), info["type"]))
    console.print(f"[bold]Size:[/bold] {format_size(info['size'])}")
    console.print(f"[bold]Created:[/bold] {info['created']}")
    console.print(f"[bold]Modified:[/bold] {info['modified']}")
    console.print(f"[bold]Accessed:[/bold] {info['accessed']}")
    console.print()

    if "lines" in info:
        console.print("[bold]Preview:[/bold]")
        for number, line in enumerate(info["lines"], 1):
            console.print(Text(f"{number:3}: {line}"))
        if info["more_lines"]:
            console.print(f"[dim]... and {info['more_lines']} more lines[/dim]")
    elif "image" in info:
        image = info["image"]
        console.print("[bold]Image Dimensions:[/bold]")
        console.print(f"  {image['width']} x {image['height']} pixels")
        console.print(f"  Mode: {image['mode']}")
    elif "pdf" in info:
        pdf = info["pdf"]
        console.print("[bold]PDF Info:[/bold]")
        console.print(f"  Pages: {pdf['pages']}")
        console.print(Text(f"  Title: {pdf['title']}"))
        console.print(Text(f"  Author: {pdf['author']}"))
    if "note" in info:
        console.print(f"[dim]{escape(info['note'])}[/dim]")


@app.command("backup")
def backup_file(
    target: Path = typer.Argument(..., help="File to backup."),
    label: str = typer.Option("manual", "-l", "--label", help="Label for this backup."),
):
    """
    Create a backup of a file.
    """
    result = _run(
        files_ops.backup,
        "Backup failed",
        target=target,
        label=label,
        organizer=_get_organizer(),
    )
    if result:
        log_success(escape(result.message))


@app.command("backups")
def list_backups(
    filter: str = typer.Option(None, "--filter", "-f", help="Filter by filename."),
    restore: Path = typer.Option(
        None, "--restore", "-r", help="Restore a specific backup."
    ),
    output: Path = typer.Option(None, "-o", help="Restore to specific directory."),
):
    """
    List and manage backups.
    """
    from max_cli.common.utils import format_size

    result = _run(
        files_ops.backups,
        "Restore failed" if restore else "Listing backups failed",
        filter=filter,
        restore=restore,
        output=output,
        organizer=_get_organizer(),
    )
    if result is None:
        return
    if restore:
        log_success(escape(result.message))
        return
    found = result.details["backups"]
    if not found:
        console.print(f"[yellow]{escape(result.message)}[/yellow]")
        return
    console.print(f"[cyan]{escape(result.message)}:[/cyan]\n")
    for entry in found:
        console.print(Text(entry["name"], style="bold"))
        console.print(f"  Size: {format_size(entry['size'])}")
        console.print(f"  Created: {entry['created']}")
        console.print(Text(f"  Path: {entry['path']}"))
        console.print()


@app.command("backup-cleanup")
def cleanup_backups(
    days: int = typer.Option(
        30, "-d", "--days", help="Remove backups older than N days."
    ),
    force: bool = typer.Option(False, "-f", "--force", help="Skip confirmation."),
):
    """
    Clean up old backups to save space.
    """
    if not force:
        console.print(
            f"[yellow]This will remove backups older than {days} days.[/yellow]"
        )
        if not Confirm.ask("Continue?"):
            console.print("[yellow]Aborted.[/yellow]")
            return

    result = _run(
        files_ops.backup_cleanup,
        "Cleanup failed",
        days=days,
        organizer=_get_organizer(),
    )
    if result:
        log_success(escape(result.message))


@app.command("undo")
def undo_last():
    """Undo the last file operation (rename, move, delete)."""
    from max_cli.common.transaction_log import TransactionError

    try:
        result = files_ops.undo()
    except TransactionError as e:
        log_error(escape(f"Undo failed: {e}"))
        console.print(
            "[yellow]Some files may have been partially restored. "
            "Check the transaction log for details.[/yellow]"
        )
        raise typer.Exit(code=1) from None

    steps = result.details.get("steps")
    if steps is None:
        console.print(f"[yellow]{escape(result.message)}[/yellow]")
        if "command" in result.details:
            console.print(
                f"[dim]Command was: {escape(result.details['command'])} "
                f"at {result.details['timestamp']}[/dim]"
            )
        return
    console.print(f"[cyan]Undid: {escape(result.details['command'])}[/cyan]")
    for step in steps:
        console.print(f"  [green]+[/green] {escape(step)}")
    log_success(escape(result.message))


@app.command("history")
@app.command("hist", hidden=True)
def transaction_history(
    limit: int = typer.Option(10, "-n", "--limit", help="Number of entries to show."),
    verbose: bool = typer.Option(
        False, "-v", "--verbose", help="Show individual operations."
    ),
):
    """Show recent file operation history."""
    from datetime import datetime

    result = files_ops.history(limit=limit, verbose=verbose)
    groups = result.details["groups"]
    if not groups:
        console.print(f"[yellow]{escape(result.message)}[/yellow]")
        return

    console.print(f"[cyan]{escape(result.message)}:[/cyan]\n")
    for group in groups:
        undone = group["undo_status"] == "undone"
        status_icon = "✓" if undone else "•"
        status_color = "dim" if undone else "cyan"
        try:
            time_str = datetime.fromisoformat(group["timestamp"]).strftime(
                "%Y-%m-%d %H:%M"
            )
        except (ValueError, TypeError):
            time_str = group["timestamp"]

        console.print(
            f"  [{status_color}]{status_icon}[/{status_color}] "
            f"[bold]{escape(group['command'])}[/bold] — {time_str}"
        )
        console.print(
            f"     ID: {group['group_id']} | "
            f"Operations: {group['operation_count']} | "
            f"Status: {group['status']}"
        )
        if group["undo_status"]:
            console.print(f"     Undo: {group['undo_status']}")
        for step in group.get("operations", []):
            original = step["original_path"] or "(none)"
            new = step["new_path"] or "(none)"
            console.print(Text(f"       {step['op_type']}: {original} -> {new}"))
        console.print()

    console.print("[dim]Undo the last operation with: max files undo[/dim]")
