"""`max images`: parse options, call core/operations/images.py, print the result.

The catalog entries in core/catalog/groups/images.py describe the same
commands; tests/test_catalog_drift.py fails when the two disagree.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

import typer
from rich.markup import escape

from max_cli.common.exceptions import ResourceNotFoundError, ValidationError
from max_cli.common.logger import console, log_error, log_success
from max_cli.config import settings
from max_cli.core.operations import images as images_ops
from max_cli.core.presets import STRIP_IMAGE_METADATA

if TYPE_CHECKING:
    from max_cli.core.operations.result import ActionResult

app = typer.Typer()

SUMMARY_ROWS = 15


def _get_engine():
    from max_cli.core.engines.image_processor import ImageEngine

    return ImageEngine()


def _run(operation: Callable[..., "ActionResult"], label: str, **kwargs: Any) -> None:
    """Run an images operation with a progress bar, then print its summary.

    Bad input (a missing path, no size for resize) exits 1 before any work.
    """
    from max_cli.common.events import get_emitter
    from max_cli.interface.event_subscriber import EventSubscriber

    emitter = get_emitter()
    subscriber = EventSubscriber(emitter)
    subscriber.subscribe()
    try:
        with subscriber.create_progress_context(0, f"{label}..."):
            result = operation(engine=_get_engine(), emitter=emitter, **kwargs)
    except (ResourceNotFoundError, ValidationError) as e:
        log_error(str(e))
        raise typer.Exit(1) from None
    finally:
        subscriber.unsubscribe()
    _print_result(result, label)


def _print_result(result: "ActionResult", label: str) -> None:
    from rich import box
    from rich.table import Table
    from rich.text import Text

    for failure in result.details.get("failed", []):
        # Plain Text: file names like "cat [red].png" are not markup.
        console.print(Text(f"Error {failure['file']}: {failure['error']}", "red"))
    processed = result.details.get("processed", [])
    if processed:
        table = Table(title=f"{label} Summary", box=box.ROUNDED)
        table.add_column("File", style="cyan")
        table.add_column("Original", justify="right")
        table.add_column("Final", justify="right", style="green")
        table.add_column("Saved", justify="right", style="bold yellow")
        for row in processed[:SUMMARY_ROWS]:
            table.add_row(
                Text(row["file_name"]),
                row["original_size"],
                row["final_size"],
                f"{row['reduction_pct']}%",
            )
        console.print(table)
    # escape: a folder named "photos [red]" is not markup.
    if result.ok:
        log_success(escape(result.message))
    else:
        log_error(escape(result.message))


@app.command("compress")
@app.command("c", hidden=True)
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
    strip: bool = typer.Option(
        STRIP_IMAGE_METADATA, "--strip/--keep", help="Remove EXIF metadata."
    ),
    workers: int = typer.Option(
        settings.MAX_WORKERS, "-j", help="Number of parallel workers."
    ),
):
    """
    All-in-one optimizer. Compress, resize, and convert formats in one go.
    """
    _run(
        images_ops.compress,
        "Optimizing",
        target=target,
        quality=quality,
        scale=scale,
        max_dim=max_dim,
        force_jpeg=force_jpeg,
        quantize=quantize,
        strip=strip,
        workers=workers,
    )


@app.command("resize")
@app.command("r", hidden=True)
def resize_images(
    target: Path = typer.Argument(Path("."), help="File or folder."),
    width: Optional[int] = typer.Option(None, "-w", help="Width in px."),
    height: Optional[int] = typer.Option(None, "-h", help="Height in px."),
    scale: Optional[int] = typer.Option(None, "-s", help="Scale %."),
    workers: int = typer.Option(
        settings.MAX_WORKERS, "-j", help="Number of parallel workers."
    ),
):
    """Specialized command for adjusting image dimensions."""
    _run(
        images_ops.resize,
        "Resizing",
        target=target,
        width=width,
        height=height,
        scale=scale,
        workers=workers,
    )


@app.command("convert")
@app.command("cv", hidden=True)
def convert_images(
    target: Path = typer.Argument(Path("."), help="File or folder."),
    to: str = typer.Option(..., help="Target format (webp, jpg, png)."),
    workers: int = typer.Option(
        settings.MAX_WORKERS, "-j", help="Number of parallel workers."
    ),
):
    """Bulk convert images to a new format."""
    _run(images_ops.convert, "Converting", target=target, to=to, workers=workers)


@app.command("strip")
@app.command("s", hidden=True)
def strip_metadata(
    target: Path = typer.Argument(Path("."), help="File or folder."),
    workers: int = typer.Option(
        settings.MAX_WORKERS, "-j", help="Number of parallel workers."
    ),
):
    """Remove GPS and EXIF data from images for privacy."""
    _run(images_ops.strip, "Stripping", target=target, workers=workers)
