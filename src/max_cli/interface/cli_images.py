import typer
from pathlib import Path
from typing import Optional
from rich.progress import track
from max_cli.core.image_processor import ImageEngine
from max_cli.common.logger import console, log_error, log_success
from max_cli.config import settings

app = typer.Typer()
engine = ImageEngine()


@app.command("compress")
def compress_images(
    target: Path = typer.Argument(..., help="File or Folder to process"),
    quality: int = typer.Option(settings.DEFAULT_QUALITY, "-q", help="JPEG Quality"),
    scale: Optional[int] = typer.Option(None, help="Resize percentage (e.g. 50)"),
    force_jpeg: bool = typer.Option(False, "--jpeg", help="Convert to JPEG"),
):
    """
    Compress and optimize images in a folder or single file.
    """
    files_to_process = []

    if target.is_file():
        files_to_process.append(target)
        output_dir = target.parent
    elif target.is_dir():
        output_dir = target.parent / f"{target.name}_compressed"
        output_dir.mkdir(exist_ok=True)
        # Gather standard images
        extensions = {".jpg", ".jpeg", ".png", ".webp"}
        files_to_process = [
            f for f in target.iterdir() if f.suffix.lower() in extensions
        ]
    else:
        log_error("Target not found.")
        raise typer.Exit(code=1)

    console.print(f"[bold]Found {len(files_to_process)} images. Processing...[/bold]")

    # Rich Progress Bar
    for img_path in track(files_to_process, description="Compressing..."):
        output_path = output_dir / img_path.name

        try:
            res = engine.process_image(
                img_path,
                output_path,
                quality=quality,
                scale=scale,
                force_jpeg=force_jpeg,
            )
        except Exception as e:
            console.print(f"[warning]Skipped {img_path.name}: {e}[/warning]")

    log_success(f"Done! Saved to: {output_dir}")
