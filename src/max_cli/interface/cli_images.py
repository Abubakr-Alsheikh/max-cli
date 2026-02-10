import typer
from pathlib import Path
from typing import Optional, List, Tuple
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.table import Table
from rich import box

from max_cli.core.image_processor import ImageEngine
from max_cli.common.logger import console, log_success, log_error
from max_cli.config import settings

app = typer.Typer()
engine = ImageEngine()


def _resolve_batch(target: Path) -> Tuple[List[Path], Path]:
    if target.is_file():
        return [target], target.parent
    files = [
        f
        for f in target.iterdir()
        if f.is_file() and f.suffix.lower() in engine.SUPPORTED_EXTENSIONS
    ]
    out_dir = target.parent / f"{target.name}_optimized"
    out_dir.mkdir(exist_ok=True)
    return files, out_dir


@app.command("compress")
def compress_images(
    target: Path = typer.Argument(Path("."), help="File or folder."),
    quality: int = typer.Option(
        settings.DEFAULT_QUALITY, "-q", help="Quality (1-100)."
    ),
    scale: Optional[int] = typer.Option(None, "-s", help="Scale percentage."),
    max_dim: Optional[int] = typer.Option(None, "-m", help="Max dimension (px)."),
    force_jpeg: bool = typer.Option(False, "--jpeg", help="Force output to JPEG."),
    quantize: bool = typer.Option(
        False, "--quantize", help="Lossy PNG compression (256 colors)."
    ),
    strip: bool = typer.Option(True, "--strip/--keep", help="Remove EXIF metadata."),
):
    """
    All-in-one optimizer. Compress, resize, and convert formats in one go.
    """
    files, out_dir = _resolve_batch(target)

    _run_batch(
        files,
        out_dir,
        "Optimizing",
        quality=quality,
        scale=scale,
        max_dim=max_dim,
        force_format="jpg" if force_jpeg else None,
        quantize_png=quantize,
        strip_exif=strip,
    )


@app.command("resize")
def resize_images(
    target: Path = typer.Argument(Path("."), help="File or folder."),
    width: Optional[int] = typer.Option(None, "-w", help="Width in px."),
    height: Optional[int] = typer.Option(None, "-h", help="Height in px."),
    scale: Optional[int] = typer.Option(None, "-s", help="Scale %."),
):
    """Specialized command for adjusting image dimensions."""
    if not any([width, height, scale]):
        log_error("Specify --width, --height, or --scale.")
        return
    files, out_dir = _resolve_batch(target)
    _run_batch(files, out_dir, "Resizing", width=width, height=height, scale=scale)


@app.command("convert")
def convert_images(
    target: Path = typer.Argument(Path("."), help="File or folder."),
    to: str = typer.Option(..., help="Target format (webp, jpg, png)."),
):
    """Bulk convert images to a new format."""
    files, out_dir = _resolve_batch(target)
    _run_batch(files, out_dir, "Converting", force_format=to)


@app.command("strip")
def strip_metadata(target: Path = typer.Argument(Path("."), help="File or folder.")):
    """Remove GPS and EXIF data from images for privacy."""
    files, out_dir = _resolve_batch(target)
    _run_batch(files, out_dir, "Stripping", strip_exif=True)


def _run_batch(files: List[Path], out_dir: Path, action: str, **kwargs):
    stats_list = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task(f"[green]{action}...", total=len(files))
        for f in files:
            # Single file handling: save with suffix
            if len(files) == 1:
                out_path = out_dir / f"{f.stem}_opt{f.suffix}"
            else:
                out_path = out_dir / f.name

            try:
                stats = engine.process_single_image(f, out_path, **kwargs)
                stats_list.append(stats)
            except Exception as e:
                console.print(f"[red]Error {f.name}: {e}[/red]")
            progress.advance(task)

    if not stats_list:
        return

    table = Table(title=f"{action} Summary", box=box.ROUNDED)
    table.add_column("File", style="cyan")
    table.add_column("Original", justify="right")
    table.add_column("Final", justify="right", style="green")
    table.add_column("Saved", justify="right", style="bold yellow")

    for s in stats_list[:15]:
        table.add_row(
            s["file_name"],
            s["original_size"],
            s["final_size"],
            f"{s['reduction_pct']}%",
        )

    console.print(table)
    log_success(f"Output saved to: {out_dir}")
