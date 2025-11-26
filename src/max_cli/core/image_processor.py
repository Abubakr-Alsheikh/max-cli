from pathlib import Path
from typing import Optional, Dict, Any 
from PIL import Image

# Handle Pillow version differences for Resampling
try:
    from PIL.Image import Resampling

    LANCZOS = Resampling.LANCZOS
except ImportError:
    LANCZOS = Image.LANCZOS  # type: ignore


class ImageEngine:
    """
    Business logic for image manipulation.
    Decoupled from CLI to allow easier testing and AI integration.
    """

    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff"}

    def get_size_str(self, size_bytes: int) -> str:
        """Helper to format bytes into KB/MB."""
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        return f"{size_bytes / (1024 * 1024):.2f} MB"

    def process_single_image(
        self,
        input_path: Path,
        output_path: Path,
        quality: int = 85,
        force_jpeg: bool = False,
        quantize_png: bool = False,
        scale: Optional[int] = None,
        max_dim: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Compresses and/or resizes a single image.
        Returns a dictionary containing statistics about the operation.
        """
        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")

        # Open Image
        with Image.open(input_path) as img:
            original_dims = img.size
            original_size = input_path.stat().st_size

            # --- 1. Resizing Logic ---
            if scale:
                # Resize by percentage
                new_w = int(original_dims[0] * (scale / 100))
                new_h = int(original_dims[1] * (scale / 100))
                img = img.resize((new_w, new_h), resample=LANCZOS)
            elif max_dim:
                # Resize strictly by longest side
                if max(original_dims) > max_dim:
                    img.thumbnail((max_dim, max_dim), resample=LANCZOS)

            # --- 2. Format & Mode Logic ---
            # Determine target format based on output filename
            output_format = output_path.suffix.upper().lstrip(".")
            if output_format == "JPG":
                output_format = "JPEG"

            # Force JPEG logic or format correction
            if (force_jpeg or output_format == "JPEG") and img.mode in ["P", "RGBA"]:
                img = img.convert("RGB")
                # Ensure path ends in .jpg
                output_path = output_path.with_suffix(".jpg")
                output_format = "JPEG"

            # --- 3. Saving Logic ---
            if output_format == "JPEG":
                img.save(output_path, "JPEG", quality=quality, optimize=True)

            elif output_format == "PNG" and quantize_png:
                # Lossy PNG
                if img.mode not in ["RGB", "L"]:
                    img = img.convert("RGBA")
                quantized = img.quantize(
                    colors=256, method=2, dither=Image.Dither.FLOYDSTEINBERG
                )
                quantized.save(output_path, "PNG", optimize=True)

            else:
                # Standard save
                img.save(output_path, optimize=True)

        # Return stats
        final_size = output_path.stat().st_size
        reduction_bytes = original_size - final_size
        reduction_pct = (
            (reduction_bytes / original_size) * 100 if original_size > 0 else 0
        )

        return {
            "file_name": input_path.name,
            "original_size": self.get_size_str(original_size),
            "final_size": self.get_size_str(final_size),
            "reduction_pct": round(reduction_pct, 1),
        }
