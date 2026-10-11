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


# Decimal units, as upload limits count them ("25 MB" on a mail or chat
# service is 25,000,000 bytes), so a file sized for "25MB" fits either way.
SIZE_UNITS = {
    "": 1,
    "b": 1,
    "k": 1000,
    "kb": 1000,
    "m": 1000**2,
    "mb": 1000**2,
    "g": 1000**3,
    "gb": 1000**3,
}
SIZE_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([a-z]*)\s*$", re.IGNORECASE)


def parse_size(text: str) -> int:
    """Bytes in a size such as "25MB", "800 kb", "1.5G" or "500000".

    Raises ValueError for text that isn't a positive size.
    """
    match = SIZE_PATTERN.match(text or "")
    unit = match.group(2).lower() if match else ""
    if not match or unit not in SIZE_UNITS:
        raise ValueError(f"'{text}' isn't a size. Write it like 25MB, 800KB or 1.5GB.")
    size_bytes = int(float(match.group(1)) * SIZE_UNITS[unit])
    if size_bytes <= 0:
        raise ValueError(f"'{text}' is no size at all. Give more than 0.")
    return size_bytes


def format_decimal_size(size_bytes: float) -> str:
    """A size in the decimal units parse_size reads: 25000000 is "25 MB"."""
    for unit, factor in (("GB", 1000**3), ("MB", 1000**2), ("KB", 1000)):
        if size_bytes >= factor:
            return f"{size_bytes / factor:.3g} {unit}"
    return f"{size_bytes:.0f} B"


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
