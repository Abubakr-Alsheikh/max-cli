"""`max pdf`: parse options, call core/operations/pdf.py, print the result.

The catalog entries in core/catalog/groups/pdf.py describe the same
commands; tests/test_catalog_drift.py fails when the two disagree.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

import typer
from rich.markup import escape

from max_cli.common.exceptions import ResourceNotFoundError, ValidationError
from max_cli.common.logger import console, log_error, log_success
from max_cli.common.utils import format_size
from max_cli.core.operations import pdf as pdf_ops
from max_cli.core.presets import PDF_COMPRESS_DPI, PDF_COMPRESS_QUALITY

if TYPE_CHECKING:
    from max_cli.core.operations.result import ActionResult

app = typer.Typer()

OCR_TIP = (
    # "\[" keeps Rich from reading [ocr] as a style tag.
    "[yellow]Tip: Install OCR dependencies with: pip install max-cli\\[ocr][/yellow]"
)


def _get_engine():
    from max_cli.core.engines.pdf_engine import PDFEngine

    return PDFEngine()


def _run(
    operation: Callable[..., "ActionResult"],
    fail_message: str,
    exit_on_error: bool = False,
    **kwargs: Any,
) -> Optional["ActionResult"]:
    """Call a pdf operation and report its errors.

    Bad input (a missing file, an invalid range) exits 1 before any work.
    Other failures print `fail_message`; commands whose scripts rely on it
    exit 1 (exit_on_error), the rest return None and `max` exits 1 anyway.
    """
    try:
        return operation(engine=_get_engine(), **kwargs)
    except (ResourceNotFoundError, ValidationError) as e:
        log_error(escape(str(e)))
        raise typer.Exit(1) from None
    except Exception as e:
        log_error(escape(f"{fail_message}: {e}"))
        if exit_on_error:
            raise typer.Exit(1) from None
        return None


def _success(result: Optional["ActionResult"]) -> Optional["ActionResult"]:
    if result:
        log_success(escape(result.message))
    return result


@app.command("merge")
@app.command("m", hidden=True)
def merge_pdfs(
    inputs: Optional[list[Path]] = typer.Argument(
        None, help="List of files OR a single folder."
    ),
    output: Optional[Path] = typer.Option(
        None, "-o", "--output", help="Output filename."
    ),
):
    """
    Combine multiple PDFs into one.
    """
    _success(_run(pdf_ops.merge, "Merge failed", inputs=inputs, output=output))


@app.command("compress")
@app.command("c", hidden=True)
def compress_pdf(
    target: Path = typer.Argument(..., help="PDF file OR Folder to compress."),
    dpi: int = typer.Option(
        PDF_COMPRESS_DPI, "-d", "--dpi", help="DPI resolution (Lower = smaller file)."
    ),
    quality: int = typer.Option(
        PDF_COMPRESS_QUALITY,
        "-q",
        "--quality",
        help="JPEG Quality 1-100 (Lower = smaller file).",
    ),
):
    """
    Shrink PDFs. Accepts a single file OR a folder (batch mode).
    """
    from max_cli.common.events import get_emitter
    from max_cli.interface.event_subscriber import EventSubscriber

    emitter = get_emitter()
    subscriber = EventSubscriber(emitter)
    subscriber.subscribe()
    try:
        with subscriber.create_progress_context(0, "Compressing PDFs..."):
            result = _run(
                pdf_ops.compress,
                "Compression failed",
                target=target,
                dpi=dpi,
                quality=quality,
                emitter=emitter,
            )
    finally:
        subscriber.unsubscribe()
    if not result:
        return

    for failure in result.details["failed"]:
        console.print(
            f"[red]Failed to compress {escape(failure['file'])}: "
            f"{escape(failure['error'])}[/red]"
        )
    if not result.ok:
        log_error(escape(result.message))
        return
    log_success(escape(result.message))
    saved = result.details["saved_bytes"]
    if saved > 0:
        console.print(
            f"[green]Total Space Saved:[/green] [bold]{format_size(saved)}[/bold]"
        )
    else:
        console.print(
            "[yellow]⚠ Warning:[/yellow] File size increased by "
            f"[bold red]{format_size(abs(saved))}[/bold red]."
        )
        console.print(
            "[dim]Note: This PDF is likely text-based. Rasterization (image-based"
            " compression) is best for scanned documents, not digital text"
            " documents.[/dim]"
        )


@app.command("bundle")
@app.command("b", hidden=True)
def bundle_pdfs(
    inputs: Optional[list[Path]] = typer.Argument(
        None, help="Files or Folder to bundle."
    ),
    output: Optional[Path] = typer.Option(
        None, "-o", "--output", help="Final output path."
    ),
    dpi: int = typer.Option(
        PDF_COMPRESS_DPI, "-d", "--dpi", help="Compression DPI (default: 150)."
    ),
    quality: int = typer.Option(
        PDF_COMPRESS_QUALITY,
        "-q",
        "--quality",
        help="Compression Quality 1-100 (default: 80).",
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
    with console.status("Merging..." if no_compress else "Merging and compressing..."):
        result = _run(
            pdf_ops.bundle,
            "Bundle operation failed",
            exit_on_error=True,
            inputs=inputs,
            output=output,
            dpi=dpi,
            quality=quality,
            no_compress=no_compress,
        )
    if not result:
        return
    details = result.details
    if details["grew"]:
        growth = details["output_size"] - details["input_size"]
        console.print(
            "[yellow]⚠ Warning:[/yellow] Bundle size increased by "
            f"[bold red]{format_size(growth)}[/bold red]."
        )
        console.print(
            "[dim]Note: Consider using lower quality or 'compress' command"
            " separately.[/dim]"
        )
    log_success("Bundle created successfully!")
    console.print(f"Path: [bold]{escape(str(result.output_files[0]))}[/bold]")
    console.print(f"Size: {format_size(details['output_size'])}")
    console.print(f"Pages: [bold]{details['page_count']}[/bold]")


@app.command("split")
@app.command("sp", hidden=True)
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
    result = _run(
        pdf_ops.split,
        "Split failed",
        exit_on_error=True,
        target=target,
        start=start,
        end=end,
        output=output,
        chunks=chunks,
        remove=remove,
        list_pages=list_pages,
    )
    if result is None:
        return
    if list_pages:
        console.print(f"[cyan]{escape(result.message)}[/cyan]")
        return
    for path in result.output_files:
        console.print(f"  {escape(path.name)} ({format_size(path.stat().st_size)})")
    log_success(escape(result.message))


@app.command("stamp")
@app.command("st", hidden=True)
def stamp_pdf(
    target: Path = typer.Argument(..., help="PDF to watermark."),
    text: str = typer.Argument("DRAFT", help="Text to overlay."),
    output: Optional[Path] = typer.Option(None, "-o", help="Output filename."),
):
    """
    Add a watermark (e.g., 'CONFIDENTIAL') to the center of every page.
    """
    console.print(
        f"[cyan]Stamping '{escape(text)}' onto {escape(target.name)}...[/cyan]"
    )
    _success(
        _run(pdf_ops.stamp, "Stamp failed", target=target, text=text, output=output)
    )


@app.command("lock")
@app.command("l", hidden=True)
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
    _success(
        _run(
            pdf_ops.lock,
            "Encryption failed",
            target=target,
            password=password,
            output=output,
        )
    )


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
    result = _run(
        pdf_ops.rip, "Extraction failed", target=target, output_dir=output_dir
    )
    if result is None:
        return
    if result.details["count"]:
        log_success(escape(result.message))
    else:
        console.print(f"[yellow]{escape(result.message)}[/yellow]")


@app.command("ocr")
@app.command("o", hidden=True)
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
    console.print(f"[cyan]Running OCR on {escape(target.name)} (lang={lang})...[/cyan]")
    try:
        result = pdf_ops.ocr(target, lang=lang, output=output, engine=_get_engine())
    except ResourceNotFoundError as e:
        log_error(escape(str(e)))
        raise typer.Exit(1) from None
    except RuntimeError as e:
        # The engine raises RuntimeError when pytesseract or Tesseract is missing.
        log_error(escape(str(e)))
        console.print(OCR_TIP)
        return
    except Exception as e:
        log_error(escape(f"OCR failed: {e}"))
        return
    log_success(escape(result.message))
    console.print(f"Extracted [bold]{result.details['characters']}[/bold] characters")


@app.command("form-data")
def extract_form(
    target: Path = typer.Argument(..., help="PDF form to extract data from."),
):
    """
    Extract data from PDF form fields.
    """
    result = _run(pdf_ops.form_data, "Failed to extract form data", target=target)
    if result is None:
        return
    fields = result.details["fields"]
    if not fields:
        console.print(f"[yellow]{escape(result.message)}[/yellow]")
        return
    console.print("[bold]Form Fields:[/bold]")
    for name, value in fields.items():
        console.print(f"  {escape(str(name))}: [green]{escape(str(value))}[/green]")
    log_success(escape(result.message))


@app.command("form-fill")
def fill_form(
    target: Path = typer.Argument(..., help="PDF form to fill."),
    field: list[str] = typer.Option(
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
    _success(
        _run(
            pdf_ops.form_fill,
            "Failed to fill form",
            target=target,
            field=field,
            output=output,
        )
    )


@app.command("form-flatten")
def flatten_form(
    target: Path = typer.Argument(..., help="PDF form to flatten."),
    output: Optional[Path] = typer.Option(None, "-o", help="Output file."),
):
    """
    Flatten PDF form (convert fields to regular content).
    """
    _success(
        _run(
            pdf_ops.form_flatten,
            "Failed to flatten form",
            target=target,
            output=output,
        )
    )


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
    result = _success(
        _run(
            pdf_ops.optimize,
            "Optimization failed",
            target=target,
            output=output,
            no_compress=no_compress,
            no_linearize=no_linearize,
        )
    )
    if result is None:
        return
    original_size = result.details["original_size"]
    new_size = result.details["new_size"]
    reduction = (original_size - new_size) / original_size * 100 if original_size else 0
    console.print(
        f"Size: {format_size(original_size)} -> "
        f"[green]{format_size(new_size)}[/green] (-{reduction:.1f}%)"
    )


@app.command("compare")
def compare_pdfs(
    file1: Path = typer.Argument(..., help="First PDF file."),
    file2: Path = typer.Argument(..., help="Second PDF file."),
):
    """
    Compare two PDFs and show differences.
    """
    result = _run(pdf_ops.compare, "Comparison failed", file1=file1, file2=file2)
    if result is None:
        return
    details = result.details
    if details["identical"]:
        console.print("[green]✓ PDFs are identical![/green]")
        return
    console.print("[yellow]⚠ PDFs have differences:[/yellow]")
    for difference in details["differences"]:
        console.print(f"  - {escape(difference)}")
    if details["pages_equal"]:
        console.print("\n[green]Page count and content match.[/green]")
    else:
        console.print("\n[red]PDFs are different.[/red]")
