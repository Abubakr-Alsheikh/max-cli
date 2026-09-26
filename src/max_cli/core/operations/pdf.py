"""`max pdf` operations: input checks, output naming and batches around PDFEngine.

The CLI, the dashboard and the agent call these through the catalog
(`core/catalog/groups/pdf.py`). They never prompt or print. Pass `engine` to
reuse a PDFEngine; `compress` also takes an `emitter` for batch progress.

Default output names, the same for every caller:
- merge: `<folder>/<folder>_merged.pdf` for a folder, `<first>_merged.pdf`
  next to the first file otherwise;
- bundle: `<folder>_bundled.pdf` (or `_merged` with no_compress) next to the
  folder or the first file;
- compress: `<name>_compressed.pdf` next to a file, `<folder>/compressed/`
  for a folder;
- split: `<name>_p<start>-<end>.pdf`, or `<name>_without_p<start>-<end>.pdf`
  with remove;
- stamp, lock, form-fill, form-flatten, optimize: `<name>_<suffix>.pdf`;
- rip: `<name>_assets/`; ocr: `<name>.txt`.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from max_cli.common.exceptions import (
    ProcessingError,
    ResourceNotFoundError,
    ValidationError,
)
from max_cli.core.operations.result import ActionResult
from max_cli.core.presets import PDF_COMPRESS_DPI, PDF_COMPRESS_QUALITY

if TYPE_CHECKING:
    from max_cli.common.events import EventEmitter
    from max_cli.core.engines.pdf_engine import PDFEngine

PDF_SUFFIX = ".pdf"
COMPRESS_FOLDER = "compressed"
LAST_PAGE = -1
FIELD_SEPARATOR = "="
QUALITY_RANGE = range(1, 101)


def _engine(engine: Optional["PDFEngine"]) -> "PDFEngine":
    if engine is not None:
        return engine
    from max_cli.core.engines.pdf_engine import PDFEngine

    return PDFEngine()


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise ResourceNotFoundError(f"File not found: {path}")


def _sibling(target: Path, suffix: str, extension: str = PDF_SUFFIX) -> Path:
    return target.parent / f"{target.stem}{suffix}{extension}"


def _check_quality(quality: int) -> None:
    if quality not in QUALITY_RANGE:
        raise ValidationError("Quality must be between 1 and 100.")


def _folder_name(folder: Path) -> str:
    """A real name for a folder, including "." (whose .name is "")."""
    return folder.name or folder.resolve().name


def resolve_pdfs(inputs: Optional[list[Path]]) -> list[Path]:
    """One folder gives its PDFs in natural order; otherwise the PDFs listed."""
    inputs = inputs or [Path(".")]
    if len(inputs) == 1 and inputs[0].is_dir():
        from max_cli.core.engines.pdf_engine import find_pdfs

        files = find_pdfs(inputs[0])
    else:
        files = [
            path
            for path in inputs
            if path.is_file() and path.suffix.lower() == PDF_SUFFIX
        ]
    if not files:
        raise ValidationError("No PDF files found in input.")
    return files


def _without(files: list[Path], output: Path) -> list[Path]:
    """Leave out an earlier result, so running twice doesn't merge it back in."""
    resolved_output = output.resolve()
    return [path for path in files if path.resolve() != resolved_output]


def merge(
    inputs: Optional[list[Path]] = None,
    output: Optional[Path] = None,
    *,
    engine: Optional["PDFEngine"] = None,
) -> ActionResult:
    inputs = inputs or [Path(".")]
    first = inputs[0]
    if output is None:
        output = (
            first / f"{_folder_name(first)}_merged.pdf"
            if first.is_dir()
            else _sibling(first, "_merged")
        )
    files = _without(resolve_pdfs(inputs), output)
    if not files:
        raise ValidationError("No PDF files found in input.")
    pages = _engine(engine).merge_pdfs(files, output)
    return ActionResult(
        True,
        f"Merged {pages} pages into: {output}",
        [output],
        details={"file_count": len(files), "page_count": pages},
    )


def compress(
    target: Path,
    dpi: int = PDF_COMPRESS_DPI,
    quality: int = PDF_COMPRESS_QUALITY,
    *,
    engine: Optional["PDFEngine"] = None,
    emitter: Optional["EventEmitter"] = None,
) -> ActionResult:
    """Rasterize pages to JPEG: good for scans, often larger for text PDFs."""
    from max_cli.common.concurrent import process_batch_sequential
    from max_cli.common.utils import natural_sort_key

    if not target.exists():
        raise ResourceNotFoundError(f"Target not found: {target}")
    _check_quality(quality)
    batch = target.is_dir()
    if batch:
        pdfs = sorted(
            target.glob(f"*{PDF_SUFFIX}"), key=lambda f: natural_sort_key(f.name)
        )
        output_dir = target / COMPRESS_FOLDER
    else:
        pdfs = [target]
        output_dir = target.parent
    if not pdfs:
        raise ValidationError("No PDF files found.")
    output_dir.mkdir(exist_ok=True)
    pdf_engine = _engine(engine)

    def compress_one(pdf: Path) -> dict[str, Any]:
        output = output_dir / pdf.name if batch else _sibling(pdf, "_compressed")
        pdf_engine.compress_pdf(pdf, output, dpi, quality)
        return {
            "file": pdf.name,
            "output": str(output),
            "original_size": pdf.stat().st_size,
            "new_size": output.stat().st_size,
        }

    results = process_batch_sequential(
        pdfs, compress_one, emitter=emitter, action="Compressing"
    )
    done = [result for result in results if "error" not in result]
    failed = [
        {"file": Path(result["item"]).name, "error": result["error"]}
        for result in results
        if "error" in result
    ]
    saved = sum(result["original_size"] - result["new_size"] for result in done)
    return ActionResult(
        ok=bool(done),
        message=f"Finished! Processed {len(done)}/{len(pdfs)} files.",
        output_files=[Path(result["output"]) for result in done],
        details={"files": done, "failed": failed, "saved_bytes": saved},
    )


def bundle(
    inputs: Optional[list[Path]] = None,
    output: Optional[Path] = None,
    dpi: int = PDF_COMPRESS_DPI,
    quality: int = PDF_COMPRESS_QUALITY,
    no_compress: bool = False,
    *,
    engine: Optional["PDFEngine"] = None,
) -> ActionResult:
    """Merge, then compress the result unless no_compress."""
    inputs = inputs or [Path(".")]
    _check_quality(quality)
    first = inputs[0]
    base_name = _folder_name(first) if first.is_dir() else first.stem
    filename = f"{base_name}_{'merged' if no_compress else 'bundled'}{PDF_SUFFIX}"
    if output is None:
        output = first.parent / filename
    elif output.is_dir():
        output = output / filename
    files = _without(resolve_pdfs(inputs), output)
    stats = _engine(engine).bundle_pdfs(
        files, output, compress=not no_compress, dpi=dpi, quality=quality
    )
    return ActionResult(
        True,
        f"Bundle created: {output}",
        [output],
        details={
            "file_count": len(files),
            "page_count": stats["page_count"],
            "input_size": stats["input_size"],
            "output_size": stats["output_size"],
            "grew": not no_compress and stats["output_size"] > stats["input_size"],
        },
    )


def split(
    target: Path,
    start: int = 1,
    end: int = LAST_PAGE,
    output: Optional[Path] = None,
    chunks: int = 0,
    remove: bool = False,
    list_pages: bool = False,
    *,
    engine: Optional["PDFEngine"] = None,
) -> ActionResult:
    """Keep or remove a page range, split into chunks, or just count pages."""
    _require_file(target)
    pdf_engine = _engine(engine)
    try:
        total_pages = pdf_engine.get_page_count(target)
    except Exception as e:  # fitz raises its own types for damaged files
        raise ProcessingError(f"Failed to read PDF: {e}") from e
    if list_pages:
        return ActionResult(
            True,
            f"'{target.name}' has {total_pages} pages.",
            details={"page_count": total_pages},
        )

    if chunks > 0:
        output_dir = output if output is not None and output.is_dir() else target.parent
        files = pdf_engine.split_into_chunks(target, output_dir, chunks)
        return ActionResult(
            True,
            f"Split into {len(files)} chunks",
            files,
            details={"page_count": total_pages},
        )
    if chunks < 0:
        raise ValidationError("Chunks must be 0 (off) or a positive page count.")

    if end == LAST_PAGE or end > total_pages:
        end = total_pages
    if start < 1 or start > end:
        raise ValidationError(
            f"Invalid range: {start}-{end}. Document has {total_pages} pages."
        )
    if output is None:
        prefix = "_without_p" if remove else "_p"
        output = _sibling(target, f"{prefix}{start}-{end}")
    count = pdf_engine.split_by_range(target, output, start, end, keep=not remove)
    verb = "Removed pages" if remove else "Extracted pages"
    return ActionResult(
        True,
        f"{verb} {start}-{end}: {count} pages saved to: {output}",
        [output],
        details={"page_count": count},
    )


def stamp(
    target: Path,
    text: str = "DRAFT",
    output: Optional[Path] = None,
    *,
    engine: Optional["PDFEngine"] = None,
) -> ActionResult:
    _require_file(target)
    output = output or _sibling(target, "_stamped")
    _engine(engine).watermark_pdf(target, output, text=text)
    return ActionResult(True, f"Stamped PDF saved to: {output}", [output])


def lock(
    target: Path,
    password: str,
    output: Optional[Path] = None,
    *,
    engine: Optional["PDFEngine"] = None,
) -> ActionResult:
    _require_file(target)
    if not password:
        raise ValidationError("Enter a password.")
    output = output or _sibling(target, "_locked")
    _engine(engine).set_password(target, output, password)
    return ActionResult(True, f"Encrypted file saved to: {output}", [output])


def rip(
    target: Path,
    output_dir: Optional[Path] = None,
    *,
    engine: Optional["PDFEngine"] = None,
) -> ActionResult:
    """Extract every embedded image."""
    _require_file(target)
    output_dir = output_dir or target.parent / f"{target.stem}_assets"
    output_dir.mkdir(exist_ok=True)
    count = _engine(engine).extract_assets(target, output_dir)
    if count == 0:
        return ActionResult(True, "No images found in this PDF.", details={"count": 0})
    return ActionResult(
        True,
        f"Extracted {count} images to: {output_dir}",
        [output_dir],
        details={"count": count},
    )


def ocr(
    target: Path,
    lang: str = "eng",
    output: Optional[Path] = None,
    *,
    engine: Optional["PDFEngine"] = None,
) -> ActionResult:
    """Needs pytesseract and Tesseract; the engine raises RuntimeError without them."""
    _require_file(target)
    output = output or _sibling(target, "", ".txt")
    text = _engine(engine).ocr_pdf(target, output, lang=lang)
    return ActionResult(
        True,
        f"Text extracted to: {output}",
        [output],
        details={"characters": len(text)},
    )


def form_data(target: Path, *, engine: Optional["PDFEngine"] = None) -> ActionResult:
    _require_file(target)
    fields = _engine(engine).extract_form_data(target)
    message = (
        f"Found {len(fields)} form fields"
        if fields
        else "No form fields found in this PDF."
    )
    return ActionResult(True, message, details={"fields": fields})


def _parse_fields(field: list[str]) -> dict[str, str]:
    values = {}
    for entry in field:
        name, separator, value = entry.partition(FIELD_SEPARATOR)
        if not separator or not name.strip():
            raise ValidationError(f"Invalid field format: {entry}. Use fieldname=value")
        values[name.strip()] = value
    return values


def form_fill(
    target: Path,
    field: list[str],
    output: Optional[Path] = None,
    *,
    engine: Optional["PDFEngine"] = None,
) -> ActionResult:
    """Fill form fields from `name=value` entries."""
    _require_file(target)
    values = _parse_fields(field)
    output = output or _sibling(target, "_filled")
    _engine(engine).fill_form(target, output, values)
    return ActionResult(
        True,
        f"Filled form saved to: {output}",
        [output],
        details={"field_count": len(values)},
    )


def form_flatten(
    target: Path,
    output: Optional[Path] = None,
    *,
    engine: Optional["PDFEngine"] = None,
) -> ActionResult:
    _require_file(target)
    output = output or _sibling(target, "_flattened")
    _engine(engine).flatten_form(target, output)
    return ActionResult(True, f"Flattened form saved to: {output}", [output])


def optimize(
    target: Path,
    output: Optional[Path] = None,
    no_compress: bool = False,
    no_linearize: bool = False,
    *,
    engine: Optional["PDFEngine"] = None,
) -> ActionResult:
    _require_file(target)
    output = output or _sibling(target, "_optimized")
    original_size = target.stat().st_size
    _engine(engine).optimize_pdf(
        target, output, compress_images=not no_compress, linearize=not no_linearize
    )
    return ActionResult(
        True,
        f"Optimized PDF saved to: {output}",
        [output],
        details={"original_size": original_size, "new_size": output.stat().st_size},
    )


def compare(
    file1: Path, file2: Path, *, engine: Optional["PDFEngine"] = None
) -> ActionResult:
    _require_file(file1)
    _require_file(file2)
    result = _engine(engine).compare_pdfs(file1, file2)
    identical = result["pages_equal"] and not result["differences"]
    return ActionResult(
        True,
        "PDFs are identical!" if identical else "PDFs have differences.",
        details={
            "identical": identical,
            "pages_equal": result["pages_equal"],
            "differences": result["differences"],
        },
    )
