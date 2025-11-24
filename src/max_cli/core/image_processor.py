import os
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image

# Handle Pillow version differences
try:
    from PIL.Image import Resampling

    LANCZOS = Resampling.LANCZOS
except ImportError:
    LANCZOS = Image.LANCZOS  # type: ignore


class ImageEngine:
    """Core logic for image manipulation."""

    @staticmethod
    def get_size_str(file_path: Path) -> str:
        """Returns human readable file size."""
        size = file_path.stat().st_size
        if size < 1024 * 1024:
            return f"{size / 1024:.2f} KB"
        return f"{size / (1024 * 1024):.2f} MB"

    def process_image(
        self,
        input_path: Path,
        output_path: Path,
        quality: int = 85,
        force_jpeg: bool = False,
        quantize_png: bool = False,
        scale: Optional[int] = None,
        max_dim: Optional[int] = None,
    ) -> dict:
        """
        Compresses/Resizes a single image.
        Returns a dictionary with stats.
        """
        if not input_path.exists():
            raise FileNotFoundError(f"'{input_path}' does not exist.")

        img = Image.open(input_path)
        original_dims = img.size

        # --- Resizing Logic ---
        if scale:
            new_w = int(original_dims[0] * (scale / 100))
            new_h = int(original_dims[1] * (scale / 100))
            img = img.resize((new_w, new_h), resample=LANCZOS)
        elif max_dim:
            if max(original_dims) > max_dim:
                img.thumbnail((max_dim, max_dim), resample=LANCZOS)

        # --- Format Logic ---
        output_format = output_path.suffix.upper().strip(".")
        if output_format == "JPG":
            output_format = "JPEG"

        # Handle transparency/mode for JPEG
        if (force_jpeg or output_format == "JPEG") and img.mode in ["P", "RGBA"]:
            img = img.convert("RGB")
            output_path = output_path.with_suffix(".jpg")

        # --- Save Logic ---
        if output_format == "JPEG" or force_jpeg:
            img.save(output_path, "JPEG", quality=quality, optimize=True)
        elif output_format == "PNG" and quantize_png:
            if img.mode not in ["RGB", "L"]:
                img = img.convert("RGBA")
            q_img = img.quantize(
                colors=256, method=2, dither=Image.Dither.FLOYDSTEINBERG
            )
            q_img.save(output_path, "PNG", optimize=True)
        else:
            img.save(output_path, optimize=True)

        return {
            "file": input_path.name,
            "original_size": self.get_size_str(input_path),
            "new_size": self.get_size_str(output_path),
            "reduction_bytes": input_path.stat().st_size - output_path.stat().st_size,
        }
