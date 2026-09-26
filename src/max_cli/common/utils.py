import base64
import os
import re
import subprocess
import sys
from pathlib import Path


def natural_sort_key(s: str) -> list:
    """
    Splits a string into a list of integers and text chunks.
    Used for sorting ["1_doc", "10_doc", "2_doc"] -> ["1_doc", "2_doc", "10_doc"]
    """
    return [
        int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)
    ]


def format_size(size_in_bytes: float) -> str:
    """Returns a human-readable file size string, handling negative values (growth)."""
    is_negative = size_in_bytes < 0
    size = abs(size_in_bytes)

    final_unit = "B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        final_unit = unit
        if size < 1024.0:
            break
        size /= 1024.0

    prefix = "-" if is_negative else ""
    return f"{prefix}{size:.2f} {final_unit}"


def encode_image_to_base64(image_path: Path) -> str:
    """
    Reads a file and returns a base64 string for AI consumption.
    """
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def open_in_file_manager(path: Path) -> None:
    """Show a folder (or the folder holding a file) in the system file manager."""
    folder = path if path.is_dir() else path.parent
    if sys.platform == "win32":
        # os.startfile exists only on Windows, so mypy on other systems can't see it.
        getattr(os, "startfile")(str(folder))  # noqa: B009
    elif sys.platform == "darwin":
        subprocess.run(["open", str(folder)], check=False)
    else:
        subprocess.run(["xdg-open", str(folder)], check=False)
