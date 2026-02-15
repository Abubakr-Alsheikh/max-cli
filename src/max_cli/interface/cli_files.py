import typer
from pathlib import Path
from rich.prompt import Confirm
from rich.panel import Panel
from rich.text import Text

from max_cli.core.file_organizer import FileOrganizer
from max_cli.common.logger import console, log_error, log_success
from max_cli.interface.cli_ai import engine  # Import the AIEngine instance

app = typer.Typer()
organizer = FileOrganizer()


@app.command("order")
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
        files = organizer.scan_directory(folder)
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

    results = organizer.order_files(folder, dry_run=dry_run, start_index=start)

    # 4. Report
    # Print the log of actions (limited to last 10 if too many, to avoid spam)
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


@app.command("smart-sort")
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

    # engine is the AIEngine instance
    categories = engine.categorize_files(files)

    for filename, category in categories.items():
        src = path / filename
        dest_dir = path / category

        console.print(
            f"  [dim]{filename}[/dim][/dim] -> [bold cyan]{category}/[/bold cyan]"
        )

        if not dry_run:
            dest_dir.mkdir(exist_ok=True)
            src.rename(dest_dir / filename)

    if not dry_run:
        log_success(f"Successfully organized {len(files)} files.")
    else:
        console.print("[yellow]Dry run complete. No files moved.[/yellow]")


@app.command("duplicates")
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
        duplicates = organizer.find_duplicates(folder, recursive=recursive)

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
            removed = 0
            for hash_val, paths in duplicates.items():
                keep = paths[0]
                for p in paths[1:]:
                    p.unlink()
                    removed += 1
                    console.print(f"[red]Deleted:[/red] {p}")

            log_success(f"Removed {removed} duplicate(s). Kept: {keep}")
        else:
            console.print("[dim]Run with --delete to remove duplicates[/dim]")

    except Exception as e:
        log_error(f"Error finding duplicates: {e}")
