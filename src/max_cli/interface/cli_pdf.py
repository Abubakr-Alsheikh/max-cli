import typer
import os
from pathlib import Path
from typing import List, Optional
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from max_cli.core.engines.pdf_engine import PDFEngine
from max_cli.common.logger import console, log_error, log_success
from max_cli.common.utils import natural_sort_key, format_size

app = typer.Typer()
engine = PDFEngine()


@app.command("merge")
def merge_pdfs(
    inputs: Optional[List[Path]] = typer.Argument(
        None, help="List of files OR a single folder."
    ),
    output: Optional[Path] = typer.Option(
        None, "-o", "--output", help="Output filename."
    ),
):
    """
    Combine multiple PDFs into one.
    """
    # Handle default to current directory
    if inputs is None:
        inputs = [Path(".")]

    files_to_merge = _resolve_files(inputs)

    if not output:
        # Smart default naming
        if inputs[0].is_dir():
            folder_name = inputs[0].name
            if not folder_name:
                folder_name = inputs[0].absolute().name or inputs[0].parent.name
            output = inputs[0] / f"{folder_name}_merged.pdf"
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
    dpi: int = typer.Option(
        150, "-d", "--dpi", help="DPI resolution (Lower = smaller file)."
    ),
    quality: int = typer.Option(
        80, "-q", "--quality", help="JPEG Quality 1-100 (Lower = smaller file)."
    ),
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
    if total_saved > 0:
        console.print(
            f"[green]Total Space Saved:[/green] [bold]{format_size(total_saved)}[/bold]"
        )
    else:
        # Growth scenario
        console.print(
            f"[yellow]⚠ Warning:[/yellow] File size increased by [bold red]{format_size(abs(total_saved))}[/bold red]."
        )
        console.print(
            "[dim]Note: This PDF is likely text-based. Rasterization (image-based compression) "
            "is best for scanned documents, not digital text documents.[/dim]"
        )


@app.command("bundle")
def bundle_pdfs(
    inputs: Optional[List[Path]] = typer.Argument(
        None, help="Files or Folder to bundle."
    ),
    output: Optional[Path] = typer.Option(
        None, "-o", "--output", help="Final output path."
    ),
    dpi: int = typer.Option(150, "-d", "--dpi", help="Compression DPI (default: 150)."),
    quality: int = typer.Option(
        80, "-q", "--quality", help="Compression Quality 1-100 (default: 80)."
    ),
    no_compress: bool = typer.Option(
        False, "--no-compress", help="Skip compression (merge only, no compress)."
    ),
):
    """
    Pipeline: Merge multiple files -> Optionally Compress -> Save final.

    Examples:
      max pdf bundle                    # Merge + Compress (default)
      max pdf bundle --no-compress      # Merge only, no compression
      max pdf bundle -d 300 -q 90       # Merge + Compress with high quality
      max pdf bundle -d 72 -q 50        # Merge + Heavy compression
    """
    # Handle default to current directory
    if inputs is None:
        inputs = [Path(".")]

    # 1. Resolve Inputs
    try:
        files = _resolve_files(inputs)
    except Exception as e:
        log_error(str(e))
        raise typer.Exit(1)

    # 2. Smart Output Logic
    # Determine a base name for the file
    if inputs[0].is_dir():
        base_name = inputs[0].name
        if not base_name:
            base_name = inputs[0].absolute().name or inputs[0].parent.name
        default_parent = inputs[0].parent
    else:
        base_name = inputs[0].stem
        default_parent = inputs[0].parent

    # Determine filename based on whether compression is used
    if no_compress:
        filename = f"{base_name}_merged.pdf"
    else:
        filename = f"{base_name}_bundled.pdf"

    if output is None:
        output = default_parent / filename
    elif output.is_dir():
        output = output / filename

    # Show pipeline info
    if no_compress:
        console.print(f"[cyan]Pipeline: Merge ({len(files)} files)[/cyan]")
    else:
        console.print(
            f"[cyan]Pipeline: Merge ({len(files)} files) -> Compress (DPI:{dpi}, Q:{quality})[/cyan]"
        )
    console.print(f"[dim]Target: {output}[/dim]")

    # Create a unique temp file to avoid collisions
    temp_merged = output.parent / f".tmp_{base_name}_merged.pdf"

    try:
        # Step 1: Merge
        with console.status("Merging..."):
            engine.merge_pdfs(files, temp_merged)

        final_size = 0

        if no_compress:
            # Just move the merged file to output
            temp_merged.rename(output)
            final_size = output.stat().st_size
        else:
            # Step 2: Compress
            with console.status("Compressing..."):
                engine.compress_pdf(temp_merged, output, dpi, quality)

            # Cleanup temp
            if temp_merged.exists():
                os.remove(temp_merged)

            # Stats
            final_size = output.stat().st_size
            original_total_size = sum(f.stat().st_size for f in files)

            if final_size > original_total_size:
                growth = final_size - original_total_size
                console.print(
                    f"[yellow]⚠ Warning:[/yellow] Bundle size increased by [bold red]{format_size(growth)}[/bold red]."
                )
                console.print(
                    "[dim]Note: Consider using lower quality or 'compress' command separately.[/dim]"
                )

        log_success("Bundle created successfully!")
        console.print(f"Path: [bold]{output}[/bold]")
        console.print(f"Size: {format_size(final_size)}")
        console.print(f"Pages: [bold]{engine.get_page_count(output)}[/bold]")

    except Exception as e:
        if temp_merged.exists():
            os.remove(temp_merged)
        log_error(f"Bundle operation failed: {e}")
        raise typer.Exit(1)


def _resolve_files(inputs: List[Path]) -> List[Path]:
    """Helper to turn input arguments into a sorted list of PDF paths."""
    files = []

    # If the user passed a single directory
    if len(inputs) == 1 and inputs[0].is_dir():
        folder = inputs[0]
        # Recursively or flatly find PDFs? Standard is flat to avoid deep loops.
        # We filter out files starting with '.' or '_' to avoid hidden/temp files.
        raw = [
            f
            for f in folder.iterdir()
            if f.suffix.lower() == ".pdf" and not f.name.startswith((".", "_"))
        ]
        files = sorted(raw, key=lambda f: natural_sort_key(f.name))

    else:
        # Explicit list of files
        files = [f for f in inputs if f.exists() and f.suffix.lower() == ".pdf"]

    if not files:
        raise ValueError("No PDF files found in input.")

    return files


@app.command("split")
def split_pdf(
    target: Path = typer.Argument(..., help="PDF file to split."),
    start: int = typer.Option(
        1, "-s", "--start", help="Start page (1-based, default: 1)."
    ),
    end: int = typer.Option(
        -1, "-e", "--end", help="End page (-1 for last page, default: last)."
    ),
    output: Optional[Path] = typer.Option(None, "-o", help="Output filename."),
    chunks: int = typer.Option(
        0,
        "-c",
        "--chunks",
        help="Split into chunks of N pages (0=disabled, creates multiple files).",
    ),
    remove: bool = typer.Option(
        False, "--remove", help="Remove the specified range instead of keeping it."
    ),
    list_pages: bool = typer.Option(
        False, "--list", help="Just show page count and exit."
    ),
):
    """
    Split a PDF by page range or into chunks.

    Examples:
      max pdf split file.pdf -s 1 -e 10       Keep pages 1-10
      max pdf split file.pdf -s 11             Keep from page 11 to end
      max pdf split file.pdf -e 5              Keep pages 1-5
      max pdf split file.pdf -c 10             Split into chunks of 10 pages each
      max pdf split file.pdf --remove -s 5 -e 10  Remove pages 5-10
    """
    if not target.exists() or not target.is_file():
        log_error(f"File not found: {target}")
        raise typer.Exit(1)

    try:
        total_pages = engine.get_page_count(target)
    except Exception as e:
        log_error(f"Failed to read PDF: {e}")
        raise typer.Exit(1)

    if list_pages:
        console.print(f"[cyan]'{target.name}' has [bold]{total_pages}[/bold] pages.")
        return

    # Handle chunk mode
    if chunks > 0:
        output_dir = target.parent
        if output and output.is_dir():
            output_dir = output

        output_dir.mkdir(exist_ok=True)

        console.print(f"[cyan]Splitting into chunks of {chunks} pages...")
        files = engine.split_into_chunks(target, output_dir, chunks)

        console.print(f"[green]Created [bold]{len(files)}[/bold] files:")
        for f in files:
            size = f.stat().st_size
            console.print(f"  {f.name} ({format_size(size)})")

        log_success(f"Split into {len(files)} chunks")
        return

    # Resolve end to last page
    if end == -1 or end > total_pages:
        end = total_pages

    # Validate range
    if start < 1 or start > end:
        log_error(f"Invalid range: {start}-{end}. Document has {total_pages} pages.")
        raise typer.Exit(1)

    # Determine output path
    if not output:
        if remove:
            output = target.parent / f"{target.stem}_without_p{start}-{end}.pdf"
        else:
            output = target.parent / f"{target.stem}_p{start}-{end}.pdf"

    # Show what we're doing
    if remove:
        console.print(f"[cyan]Removing pages {start}-{end} from '{target.name}'...")
        action_text = "Removed"
    else:
        console.print(f"[cyan]Extracting pages {start}-{end} from '{target.name}'...")
        action_text = "Extracted"

    try:
        count = engine.split_by_range(target, output, start, end, keep=not remove)

        size = output.stat().st_size
        console.print(f"{action_text} [bold]{count}[/bold] pages -> {output.name}")
        console.print(f"Size: {format_size(size)}")
        log_success(f"Saved to: {output}")

    except ValueError as e:
        log_error(str(e))
    except Exception as e:
        log_error(f"Split failed: {e}")


@app.command("stamp")
def stamp_pdf(
    target: Path = typer.Argument(..., help="PDF to watermark."),
    text: str = typer.Argument("DRAFT", help="Text to overlay."),
    output: Optional[Path] = typer.Option(None, "-o", help="Output filename."),
):
    """
    Add a watermark (e.g., 'CONFIDENTIAL') to the center of every page.
    """
    if not output:
        output = target.parent / f"{target.stem}_stamped.pdf"

    console.print(f"[cyan]Stamping '{text}' onto {target.name}...[/cyan]")
    engine.watermark_pdf(target, output, text=text)
    log_success(f"Stamped PDF saved to: {output}")


@app.command("lock")
def lock_pdf(
    target: Path = typer.Argument(..., help="PDF to encrypt."),
    password: str = typer.Option(
        ..., "--password", "-p", prompt=True, hide_input=True, help="Password."
    ),
    output: Optional[Path] = typer.Option(None, "-o", help="Output filename."),
):
    """
    Encrypt a PDF with a password.
    """
    if not output:
        output = target.parent / f"{target.stem}_locked.pdf"

    engine.set_password(target, output, password)
    log_success(f"Encrypted file saved to: {output}")


@app.command("rip")
def rip_content(
    target: Path = typer.Argument(..., help="PDF to extract from."),
    output_dir: Optional[Path] = typer.Option(
        None, "-o", help="Folder to save images."
    ),
):
    """
    Extract all images from inside the PDF.
    """
    if not output_dir:
        output_dir = target.parent / f"{target.stem}_assets"

    output_dir.mkdir(exist_ok=True)

    console.print(f"Extracting images from [bold]{target.name}[/bold]...")
    count = engine.extract_assets(target, output_dir)

    if count > 0:
        log_success(f"Extracted [bold]{count}[/bold] images to: {output_dir}")
    else:
        console.print("[yellow]No images found in this PDF.[/yellow]")


@app.command("ocr")
def ocr_pdf(
    target: Path = typer.Argument(..., help="PDF file to OCR."),
    lang: str = typer.Option(
        "eng", "--lang", "-l", help="Language code (eng, deu, fra, eng+deu)."
    ),
    output: Optional[Path] = typer.Option(
        None, "-o", help="Output text file (default: same name with .txt)."
    ),
):
    """
    Extract text from scanned PDFs using OCR.

    Requires pytesseract and Tesseract OCR installed.
    Install: pip install max-cli[ocr]
    """
    if not output:
        output = target.parent / f"{target.stem}.txt"

    console.print(f"[cyan]Running OCR on {target.name} (lang={lang})...[/cyan]")

    try:
        text = engine.ocr_pdf(target, output, lang=lang)
        char_count = len(text)

        log_success(f"Text extracted to: {output}")
        console.print(f"Extracted [bold]{char_count}[/bold] characters")

    except RuntimeError as e:
        log_error(str(e))
        console.print(
            "[yellow]Tip: Install OCR dependencies with: pip install max-cli[ocr][/yellow]"
        )
    except Exception as e:
        log_error(f"OCR failed: {e}")


@app.command("form-data")
def extract_form(
    target: Path = typer.Argument(..., help="PDF form to extract data from."),
):
    """
    Extract data from PDF form fields.
    """
    if not target.exists():
        log_error(f"File not found: {target}")
        raise typer.Exit(1)

    console.print(f"[cyan]Extracting form data from {target.name}...[/cyan]")

    try:
        form_data = engine.extract_form_data(target)
        if form_data:
            console.print("[bold]Form Fields:[/bold]")
            for name, value in form_data.items():
                console.print(f"  {name}: [green]{value}[/green]")
            log_success(f"Found {len(form_data)} form fields")
        else:
            console.print("[yellow]No form fields found in this PDF.[/yellow]")
    except Exception as e:
        log_error(f"Failed to extract form data: {e}")


@app.command("form-fill")
def fill_form(
    target: Path = typer.Argument(..., help="PDF form to fill."),
    field: str = typer.Option(
        ...,
        "-f",
        "--field",
        help="Field name=value (can be specified multiple times).",
    ),
    output: Optional[Path] = typer.Option(None, "-o", help="Output file."),
):
    """
    Fill PDF form fields with values.

    Example: max pdf form-fill form.pdf -f name="John" -f email="john@example.com"
    """
    if not target.exists():
        log_error(f"File not found: {target}")
        raise typer.Exit(1)

    if not output:
        output = target.parent / f"{target.stem}_filled.pdf"

    field_values = {}
    for f in field:
        if "=" in f:
            key, value = f.split("=", 1)
            field_values[key] = value
        else:
            log_error(f"Invalid field format: {f}. Use fieldname=value")
            raise typer.Exit(1)

    console.print(f"[cyan]Filling {len(field_values)} fields...[/cyan]")

    try:
        engine.fill_form(target, output, field_values)
        log_success(f"Filled form saved to: {output}")
    except Exception as e:
        log_error(f"Failed to fill form: {e}")


@app.command("form-flatten")
def flatten_form(
    target: Path = typer.Argument(..., help="PDF form to flatten."),
    output: Optional[Path] = typer.Option(None, "-o", help="Output file."),
):
    """
    Flatten PDF form (convert fields to regular content).
    """
    if not target.exists():
        log_error(f"File not found: {target}")
        raise typer.Exit(1)

    if not output:
        output = target.parent / f"{target.stem}_flattened.pdf"

    console.print("[cyan]Flattening form...[/cyan]")

    try:
        engine.flatten_form(target, output)
        log_success(f"Flattened form saved to: {output}")
    except Exception as e:
        log_error(f"Failed to flatten form: {e}")


@app.command("optimize")
def optimize_pdf(
    target: Path = typer.Argument(..., help="PDF file to optimize."),
    output: Optional[Path] = typer.Option(None, "-o", help="Output file."),
    no_compress: bool = typer.Option(
        False, "--no-compress", help="Skip image compression."
    ),
    no_linearize: bool = typer.Option(
        False, "--no-linearize", help="Skip web optimization."
    ),
):
    """
    Optimize PDF (remove unused objects, compress images, linearize).
    """
    if not target.exists():
        log_error(f"File not found: {target}")
        raise typer.Exit(1)

    if not output:
        output = target.parent / f"{target.stem}_optimized.pdf"

    orig_size = target.stat().st_size

    console.print("[cyan]Optimizing PDF...[/cyan]")

    try:
        engine.optimize_pdf(
            target,
            output,
            compress_images=not no_compress,
            linearize=not no_linearize,
        )

        new_size = output.stat().st_size
        reduction = ((orig_size - new_size) / orig_size) * 100

        log_success(f"Optimized PDF saved to: {output}")
        console.print(
            f"Size: {format_size(orig_size)} -> [green]{format_size(new_size)}[/green] (-{reduction:.1f}%)"
        )
    except Exception as e:
        log_error(f"Optimization failed: {e}")


@app.command("compare")
def compare_pdfs(
    file1: Path = typer.Argument(..., help="First PDF file."),
    file2: Path = typer.Argument(..., help="Second PDF file."),
):
    """
    Compare two PDFs and show differences.
    """
    if not file1.exists():
        log_error(f"File not found: {file1}")
        raise typer.Exit(1)
    if not file2.exists():
        log_error(f"File not found: {file2}")
        raise typer.Exit(1)

    console.print(f"[cyan]Comparing {file1.name} vs {file2.name}...[/cyan]")

    try:
        result = engine.compare_pdfs(file1, file2)

        if result["pages_equal"] and not result["differences"]:
            console.print("[green]✓ PDFs are identical![/green]")
        else:
            console.print("[yellow]⚠ PDFs have differences:[/yellow]")
            for diff in result["differences"]:
                console.print(f"  - {diff}")

            if result["pages_equal"]:
                console.print("\n[green]Page count and content match.[/green]")
            else:
                console.print("\n[red]PDFs are different.[/red]")

    except Exception as e:
        log_error(f"Comparison failed: {e}")
