"""Read and update ~/.max_config.env, the file `Settings` loads first.

`update_settings_file` changes only the keys it's given and keeps every
other line, comments included. The dashboard's Settings page uses it; the
older writers in `interface/config/` rewrite the whole file.
"""

from pathlib import Path
from typing import Optional

from max_cli.common.atomic import atomic_write_text

SETTINGS_FILE_NAME = ".max_config.env"
# A value with one of these, or with spaces at either end, goes in quotes so
# the .env parser reads it back unchanged.
NEEDS_QUOTES = ('"', "'", "#")


def settings_file_path() -> Path:
    """Where settings are saved. Resolved per call, so tests can move home."""
    return Path.home() / SETTINGS_FILE_NAME


def _key(line: str) -> Optional[str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    return stripped.split("=", 1)[0].strip()


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        return (
            inner.replace('\\"', '"').replace("\\\\", "\\")
            if value[0] == '"'
            else inner
        )
    return value


def _quoted(value: str) -> str:
    if value != value.strip() or any(mark in value for mark in NEEDS_QUOTES):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def read_settings_file(path: Optional[Path] = None) -> dict[str, str]:
    """The keys and values saved in the settings file; empty when there's none."""
    path = path or settings_file_path()
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key = _key(line)
        if key:
            values[key] = _unquote(line.split("=", 1)[1])
    return values


def removed_settings_in_file(path: Optional[Path] = None) -> list[str]:
    """Settings the file still sets that Max no longer has (config.REMOVED_SETTINGS)."""
    from max_cli.config import REMOVED_SETTINGS

    saved = read_settings_file(path)
    return [name for name in REMOVED_SETTINGS if name in saved]


def update_settings_file(
    changes: dict[str, Optional[str]], path: Optional[Path] = None
) -> Path:
    """Set each key in `changes` to its value, or remove it when the value is None.

    Other lines stay as they are. A key saved twice keeps one line.
    """
    path = path or settings_file_path()
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    written: set[str] = set()
    kept: list[str] = []
    for line in lines:
        key = _key(line)
        if key not in changes:
            kept.append(line)
            continue
        value = changes[key]
        if value is None or key in written:
            continue
        kept.append(f"{key}={_quoted(value)}")
        written.add(key)
    for key, value in changes.items():
        if value is not None and key not in written:
            kept.append(f"{key}={_quoted(value)}")
    atomic_write_text(path, "\n".join(kept) + "\n")
    return path
