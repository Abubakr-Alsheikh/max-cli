import typer
import os
from pathlib import Path
from typing import List, Optional
from rich.progress import track, Progress, SpinnerColumn, TextColumn, BarColumn

from max_cli.core.pdf_engine import PDFEngine
from max_cli.common.logger import console, log_error, log_success
from max_cli.common.utils import natural_sort_key, format_size

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
    """
    files_to_merge = _resolve_files(inputs)

    if not output:
        # Smart default naming
        if inputs[0].is_dir():
            output = inputs[0] / f"{inputs[0].name}_merged.pdf"
        else:
            output = inputs[0].parent / f"{inputs[0].stem}_merged.pdf"

    console.print(f"Merging [bold]{len(files_to_merge)}[/bold] files...")

    try:
        pages = engine.merge_pdfs(files_to_merge, output)
        log_success(f"Merged {pages} pages into: [bold]{output}[/bold]")
    except Exception as e:
        log_error(f"Merge failed: {e}")


@app.command("compress")
def compress_pdf(
    target: Path = typer.Argument(..., help="PDF file OR Folder to compress."),
    dpi: int = typer.Option(150, help="DPI resolution (Lower = smaller file)."),
    quality: int = typer.Option(80, help="JPEG Quality (Lower = smaller file)."),
):
    """
    Shrink PDFs. Accepts a single file OR a folder (batch mode).
    """
    if not target.exists():
        log_error(f"Target not found: {target}")
        raise typer.Exit(1)

    targets = []

    # 1. Determine targets
    if target.is_dir():
        console.print(f"[cyan]Batch Mode: Scanning '{target.name}'...[/cyan]")
        targets = sorted(
            list(target.glob("*.pdf")), key=lambda f: natural_sort_key(f.name)
        )
        # Create a subfolder for output to avoid mess
        output_dir = target / "compressed"
        output_dir.mkdir(exist_ok=True)
    else:
        targets = [target]
        output_dir = target.parent

    if not targets:
        log_error("No PDF files found.")
        raise typer.Exit(1)

    # 2. Process
    success_count = 0
    total_saved = 0

    # Using Rich Progress Bar for better UX
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("Compressing...", total=len(targets))

        for pdf in targets:
            progress.update(task, description=f"Compressing {pdf.name}...")

            if target.is_dir():
                # Folder mode: save to ./compressed/filename.pdf
                out_path = output_dir / pdf.name
            else:
                # Single file mode: save to filename_compressed.pdf
                out_path = output_dir / f"{pdf.stem}_compressed.pdf"

            try:
                engine.compress_pdf(pdf, out_path, dpi, quality)

                # Stats calculation
                orig = pdf.stat().st_size
                new = out_path.stat().st_size
                diff = orig - new
                total_saved += diff

                success_count += 1
            except Exception as e:
                console.print(f"[red]Failed to compress {pdf.name}: {e}[/red]")

            progress.advance(task)

    log_success(f"Finished! Processed {success_count}/{len(targets)} files.")
    console.print(
        f"[green]Total Space Saved:[/green] [bold]{format_size(total_saved)}[/bold]"
    )


@app.command("bundle")
def bundle_pdfs(
    inputs: List[Path] = typer.Argument(..., help="Files or Folder to bundle."),
    output: Path = typer.Option(..., "-o", "--output", help="Final output file path."),
    dpi: int = typer.Option(150, help="Compression DPI."),
    quality: int = typer.Option(80, help="Compression Quality."),
):
    """
    Pipeline: Merge multiple files -> Compress result -> Save final.
    Does not leave temporary files behind.
    """
    files = _resolve_files(inputs)

    # Create a temporary path for the merged (uncompressed) file
    temp_merged = output.parent / f".temp_{output.stem}_merged.pdf"

    console.print(f"[cyan]Pipeline: Merge ({len(files)} files) -> Compress[/cyan]")

    try:
        # Step 1: Merge
        with console.status("Step 1/2: Merging..."):
            engine.merge_pdfs(files, temp_merged)

        # Step 2: Compress
        with console.status("Step 2/2: Compressing..."):
            engine.compress_pdf(temp_merged, output, dpi, quality)

        # Step 3: Cleanup
        if temp_merged.exists():
            os.remove(temp_merged)

        # Stats
        final_size = output.stat().st_size
        log_success(f"Bundle created at: [bold]{output}[/bold]")
        console.print(f"Final Size: {format_size(final_size)}")

    except Exception as e:
        # Cleanup on fail
        if temp_merged.exists():
            os.remove(temp_merged)
        log_error(f"Bundle operation failed: {e}")
        raise typer.Exit(1)


def _resolve_files(inputs: List[Path]) -> List[Path]:
    """Helper to turn input arguments into a sorted list of PDF paths."""
    files = []
    if len(inputs) == 1 and inputs[0].is_dir():
        # Folder scan
        raw = [f for f in inputs[0].iterdir() if f.suffix.lower() == ".pdf"]
        files = sorted(raw, key=lambda f: natural_sort_key(f.name))
    else:
        # Explicit list
        files = inputs

    if not files:
        log_error("No PDF files found in input.")
        raise typer.Exit(1)

    return files
