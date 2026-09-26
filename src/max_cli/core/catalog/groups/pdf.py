"""Catalog entries for `max pdf`. `tests/test_catalog_drift.py` checks them against the CLI."""

from max_cli.core.catalog.spec import (
    Action,
    Danger,
    Group,
    Param,
    ParamKind,
    Surface,
)
from max_cli.core.presets import PDF_COMPRESS_DPI, PDF_COMPRESS_QUALITY

OPS = "max_cli.core.operations.pdf"
# The agent never gets `lock`: it would have to see your password.
NOT_FOR_AGENT = frozenset({Surface.CLI, Surface.DASHBOARD})


def _pdf(help: str = "PDF file.") -> Param:
    return Param("target", ParamKind.FILE, help)


def _output(help: str = "Output file. Default: next to the input.") -> Param:
    return Param("output", ParamKind.OUTPUT, help, default=None, cli=("-o",))


def _inputs(help: str) -> Param:
    return Param("inputs", ParamKind.FILE, help, default=None, multiple=True)


def _dpi() -> Param:
    return Param(
        "dpi",
        ParamKind.INT,
        "Page resolution. Lower gives a smaller file.",
        default=PDF_COMPRESS_DPI,
        cli=("-d", "--dpi"),
    )


def _quality() -> Param:
    return Param(
        "quality",
        ParamKind.INT,
        "JPEG quality, 1 to 100. Lower gives a smaller file.",
        default=PDF_COMPRESS_QUALITY,
        cli=("-q", "--quality"),
    )


GROUP = Group(
    name="pdf",
    summary="Merge, split, compress, protect and fill PDFs.",
    actions=(
        Action(
            group="pdf",
            name="merge",
            summary="Combine PDFs into one file.",
            operation=f"{OPS}:merge",
            params=(
                _inputs("PDF files, or one folder of PDFs. Default: this folder."),
                Param(
                    "output",
                    ParamKind.OUTPUT,
                    "Output file. Default: <folder>_merged.pdf.",
                    default=None,
                    cli=("-o", "--output"),
                ),
            ),
        ),
        Action(
            group="pdf",
            name="compress",
            summary="Shrink a PDF, or every PDF in a folder, by rasterizing pages."
            " Best for scans.",
            operation=f"{OPS}:compress",
            params=(_pdf("A PDF, or a folder of PDFs."), _dpi(), _quality()),
        ),
        Action(
            group="pdf",
            name="bundle",
            summary="Merge PDFs and compress the result in one step.",
            operation=f"{OPS}:bundle",
            params=(
                _inputs("PDF files, or one folder of PDFs. Default: this folder."),
                Param(
                    "output",
                    ParamKind.OUTPUT,
                    "Output file or folder. Default: <folder>_bundled.pdf.",
                    default=None,
                    cli=("-o", "--output"),
                ),
                _dpi(),
                _quality(),
                Param(
                    "no_compress",
                    ParamKind.BOOL,
                    "Merge only; skip the compression.",
                    default=False,
                    cli=("--no-compress",),
                ),
            ),
        ),
        Action(
            group="pdf",
            name="split",
            summary="Keep or remove a page range, or split into chunks of N pages.",
            operation=f"{OPS}:split",
            params=(
                _pdf("PDF file to split."),
                Param(
                    "start",
                    ParamKind.INT,
                    "First page, counting from 1.",
                    default=1,
                    cli=("-s", "--start"),
                ),
                Param(
                    "end",
                    ParamKind.INT,
                    "Last page; -1 means the last page.",
                    default=-1,
                    cli=("-e", "--end"),
                ),
                _output(),
                Param(
                    "chunks",
                    ParamKind.INT,
                    "Split into files of this many pages. 0 turns it off.",
                    default=0,
                    cli=("-c", "--chunks"),
                    advanced=True,
                ),
                Param(
                    "remove",
                    ParamKind.BOOL,
                    "Remove the range instead of keeping it.",
                    default=False,
                    cli=("--remove",),
                ),
                Param(
                    "list_pages",
                    ParamKind.BOOL,
                    "Only show the page count.",
                    default=False,
                    cli=("--list",),
                    advanced=True,
                ),
            ),
        ),
        Action(
            group="pdf",
            name="stamp",
            summary="Write a watermark such as CONFIDENTIAL across every page.",
            operation=f"{OPS}:stamp",
            params=(
                _pdf("PDF to watermark."),
                Param("text", ParamKind.TEXT, "Text to stamp.", default="DRAFT"),
                _output(),
            ),
        ),
        Action(
            group="pdf",
            name="lock",
            summary="Protect a PDF with a password.",
            operation=f"{OPS}:lock",
            params=(
                _pdf("PDF to encrypt."),
                Param(
                    "password",
                    ParamKind.SECRET,
                    "Password needed to open the file.",
                    cli=("--password", "-p"),
                ),
                _output(),
            ),
            surfaces=NOT_FOR_AGENT,
        ),
        Action(
            group="pdf",
            name="rip",
            summary="Extract every image inside a PDF.",
            operation=f"{OPS}:rip",
            params=(
                _pdf("PDF to extract from."),
                Param(
                    "output_dir",
                    ParamKind.FOLDER,
                    "Folder for the images. Default: <name>_assets.",
                    default=None,
                    cli=("-o",),
                ),
            ),
        ),
        Action(
            group="pdf",
            name="ocr",
            summary="Read the text of a scanned PDF into a .txt file."
            " Needs Tesseract (pip install max-cli[ocr]).",
            operation=f"{OPS}:ocr",
            params=(
                _pdf("Scanned PDF."),
                Param(
                    "lang",
                    ParamKind.TEXT,
                    "Tesseract language code: eng, deu, fra, or eng+deu.",
                    default="eng",
                    cli=("--lang", "-l"),
                ),
                _output("Text file. Default: the PDF's name with .txt."),
            ),
        ),
        Action(
            group="pdf",
            name="form-data",
            summary="Show the values in a PDF form's fields.",
            operation=f"{OPS}:form_data",
            params=(_pdf("PDF form."),),
            danger=Danger.NONE,
        ),
        Action(
            group="pdf",
            name="form-fill",
            summary="Fill a PDF form's fields.",
            operation=f"{OPS}:form_fill",
            params=(
                _pdf("PDF form to fill."),
                Param(
                    "field",
                    ParamKind.TEXT,
                    "Field values as name=value, e.g. name=John.",
                    cli=("-f", "--field"),
                    multiple=True,
                ),
                _output(),
            ),
        ),
        Action(
            group="pdf",
            name="form-flatten",
            summary="Turn a form's fields into plain page content.",
            operation=f"{OPS}:form_flatten",
            params=(_pdf("PDF form to flatten."), _output()),
        ),
        Action(
            group="pdf",
            name="optimize",
            summary="Remove unused objects, compress images and prepare for the web.",
            operation=f"{OPS}:optimize",
            params=(
                _pdf("PDF to optimize."),
                _output(),
                Param(
                    "no_compress",
                    ParamKind.BOOL,
                    "Skip image compression.",
                    default=False,
                    cli=("--no-compress",),
                    advanced=True,
                ),
                Param(
                    "no_linearize",
                    ParamKind.BOOL,
                    "Skip web optimization.",
                    default=False,
                    cli=("--no-linearize",),
                    advanced=True,
                ),
            ),
        ),
        Action(
            group="pdf",
            name="compare",
            summary="Compare two PDFs page by page.",
            operation=f"{OPS}:compare",
            params=(
                Param("file1", ParamKind.FILE, "First PDF."),
                Param("file2", ParamKind.FILE, "Second PDF."),
            ),
            danger=Danger.NONE,
        ),
    ),
)
