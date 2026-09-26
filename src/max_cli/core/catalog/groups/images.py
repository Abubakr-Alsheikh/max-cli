"""Catalog entries for `max images`. `tests/test_catalog_drift.py` checks them against the CLI."""

from pathlib import Path

from max_cli.core.catalog.spec import Action, Group, Param, ParamKind, Setting
from max_cli.core.presets import STRIP_IMAGE_METADATA

OPS = "max_cli.core.operations.images"
# Same list as core/operations/images.py IMAGE_FORMATS; catalog modules
# don't import operations.
IMAGE_FORMATS = ("webp", "jpg", "png")


def _target() -> Param:
    return Param(
        "target",
        ParamKind.FILE,
        "An image, or a folder of images. A folder's results go to"
        " <folder>_optimized next to it.",
        default=Path("."),
    )


def _workers() -> Param:
    return Param(
        "workers",
        ParamKind.INT,
        "Images to process at once.",
        default=Setting("MAX_WORKERS"),
        cli=("-j",),
        advanced=True,
    )


GROUP = Group(
    name="images",
    summary="Compress, resize, convert and clean images.",
    actions=(
        Action(
            group="images",
            name="compress",
            summary="Make images smaller: compress, resize and convert in one pass.",
            operation=f"{OPS}:compress",
            params=(
                _target(),
                Param(
                    "quality",
                    ParamKind.INT,
                    "JPEG and WebP quality, 1 to 100. Lower is smaller.",
                    default=Setting("DEFAULT_QUALITY"),
                    cli=("-q",),
                ),
                Param(
                    "scale",
                    ParamKind.INT,
                    "Resize to this percentage, e.g. 50.",
                    default=None,
                    cli=("-s",),
                ),
                Param(
                    "max_dim",
                    ParamKind.INT,
                    "Shrink so the longest side is at most this many pixels.",
                    default=None,
                    cli=("-m",),
                ),
                Param(
                    "force_jpeg",
                    ParamKind.BOOL,
                    "Save as JPEG, whatever the input format.",
                    default=False,
                    cli=("--jpeg",),
                    advanced=True,
                ),
                Param(
                    "quantize",
                    ParamKind.BOOL,
                    "Lossy PNG compression (256 colors).",
                    default=False,
                    cli=("--quantize",),
                    advanced=True,
                ),
                Param(
                    "strip",
                    ParamKind.BOOL,
                    "Remove EXIF metadata such as GPS position.",
                    default=STRIP_IMAGE_METADATA,
                    cli=("--strip",),
                    advanced=True,
                ),
                _workers(),
            ),
        ),
        Action(
            group="images",
            name="resize",
            summary="Change image dimensions. Give a width, a height or a scale.",
            operation=f"{OPS}:resize",
            params=(
                _target(),
                Param(
                    "width",
                    ParamKind.INT,
                    "Width in pixels. Alone, it keeps the aspect ratio.",
                    default=None,
                    cli=("-w",),
                ),
                Param(
                    "height",
                    ParamKind.INT,
                    "Height in pixels. Alone, it keeps the aspect ratio.",
                    default=None,
                    cli=("-h",),
                ),
                Param(
                    "scale",
                    ParamKind.INT,
                    "Resize to this percentage, e.g. 50.",
                    default=None,
                    cli=("-s",),
                ),
                _workers(),
            ),
        ),
        Action(
            group="images",
            name="convert",
            summary="Convert images to another format.",
            operation=f"{OPS}:convert",
            params=(
                _target(),
                Param(
                    "to",
                    ParamKind.CHOICE,
                    "Target format.",
                    choices=IMAGE_FORMATS,
                    cli=("--to",),
                ),
                _workers(),
            ),
        ),
        Action(
            group="images",
            name="strip",
            summary="Remove GPS and other EXIF data from images, for privacy.",
            operation=f"{OPS}:strip",
            params=(_target(), _workers()),
        ),
    ),
)
