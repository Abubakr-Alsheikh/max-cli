"""`max images` operations: find the images, name the outputs, run the engine on each.

The CLI, the dashboard and the agent all call these through the catalog
(`core/catalog/groups/images.py`). They never prompt or print. Pass `emitter`
to get batch progress events; pass `engine` to reuse an ImageEngine.

Output naming, the same for every caller:
- a file `photo.jpg` gives `photo_opt.jpg` next to it;
- a folder `photos/` gives `photos_optimized/` next to it, with each image
  under its own name.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from max_cli.common.exceptions import ResourceNotFoundError, ValidationError
from max_cli.core.operations.result import ActionResult
from max_cli.core.presets import STRIP_IMAGE_METADATA

if TYPE_CHECKING:
    from max_cli.common.events import EventEmitter
    from max_cli.core.engines.image_processor import ImageEngine

IMAGE_FORMATS = ("webp", "jpg", "png")
FORMAT_ALIASES = {"jpeg": "jpg"}
SINGLE_FILE_SUFFIX = "_opt"
BATCH_FOLDER_SUFFIX = "_optimized"
QUALITY_RANGE = range(1, 101)


def _engine(engine: Optional["ImageEngine"]) -> "ImageEngine":
    if engine is not None:
        return engine
    from max_cli.core.engines.image_processor import ImageEngine

    return ImageEngine()


def resolve_batch(target: Path) -> tuple[list[Path], Path]:
    """The images to process and the folder their results go to.

    A folder yields its own images, not those in subfolders.
    """
    # Resolve first: Path(".").name is "", which made the folder "_optimized".
    target = target.expanduser().resolve()
    if not target.exists():
        raise ResourceNotFoundError(f"Not found: {target}")
    if target.is_file():
        return [target], target.parent
    from max_cli.core.engines.image_processor import ImageEngine

    images = sorted(
        path
        for path in target.iterdir()
        if path.is_file() and path.suffix.lower() in ImageEngine.SUPPORTED_EXTENSIONS
    )
    return images, target.parent / f"{target.name}{BATCH_FOLDER_SUFFIX}"


def _workers(workers: Optional[int]) -> int:
    from max_cli.config import settings

    return max(1, workers if workers is not None else settings.MAX_WORKERS)


def _run_batch(
    target: Path,
    label: str,
    workers: Optional[int],
    engine: Optional["ImageEngine"],
    emitter: Optional["EventEmitter"],
    **engine_options: Any,
) -> ActionResult:
    from max_cli.common.concurrent import process_batch_parallel

    images, out_dir = resolve_batch(target)
    if not images:
        return ActionResult(False, f"No images found in {target.resolve()}")
    single_file = images == [target.expanduser().resolve()]
    out_dir.mkdir(exist_ok=True)
    image_engine = _engine(engine)

    def process(image: Path) -> dict[str, Any]:
        name = f"{image.stem}{SINGLE_FILE_SUFFIX}{image.suffix}"
        output = out_dir / (name if single_file else image.name)
        return image_engine.process_single_image(image, output, **engine_options)

    results = process_batch_parallel(
        images, process, max_workers=_workers(workers), emitter=emitter, action=label
    )
    done = [result for result in results if "error" not in result]
    failed = [result for result in results if "error" in result]
    details = {
        "output_dir": str(out_dir),
        "processed": [
            {
                "file_name": result["file_name"],
                "original_size": result["original_size"],
                "final_size": result["final_size"],
                "reduction_pct": result["reduction_pct"],
            }
            for result in done
        ],
        "failed": [
            {"file": Path(result["item"]).name, "error": result["error"]}
            for result in failed
        ],
    }
    if not done:
        return ActionResult(False, f"{label} failed for every image.", details=details)
    message = f"Output saved to: {out_dir}"
    if failed:
        message += f" ({len(failed)} of {len(images)} images failed)"
    return ActionResult(
        ok=True,
        message=message,
        output_files=[Path(result["out_path"]) for result in done],
        details=details,
    )


def compress(
    target: Path = Path("."),
    quality: Optional[int] = None,
    scale: Optional[int] = None,
    max_dim: Optional[int] = None,
    force_jpeg: bool = False,
    quantize: bool = False,
    strip: bool = STRIP_IMAGE_METADATA,
    workers: Optional[int] = None,
    *,
    engine: Optional["ImageEngine"] = None,
    emitter: Optional["EventEmitter"] = None,
) -> ActionResult:
    """Compress, resize and convert in one pass. quality None uses DEFAULT_QUALITY."""
    from max_cli.config import settings

    quality = quality if quality is not None else settings.DEFAULT_QUALITY
    if quality not in QUALITY_RANGE:
        raise ValidationError("Quality must be between 1 and 100.")
    return _run_batch(
        target,
        "Optimizing",
        workers,
        engine,
        emitter,
        quality=quality,
        scale=scale,
        max_dim=max_dim,
        force_format="jpg" if force_jpeg else None,
        quantize_png=quantize,
        strip_exif=strip,
    )


def resize(
    target: Path = Path("."),
    width: Optional[int] = None,
    height: Optional[int] = None,
    scale: Optional[int] = None,
    workers: Optional[int] = None,
    *,
    engine: Optional["ImageEngine"] = None,
    emitter: Optional["EventEmitter"] = None,
) -> ActionResult:
    if not any((width, height, scale)):
        raise ValidationError("Specify --width, --height, or --scale.")
    return _run_batch(
        target,
        "Resizing",
        workers,
        engine,
        emitter,
        width=width,
        height=height,
        scale=scale,
    )


def convert(
    target: Path = Path("."),
    to: Optional[str] = None,  # required; None only because target has a default
    workers: Optional[int] = None,
    *,
    engine: Optional["ImageEngine"] = None,
    emitter: Optional["EventEmitter"] = None,
) -> ActionResult:
    if not to:
        raise ValidationError(
            f"Choose a format to convert to: {', '.join(IMAGE_FORMATS)}."
        )
    image_format = to.lower().lstrip(".")
    image_format = FORMAT_ALIASES.get(image_format, image_format)
    if image_format not in IMAGE_FORMATS:
        raise ValidationError(
            f"Unknown format '{to}'. Choose one of: {', '.join(IMAGE_FORMATS)}."
        )
    return _run_batch(
        target, "Converting", workers, engine, emitter, force_format=image_format
    )


def strip(
    target: Path = Path("."),
    workers: Optional[int] = None,
    *,
    engine: Optional["ImageEngine"] = None,
    emitter: Optional["EventEmitter"] = None,
) -> ActionResult:
    """Remove GPS and other EXIF data."""
    return _run_batch(target, "Stripping", workers, engine, emitter, strip_exif=True)
