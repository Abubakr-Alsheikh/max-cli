import re
from pathlib import Path

def natural_sort_key(s: str) -> list:
    """
    Splits a string into a list of integers and text chunks.
    Used for sorting ["1_doc", "10_doc", "2_doc"] -> ["1_doc", "2_doc", "10_doc"]
    """
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split(r"(\d+)", s)
    ]

def format_size(size_in_bytes: float) -> str:
    """Returns a human-readable file size string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.2f} TB"