import typer
from pathlib import Path
from rich.prompt import Confirm
from rich.panel import Panel
from rich.text import Text

from max_cli.common.logger import console, log_error, log_success

app = typer.Typer()


def _get_organizer():
    from max_cli.core.engines.file_organizer import FileOrganizer

    return FileOrganizer()


def _get_ai_engine():
    from max_cli.core.engines.ai_engine import AIEngine

    return AIEngine()


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

    if not folder.is_dir():
        log_error(f"'{folder}' is not a directory.")
        raise typer.Exit(code=1)

    # 1. Get stats first to show the user what will happen
    try:
        org = _get_organizer()
        files = org.scan_directory(folder)
    except Exception as e:
        log_error(str(e))
        raise typer.Exit(code=1)

    if not files:
        console.print("[yellow]Folder is empty. Nothing to do.[/yellow]")
        return

    # 2. Confirmation (Unless forced or dry-run)
    if not dry_run and not force:
        console.print(
            Panel(
                Text(f"Target: {folder}\nFiles found: {len(files)}", justify="center"),
                title="[bold yellow]⚠ Bulk Rename Warning[/bold yellow]",
                border_style="yellow",
            )
        )
        if not Confirm.ask("Are you sure you want to rename these files?"):
            console.print("[red]Aborted.[/red]")
            raise typer.Exit()

    # 3. Execute
    console.print(
        f"[bold cyan]Processing files starting at index {start}...[/bold cyan]"
    )

    txn = None
    if not dry_run:
        from max_cli.common.transaction_log import TransactionLog

        txn = TransactionLog(command="files order")

    results = _get_organizer().order_files(
        folder, dry_run=dry_run, start_index=start, transaction_log=txn
    )

    if txn:
        txn.save()

    actions = results["actions"]
    if len(actions) > 20:
        for action in actions[:10]:
            console.print(f"  {action}")
        console.print(f"  ... and {len(actions) - 10} more.")
    else:
        for action in actions:
            console.print(f"  {action}")

    summary_color = "green" if not dry_run else "yellow"
    console.print(f"\n[{summary_color}]Summary:[/ {summary_color}]")
    console.print(f"  Files Processed: {results['renamed']}")
    console.print(f"  Files Skipped:   {results['skipped']}")

    if dry_run:
        console.print(
            "\n[bold yellow]This was a Dry Run. No files were changed.[/bold yellow]"
        )
    else:
        log_success("File ordering complete!")
        console.print("[dim]Undo with: max files undo[/dim]")


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
    files = [
        f.name for f in path.iterdir() if f.is_file() and not f.name.startswith(".")
    ]

    if not files:
        console.print("[yellow]No files to organize.[/yellow]")
        return

    console.print(f"[cyan]Analyzing {len(files)} files with AI...[/cyan]")

    ai_eng = _get_ai_engine()
    categories = ai_eng.categorize_files(files)

    txn = None
    if not dry_run:
        from max_cli.common.transaction_log import TransactionLog

        txn = TransactionLog(command="files smart-sort")

    results = _get_organizer().smart_sort(
        path, categories, dry_run=dry_run, transaction_log=txn
    )

    if txn:
        txn.save()

    for action in results["actions"]:
        console.print(f"  {action}")

    if not dry_run:
        log_success(f"Successfully organized {results['moved']} files.")
        console.print("[dim]Undo with: max files undo[/dim]")
    else:
        console.print("[yellow]Dry run complete. No files moved.[/yellow]")


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
):
    """
    Find and optionally remove duplicate files based on content.
    """
    if not folder.is_dir():
        log_error(f"'{folder}' is not a directory.")
        raise typer.Exit(code=1)

    console.print(f"[cyan]Scanning for duplicates in {folder}...[/cyan]")

    try:
        org = _get_organizer()
        duplicates = org.find_duplicates(folder, recursive=recursive)

        if not duplicates:
            console.print("[green]No duplicates found![/green]")
            return

        total_dupes = sum(len(v) - 1 for v in duplicates.values())
        console.print(
            f"[yellow]Found {total_dupes} duplicate(s) in {len(duplicates)} group(s):[/yellow]\n"
        )

        for hash_val, paths in duplicates.items():
            console.print("[bold]Duplicate group:[/bold]")
            for p in paths:
                console.print(f"  {p}")
            console.print()

        if delete:
            from max_cli.common.transaction_log import TransactionLog

            txn = TransactionLog(command="files duplicates --delete")

            results = org.delete_duplicates(
                folder, duplicates, transaction_log=txn, auto_backup=True
            )

            txn.save()

            log_success(f"Removed {results['removed']} duplicate(s).")
            if results["errors"]:
                for err in results["errors"]:
                    console.print(f"  [red]{err}[/red]")
            console.print("[dim]Undo with: max files undo[/dim]")
        else:
            console.print("[dim]Run with --delete to remove duplicates[/dim]")

    except Exception as e:
        log_error(f"Error finding duplicates: {e}")


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
    if not target.exists():
        log_error(f"File not found: {target}")
        raise typer.Exit(1)

    if target.is_dir():
        log_error("Cannot shred directories. Use rm -r instead.")
        raise typer.Exit(1)

    if not force:
        console.print(f"[red]⚠ This will PERMANENTLY destroy: {target.name}[/red]")
        if not Confirm.ask("Are you sure?"):
            console.print("[yellow]Aborted.[/yellow]")
            return

    console.print(f"[cyan]Shredding {target.name} ({passes} passes)...[/cyan]")

    try:
        from max_cli.common.transaction_log import TransactionLog

        txn = TransactionLog(command="files shred")

        org = _get_organizer()
        org.secure_delete(target, passes=passes, transaction_log=txn, auto_backup=True)
        txn.save()
        log_success(f"File securely deleted: {target.name}")
        console.print("[dim]Undo with: max files undo (restores from backup)[/dim]")
    except Exception as e:
        log_error(f"Secure delete failed: {e}")


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
    from datetime import datetime
    from max_cli.common.utils import format_size

    if not target.exists():
        log_error(f"File not found: {target}")
        raise typer.Exit(1)

    stat = target.stat()

    console.print(Panel(f"[bold cyan]{target.name}[/bold cyan]", border_style="cyan"))

    console.print(f"[bold]Path:[/bold] {target.absolute()}")
    console.print(f"[bold]Type:[/bold] {target.suffix or 'No extension'}")
    console.print(f"[bold]Size:[/bold] {format_size(stat.st_size)}")
    console.print(f"[bold]Created:[/bold] {datetime.fromtimestamp(stat.st_ctime)}")
    console.print(f"[bold]Modified:[/bold] {datetime.fromtimestamp(stat.st_mtime)}")
    console.print(f"[bold]Accessed:[/bold] {datetime.fromtimestamp(stat.st_atime)}")

    console.print()

    text_extensions = {
        ".txt",
        ".md",
        ".py",
        ".js",
        ".json",
        ".yaml",
        ".yml",
        ".xml",
        ".html",
        ".css",
        ".sh",
        ".bat",
        ".ps1",
        ".ini",
        ".cfg",
        ".conf",
        ".log",
    }

    if target.suffix.lower() in text_extensions:
        try:
            content = target.read_text(encoding="utf-8", errors="ignore")
            preview_lines = content.splitlines()[:lines]
            console.print("[bold]Preview:[/bold]")
            for i, line in enumerate(preview_lines, 1):
                console.print(f"{i:3}: {line}")
            if len(content.splitlines()) > lines:
                console.print(
                    f"[dim]... and {len(content.splitlines()) - lines} more lines[/dim]"
                )
        except Exception as e:
            console.print(f"[yellow]Could not read file content: {e}[/yellow]")
    elif target.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}:
        console.print("[bold]Image Dimensions:[/bold] (requires PIL)")
        try:
            from PIL import Image

            with Image.open(target) as img:
                console.print(f"  {img.width} x {img.height} pixels")
                console.print(f"  Mode: {img.mode}")
        except Exception:
            console.print("  [dim]Could not read image info[/dim]")
    elif target.suffix.lower() == ".pdf":
        console.print("[bold]PDF Info:[/bold] (requires PyMuPDF)")
        try:
            import fitz

            doc = fitz.open(target)
            console.print(f"  Pages: {len(doc)}")
            console.print(f"  Title: {doc.metadata.get('title', 'N/A')}")
            console.print(f"  Author: {doc.metadata.get('author', 'N/A')}")
        except Exception:
            console.print("  [dim]Could not read PDF info[/dim]")
    else:
        console.print("[dim]Preview not available for this file type[/dim]")


@app.command("backup")
def backup_file(
    target: Path = typer.Argument(..., help="File to backup."),
    label: str = typer.Option("manual", "-l", "--label", help="Label for this backup."),
):
    """
    Create a backup of a file.
    """
    if not target.exists():
        log_error(f"File not found: {target}")
        raise typer.Exit(1)

    try:
        org = _get_organizer()
        backup_path = org.create_backup(target, label=label)
        log_success(f"Backup created: {backup_path}")
    except Exception as e:
        log_error(f"Backup failed: {e}")


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
    from datetime import datetime
    from max_cli.common.utils import format_size

    if restore:
        try:
            org = _get_organizer()
            restored = org.restore_backup(restore, output)
            log_success(f"Restored: {restored}")
        except Exception as e:
            log_error(f"Restore failed: {e}")
        return

    org = _get_organizer()
    backups = org.list_backups(filter)

    if not backups:
        console.print("[yellow]No backups found.[/yellow]")
        return

    console.print(f"[cyan]Found {len(backups)} backup(s):[/cyan]\n")

    for b in backups:
        console.print(f"[bold]{b['name']}[/bold]")
        console.print(f"  Size: {format_size(b['size'])}")
        console.print(f"  Created: {datetime.fromtimestamp(b['created'])}")
        console.print(f"  Path: {b['path']}")
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

    try:
        org = _get_organizer()
        removed = org.cleanup_old_backups(days)
        log_success(f"Removed {removed} old backup(s)")
    except Exception as e:
        log_error(f"Cleanup failed: {e}")


@app.command("undo")
def undo_last():
    """Undo the last file operation (rename, move, delete)."""
    from max_cli.common.transaction_log import TransactionLog, TransactionError

    latest = TransactionLog.get_latest_group()
    if not latest:
        console.print("[yellow]No transaction history found. Nothing to undo.[/yellow]")
        return

    if latest["undo_status"] == "undone":
        console.print(
            f"[yellow]Last transaction ({latest['group_id']}) is already undone.[/yellow]"
        )
        console.print(
            f"[dim]Command was: {latest['command']} at {latest['timestamp']}[/dim]"
        )
        return

    console.print(
        f"[cyan]Undoing: {latest['command']} "
        f"({latest['operation_count']} operations)...[/cyan]"
    )

    try:
        txn = TransactionLog.load(latest["group_id"])
        results = txn.undo()

        for msg in results:
            console.print(f"  [green]+[/green] {msg}")

        log_success("Undo complete! Files have been restored.")
    except TransactionError as e:
        log_error(f"Undo failed: {e}")
        console.print(
            "[yellow]Some files may have been partially restored. "
            "Check the transaction log for details.[/yellow]"
        )
        raise typer.Exit(code=1)


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

    from max_cli.common.transaction_log import TransactionLog

    groups = TransactionLog.list_groups()
    if not groups:
        console.print("[yellow]No transaction history found.[/yellow]")
        return

    console.print(
        f"[cyan]Recent file operations (showing {min(limit, len(groups))}):[/cyan]\n"
    )

    for g in groups[:limit]:
        status_icon = "✓" if g["undo_status"] == "undone" else "•"
        status_color = "dim" if g["undo_status"] == "undone" else "cyan"

        try:
            ts = datetime.fromisoformat(g["timestamp"])
            time_str = ts.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            time_str = g["timestamp"]

        console.print(
            f"  [{status_color}]{status_icon}[/{status_color}] "
            f"[bold]{g['command']}[/bold] — {time_str}"
        )
        console.print(
            f"     ID: {g['group_id']} | "
            f"Operations: {g['operation_count']} | "
            f"Status: {g['status']}"
        )
        if g["undo_status"]:
            console.print(f"     Undo: {g['undo_status']}")

        if verbose:
            txn = TransactionLog.load(g["group_id"])
            for op in txn.operations:
                op_type = op["op_type"]
                orig = op["original_path"] or "(none)"
                new = op["new_path"] or "(none)"
                console.print(f"       {op_type}: {orig} -> {new}")

        console.print()

    console.print("[dim]Undo the last operation with: max files undo[/dim]")
