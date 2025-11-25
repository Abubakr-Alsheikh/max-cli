import typer
from pathlib import Path
from typing import List, Optional
from rich.progress import track

from max_cli.core.pdf_engine import PDFEngine
from max_cli.common.logger import console, log_error, log_success
from max_cli.common.utils import natural_sort_key  # We need to create this helper

app = typer.Typer()
engine = PDFEngine()


@app.command("merge")
def merge_pdfs(
    inputs: List[Path] = typer.Argument(..., help="List of files OR a single folder."),
    output: Optional[Path] = typer.Option(
        None, "-o", "--output", help="Output filename."
    ),
):
    """
    Combine multiple PDFs into one.
    If a folder is provided, it merges all PDFs inside it in 'natural' order (1, 2, 10...).
    """
    files_to_merge = []

    # 1. Input Parsing
    if len(inputs) == 1 and inputs[0].is_dir():
        # Folder Mode
        folder = inputs[0]
        console.print(f"[cyan]Scanning folder: {folder}[/cyan]")
        raw_files = [f for f in folder.iterdir() if f.suffix.lower() == ".pdf"]
        # Sort naturally so "10_doc" comes after "2_doc"
        files_to_merge = sorted(raw_files, key=lambda f: natural_sort_key(f.name))

        # Default output name if none provided
        if not output:
            output = folder.parent / f"{folder.name}_combined.pdf"

    else:
        # File List Mode
        files_to_merge = inputs
        if not output:
            # Default to name of first file + _merged
            output = inputs[0].parent / f"{inputs[0].stem}_merged.pdf"

    if not files_to_merge:
        log_error("No PDF files found to merge.")
        raise typer.Exit(code=1)

    # 2. Execution
    console.print(f"Merging [bold]{len(files_to_merge)}[/bold] files...")
    for f in files_to_merge:
        console.print(f"  + {f.name}")

    try:
        engine.merge_pdfs(files_to_merge, output)
        log_success(f"Merged PDF saved to: [bold]{output}[/bold]")
    except Exception as e:
        log_error(f"Merge failed: {e}")


@app.command("compress")
def compress_pdf(
    target: Path = typer.Argument(..., help="PDF file to compress."),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="Output path."),
    dpi: int = typer.Option(150, help="DPI resolution (Lower = smaller file)."),
    quality: int = typer.Option(80, help="JPEG Quality (Lower = smaller file)."),
):
    """
    Shrink a PDF by converting pages to images and back.
    Great for scanned documents.
    """
    if not target.exists():
        log_error("Target file not found.")
        raise typer.Exit(code=1)

    if not output:
        output = target.parent / f"{target.stem}_compressed.pdf"

    console.print(
        f"[cyan]Compressing '{target.name}' (DPI={dpi}, Q={quality})...[/cyan]"
    )

    # We use a simple spinner here because page processing can be fast or slow
    with console.status("[bold green]Processing pages...[/bold green]"):
        try:
            pages = engine.compress_pdf(target, output, dpi, quality)

            # Calculate savings
            orig_size = target.stat().st_size
            new_size = output.stat().st_size
            reduction = ((orig_size - new_size) / orig_size) * 100

            log_success(f"Processed {pages} pages.")
            console.print(
                f"Size: {orig_size/1024/1024:.2f}MB -> [bold green]{new_size/1024/1024:.2f}MB[/bold green] (-{reduction:.1f}%)"
            )

        except Exception as e:
            log_error(f"Compression failed: {e}")
