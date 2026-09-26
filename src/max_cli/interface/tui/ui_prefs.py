"""Small dashboard preferences that should survive a restart (the Download page's mode, folder)."""

import json
from pathlib import Path
from typing import Any

from max_cli.common.atomic import atomic_write_json

PREFS_FILE_NAME = "dashboard_prefs.json"


def _prefs_file() -> Path:
    return Path.home() / ".max_cli" / PREFS_FILE_NAME


def load_prefs() -> dict[str, Any]:
    try:
        data = json.loads(_prefs_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_pref(key: str, value: Any) -> None:
    prefs = load_prefs()
    prefs[key] = value
    path = _prefs_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, prefs)
