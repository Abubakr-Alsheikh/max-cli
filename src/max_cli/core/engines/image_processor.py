import io
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from max_cli.common.exceptions import ProcessingError

if TYPE_CHECKING:
    from PIL import Image

logger = logging.getLogger(__name__)

# EXIF orientations 5 to 8 turn the picture a quarter: its stored width is
# the shown height.
ROTATED_ORIENTATIONS = {5, 6, 7, 8}

SVG_SUFFIX = ".svg"
HEIF_SUFFIXES = frozenset({".heic", ".heif"})
# An SVG has no pixels: Max draws it so its longest side is at least this
# many, so a small logo doesn't come out as a blurry thumbnail.
SVG_MIN_SIDE = 1024
# What Max writes: Pillow's format name, the file suffix, and whether the
# format keeps transparency. Others get a white background.
OUTPUT_FORMATS: dict[str, tuple[str, str, bool]] = {
    "jpg": ("JPEG", ".jpg", False),
    "jpeg": ("JPEG", ".jpg", False),
    "png": ("PNG", ".png", True),
    "webp": ("WEBP", ".webp", True),
    "avif": ("AVIF", ".avif", True),
    "gif": ("GIF", ".gif", True),
    "bmp": ("BMP", ".bmp", False),
    "tiff": ("TIFF", ".tiff", True),
    "tif": ("TIFF", ".tif", True),
    "ico": ("ICO", ".ico", True),
}
FALLBACK_FORMAT = "png"  # for sources Max reads but doesn't write (SVG, PSD ...)
LOSSY_FORMATS = frozenset({"JPEG", "WEBP", "AVIF"})
WHITE = (255, 255, 255)


def open_image(path: Path) -> "Image.Image":
    """Any image Max reads: every format Pillow opens, SVG (drawn with
    PyMuPDF) and HEIC/HEIF when pillow-heif is installed. Use it with `with`."""
    from PIL import Image, UnidentifiedImageError

    suffix = path.suffix.lower()
    if suffix == SVG_SUFFIX:
        return _draw_svg(path)
    if suffix in HEIF_SUFFIXES:
        _enable_heif()
    try:
        return Image.open(path)
    except UnidentifiedImageError as e:
        raise ProcessingError(f"{path.name} isn't an image Max can read") from e


def _draw_svg(path: Path) -> "Image.Image":
    """The SVG drawn as RGBA pixels, transparent where it draws nothing, by
    resvg (masks, filters, gradients, embedded images); PyMuPDF, which skips
    masks and filters, only when resvg is missing or refuses the file."""
    try:
        import resvg_py
    except ImportError:
        return _draw_svg_with_mupdf(path)
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(_png(resvg_py.svg_to_bytes(svg_path=str(path)))))
        longest = max(img.size) or 1
        if longest < SVG_MIN_SIDE:
            scale = SVG_MIN_SIDE / longest
            bigger = resvg_py.svg_to_bytes(
                svg_path=str(path),
                width=round(img.width * scale),
                height=round(img.height * scale),
            )
            img = Image.open(io.BytesIO(_png(bigger)))
        img.load()
    except (ValueError, RuntimeError, OSError) as e:
        logger.warning("resvg couldn't draw %s (%s); trying PyMuPDF", path.name, e)
        return _draw_svg_with_mupdf(path)
    return img.convert("RGBA")


def _png(data: Any) -> bytes:
    """resvg-py's PNG: bytes, or a list from 0.2.0 (Python 3.9 on macOS)."""
    if isinstance(data, list):
        return b"".join(data) if data and isinstance(data[0], bytes) else bytes(data)
    return bytes(data)


def _draw_svg_with_mupdf(path: Path) -> "Image.Image":
    import fitz
    from PIL import Image

    try:
        document = fitz.open(str(path))
    except (RuntimeError, ValueError) as e:  # fitz.FileDataError is a RuntimeError
        raise ProcessingError(f"Couldn't read the SVG {path.name}: {e}") from e
    with document:
        page = document[0]
        longest = max(page.rect.width, page.rect.height) or 1
        zoom = max(1.0, SVG_MIN_SIDE / longest)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=True)
        return Image.frombytes("RGBA", (pixmap.width, pixmap.height), pixmap.samples)


def _enable_heif() -> None:
    try:
        import pillow_heif
    except ImportError as e:
        raise ProcessingError(
            "HEIC photos need the pillow-heif package: pip install pillow-heif"
        ) from e
    pillow_heif.register_heif_opener()


def _on_white(img: "Image.Image") -> "Image.Image":
    """`img` as RGB, with transparent parts white (not black) for formats
    that can't keep transparency."""
    from PIL import Image

    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        flat = Image.new("RGB", rgba.size, WHITE)
        flat.paste(rgba, mask=rgba.getchannel("A"))
        return flat
    return img if img.mode in ("RGB", "L") else img.convert("RGB")


def _output_format(
    force_format: Optional[str], output_path: Path, input_path: Path
) -> tuple[str, str, bool]:
    """The format asked for, else the source's own, else PNG (an SVG, a
    PSD: formats Max reads but doesn't write)."""
    for wanted in (
        force_format or output_path.suffix.lstrip("."),
        input_path.suffix.lstrip("."),
    ):
        if wanted.lower() in OUTPUT_FORMATS:
            return OUTPUT_FORMATS[wanted.lower()]
    return OUTPUT_FORMATS[FALLBACK_FORMAT]


def _pixels_only(img: "Image.Image") -> "Image.Image":
    """A copy of `img` with its pixels (and palette) but no EXIF or other info.

    Uses paste instead of getdata/putdata: getdata is deprecated in Pillow 12,
    and the old rebuild dropped the palette of "P" mode images.
    """
    from PIL import Image

    clean_img = Image.new(img.mode, img.size)
    palette = img.getpalette()
    if img.mode == "P" and palette:
        clean_img.putpalette(palette)
    clean_img.paste(img)
    return clean_img


class ImageEngine:
    """
    Business logic for image manipulation.
    """

    # The images a folder gives (file_kinds.IMAGE says the same).
    SUPPORTED_EXTENSIONS = {
        ".jpg",
        ".jpeg",
        ".jfif",
        ".png",
        ".bmp",
        ".gif",
        ".webp",
        ".avif",
        ".tiff",
        ".tif",
        ".ico",
        ".svg",
        ".heic",
        ".heif",
        ".tga",
        ".psd",
    }

    def get_size_str(self, size_bytes: int) -> str:
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        return f"{size_bytes / (1024 * 1024):.2f} MB"

    def inspect_image(self, input_path: Path) -> dict[str, Any]:
        """What an image holds, read without changing it.

        Keys: format, mode, width, height (as shown, after the EXIF rotation),
        frames, has_exif, has_gps, taken (EXIF date and time, "" without one)
        and camera (the EXIF model). Raises RuntimeError for a file Pillow
        can't open.
        """
        from PIL import ExifTags

        try:
            img = open_image(input_path)
        except (ProcessingError, OSError) as e:
            raise RuntimeError(f"Couldn't read this image: {e}") from e
        with img:
            exif = img.getexif()
            details = exif.get_ifd(ExifTags.IFD.Exif)
            width, height = img.size
            if exif.get(ExifTags.Base.Orientation) in ROTATED_ORIENTATIONS:
                width, height = height, width
            taken = details.get(ExifTags.Base.DateTimeOriginal) or exif.get(
                ExifTags.Base.DateTime
            )
            return {
                "format": img.format or input_path.suffix.lstrip(".").upper(),
                "mode": img.mode,
                "width": width,
                "height": height,
                "frames": getattr(img, "n_frames", 1),
                "has_exif": bool(exif),
                "has_gps": bool(exif.get_ifd(ExifTags.IFD.GPSInfo)),
                "taken": str(taken or "").strip(),
                "camera": str(exif.get(ExifTags.Base.Model) or "").strip(),
            }

    def strip_metadata(self, input_path: Path, output_path: Path) -> None:
        """Removes EXIF and other metadata by re-saving pixel data only."""
        if input_path.suffix.lower() == SVG_SUFFIX:
            raise ProcessingError(
                f"{input_path.name} is a drawing: it has no photo data"
            )
        with open_image(input_path) as img:
            _pixels_only(img).save(output_path, optimize=True)

    def process_single_image(
        self,
        input_path: Path,
        output_path: Path,
        quality: int = 85,
        scale: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        max_dim: Optional[int] = None,
        force_format: Optional[str] = None,
        quantize_png: bool = False,
        strip_exif: bool = False,
    ) -> dict[str, Any]:
        """
        Versatile processor for compression, resizing, and conversion.
        """
        from PIL import Image, ImageOps, features

        try:
            from PIL.Image import Resampling

            LANCZOS = Resampling.LANCZOS
        except ImportError:
            LANCZOS = Image.LANCZOS  # type: ignore

        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")

        with open_image(input_path) as img:
            img = ImageOps.exif_transpose(img)
            original_size = input_path.stat().st_size
            original_dims = img.size

            # --- 1. Resizing ---
            new_size = None
            if scale:
                new_size = (
                    int(original_dims[0] * (scale / 100)),
                    int(original_dims[1] * (scale / 100)),
                )
            elif width or height:
                if width is not None and height is not None:
                    w, h = width, height
                elif width is not None:
                    w = width
                    h = int(original_dims[1] * (width / original_dims[0]))
                else:
                    w = int(original_dims[0] * (height / original_dims[1]))
                    h = height  # type: ignore[assignment]
                new_size = (w, h)
            elif max_dim:
                if max(original_dims) > max_dim:
                    img.thumbnail((max_dim, max_dim), resample=LANCZOS)

            if new_size:
                img = img.resize(new_size, resample=LANCZOS)

            # --- 2. Format Determination ---
            # A format Max doesn't write (an SVG, a PSD) becomes a PNG.
            target_format, target_ext, keeps_alpha = _output_format(
                force_format, output_path, input_path
            )
            if target_format == "AVIF" and not features.check("avif"):
                raise ProcessingError(
                    "This Pillow can't write AVIF. Update it: pip install -U pillow"
                )
            if not keeps_alpha:
                img = _on_white(img)

            output_path = output_path.with_suffix(target_ext)

            # --- 3. Save Logic ---
            save_args = {"optimize": True}

            # Lossy PNG Quantization
            if target_format == "PNG" and quantize_png:
                if img.mode not in ["RGB", "L"]:
                    img = img.convert("RGBA")
                img = img.quantize(
                    colors=256,
                    method=2,
                    dither=Image.Dither.FLOYDSTEINBERG,  # type: ignore[assignment]
                )

            if target_format in LOSSY_FORMATS:
                save_args["quality"] = quality

            if strip_exif:
                # Rebuild image to drop all hidden metadata blocks
                img = _pixels_only(img)
            try:
                img.save(output_path, target_format, **save_args)
            except OSError:
                # A mode the format can't hold (CMYK as PNG, 16-bit as GIF).
                img.convert("RGBA").save(output_path, target_format, **save_args)

        return {
            "file_name": input_path.name,
            "original_size": self.get_size_str(original_size),
            "final_size": self.get_size_str(output_path.stat().st_size),
            "reduction_pct": (
                round(
                    ((original_size - output_path.stat().st_size) / original_size)
                    * 100,
                    1,
                )
                if original_size > 0
                else 0
            ),
            "out_path": output_path,
        }
