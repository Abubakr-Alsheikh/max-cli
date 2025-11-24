import typer
from pathlib import Path
from max_cli.core.file_organizer import FileOrganizer
from max_cli.common.logger import console, log_error, log_success

app = typer.Typer()
organizer = FileOrganizer()


@app.command("order")
def order_files(
    target_folder: Path = typer.Argument(..., help="Folder containing files to order")
):
    """
    Renames files in a folder to be numerically ordered (e.g., 1_file.txt, 2_image.jpg).
    """
    if not target_folder.is_dir():
        log_error(f"'{target_folder}' is not a directory.")
        raise typer.Exit(code=1)

    console.print(f"[bold]Ordering files in: {target_folder}[/bold]")

    try:
        count = organizer.order_files(target_folder)
        log_success(f"Successfully ordered {count} files in '{target_folder}'.")
    except Exception as e:
        log_error(f"Failed to order files: {e}")
        raise typer.Exit(code=1)
