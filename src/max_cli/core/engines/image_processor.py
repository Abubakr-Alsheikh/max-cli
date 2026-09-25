from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from PIL import Image


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

    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff"}

    def get_size_str(self, size_bytes: int) -> str:
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        return f"{size_bytes / (1024 * 1024):.2f} MB"

    def strip_metadata(self, input_path: Path, output_path: Path) -> None:
        """Removes EXIF and other metadata by re-saving pixel data only."""
        from PIL import Image

        with Image.open(input_path) as img:
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
        from PIL import Image, ImageOps

        try:
            from PIL.Image import Resampling

            LANCZOS = Resampling.LANCZOS
        except ImportError:
            LANCZOS = Image.LANCZOS  # type: ignore

        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")

        with Image.open(input_path) as img:
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
            target_ext = (
                force_format.lower()
                if force_format
                else output_path.suffix.lower().lstrip(".")
            )
            if target_ext in ["jpg", "jpeg"]:
                target_format, target_ext = "JPEG", ".jpg"
                if img.mode in ["RGBA", "P"]:
                    img = img.convert("RGB")
            elif target_ext == "webp":
                target_format, target_ext = "WEBP", ".webp"
            elif target_ext == "png":
                target_format, target_ext = "PNG", ".png"
            else:
                target_format = img.format or "PNG"
                target_ext = input_path.suffix

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

            if target_format in ["JPEG", "WEBP"]:
                save_args["quality"] = quality

            if strip_exif:
                # Rebuild image to drop all hidden metadata blocks
                _pixels_only(img).save(output_path, target_format, **save_args)
            else:
                img.save(output_path, target_format, **save_args)

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
