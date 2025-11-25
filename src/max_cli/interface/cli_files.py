import typer
from pathlib import Path
from rich.prompt import Confirm
from rich.panel import Panel
from rich.text import Text

from max_cli.core.file_organizer import FileOrganizer
from max_cli.common.logger import console, log_error, log_success

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
        console.print(f"  ... and {len(actions)-10} more.")
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
