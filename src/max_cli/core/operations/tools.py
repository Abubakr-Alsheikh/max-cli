"""`max tools` operations: a QR code for a link, and the clipboard.

The CLI, the dashboard's Extras page and the agent call these through the
catalog (`core/catalog/groups/tools.py`). They never prompt or print. Pass
`engine` to use a SystemEngine you already have.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from max_cli.common.exceptions import (
    ProcessingError,
    ResourceNotFoundError,
    ValidationError,
)
from max_cli.core.operations.result import ActionResult

if TYPE_CHECKING:
    from max_cli.core.engines.system_engine import SystemEngine

DEFAULT_PASTE_OUTPUT = Path("clipboard.png")
PASTE_SUFFIX = ".png"


def _engine(engine: Optional["SystemEngine"]) -> "SystemEngine":
    if engine is not None:
        return engine
    from max_cli.core.engines.system_engine import SystemEngine

    return SystemEngine()


def paste_target(output: Path) -> Path:
    """Where paste saves: `output`, with .png added when it has no suffix."""
    return output if output.suffix else output.with_suffix(PASTE_SUFFIX)


def share(data: str, *, engine: Optional["SystemEngine"] = None) -> ActionResult:
    """A QR code for `data`, as text blocks in details["qr"]."""
    if not data.strip():
        raise ValidationError("Give the text or link to put in the QR code.")
    qr_text = _engine(engine).generate_qr(data)
    return ActionResult(
        True, f"QR code for {data}", details={"qr": qr_text, "data": data}
    )


def paste(
    output: Path = DEFAULT_PASTE_OUTPUT,
    overwrite: bool = False,
    *,
    engine: Optional["SystemEngine"] = None,
) -> ActionResult:
    """Save the clipboard's image. An existing file stays unless `overwrite`.

    An empty clipboard, or one holding text, isn't an error: the result says
    so with ok False and nothing is written.
    """
    target = paste_target(output)
    if target.exists() and not overwrite:
        raise ValidationError(
            f"{target} already exists. Pick another name, or allow overwriting it."
        )
    try:
        _engine(engine).save_clipboard_image(target)
    except ValueError as e:
        return ActionResult(False, str(e))
    return ActionResult(True, f"Saved the clipboard image to {target}", [target])


def copy(target: Path, *, engine: Optional["SystemEngine"] = None) -> ActionResult:
    """Put a text file's contents on the clipboard."""
    try:
        _engine(engine).copy_file_to_clipboard(target)
    except FileNotFoundError as e:
        raise ResourceNotFoundError(f"File not found: {target}") from e
    except ValueError as e:
        raise ValidationError(str(e)) from e
    except RuntimeError as e:
        raise ProcessingError(str(e)) from e
    return ActionResult(True, f"Copied {target.name} to the clipboard.")
