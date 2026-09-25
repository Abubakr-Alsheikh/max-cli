"""Crash-safe file writes for state files (queue, history, cache, logs, config).

A write goes to a temp file in the destination folder, is flushed to disk, then
replaces the destination in one step. A crash or Ctrl+C mid-write leaves the
previous file intact instead of a truncated one.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

JSON_INDENT = 2


def atomic_write_text(path: Path, text: str) -> None:
    """Replace `path` with `text` (utf-8) atomically."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp"
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(destination)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def atomic_write_json(
    path: Path,
    data: Any,
    *,
    indent: Optional[int] = JSON_INDENT,
    default: Optional[Callable[[Any], Any]] = None,
) -> None:
    """Serialize `data` first (so bad data never touches the file), then write it."""
    atomic_write_text(path, json.dumps(data, indent=indent, default=default))
