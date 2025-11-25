import typer
from pathlib import Path
from typing import Optional, List
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.table import Table
from rich import box

# Import our custom modules
from max_cli.core.image_processor import ImageEngine
from max_cli.common.logger import console, log_error, log_success
from max_cli.config import settings

app = typer.Typer()
engine = ImageEngine()


@app.command("compress")
def compress_command(
    target: Path = typer.Argument(..., help="Path to a file or a folder of images."),
    quality: int = typer.Option(
        settings.DEFAULT_QUALITY, "-q", "--quality", help="JPEG quality (1-100)."
    ),
    scale: Optional[int] = typer.Option(None, help="Resize by percentage (e.g., 50)."),
    max_dim: Optional[int] = typer.Option(
        None, help="Resize longest side to N pixels."
    ),
    force_jpeg: bool = typer.Option(False, "--jpeg", help="Force output to JPEG."),
    quantize: bool = typer.Option(
        False, "--quantize", help="Use lossy PNG compression."
    ),
):
    """
    Compress images. Smartly handles a single file OR an entire folder.
    """

    # 1. Validation
    if scale and max_dim:
        log_error("Cannot use both --scale and --max-dim. Pick one.")
        raise typer.Exit(code=1)

    if not target.exists():
        log_error(f"Target '{target}' not found.")
        raise typer.Exit(code=1)

    # 2. Preparation (Single File vs Folder)
    files_to_process: List[Path] = []
    output_dir: Path

    if target.is_file():
        # Single file mode
        if target.suffix.lower() not in engine.SUPPORTED_EXTENSIONS:
            log_error(f"File type {target.suffix} not supported.")
            raise typer.Exit(code=1)

        files_to_process = [target]
        # For single file, save in same folder with suffix
        output_dir = target.parent

    else:
        # Folder mode
        output_dir = target.parent / f"{target.name}_compressed"
        output_dir.mkdir(exist_ok=True)

        # Scan folder
        files_to_process = [
            f
            for f in target.iterdir()
            if f.is_file() and f.suffix.lower() in engine.SUPPORTED_EXTENSIONS
        ]

        if not files_to_process:
            log_error("No valid images found in folder.")
            raise typer.Exit(code=1)

    console.print(
        f"[bold cyan]Found {len(files_to_process)} images to process...[/bold cyan]"
    )

    # 3. Processing Loop with Rich Progress Bar
    stats_list = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
    ) as progress:

        task = progress.add_task("[green]Compressing...", total=len(files_to_process))

        for input_path in files_to_process:
            # Determine output filename
            if target.is_file():
                # Single file logic: input.jpg -> input_compressed.jpg
                stem = input_path.stem
                ext = ".jpg" if force_jpeg else input_path.suffix
                out_name = f"{stem}_compressed{ext}"
                output_path = output_dir / out_name
            else:
                # Folder logic: keep same name unless forcing jpeg
                out_name = (
                    input_path.with_suffix(".jpg").name
                    if force_jpeg
                    else input_path.name
                )
                output_path = output_dir / out_name

            try:
                # CALL THE CORE LOGIC
                stats = engine.process_single_image(
                    input_path=input_path,
                    output_path=output_path,
                    quality=quality,
                    scale=scale,
                    max_dim=max_dim,
                    force_jpeg=force_jpeg,
                    quantize_png=quantize,
                )
                stats_list.append(stats)
            except Exception as e:
                console.print(f"[red]Failed {input_path.name}: {e}[/red]")

            progress.advance(task)

    # 4. Summary Table
    table = Table(title="Compression Results", box=box.ROUNDED)
    table.add_column("File", style="cyan")
    table.add_column("Original", style="magenta")
    table.add_column("Compressed", style="green")
    table.add_column("Saved", style="bold white")

    # Show first 5 and last 5 if list is huge, otherwise show all
    display_limit = 10
    total_processed = len(stats_list)

    for stat in stats_list[:display_limit]:
        table.add_row(
            stat["file_name"],
            stat["original_size"],
            stat["final_size"],
            f"{stat['reduction_pct']}%",
        )

    if total_processed > display_limit:
        table.add_row("...", "...", "...", "...")
        # Add summary row
        table.add_row(f"{total_processed - display_limit} more files...", "", "", "")

    console.print(table)
    log_success(f"Operation complete. Output at: [bold]{output_dir}[/bold]")
