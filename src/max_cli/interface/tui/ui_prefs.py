"""Small dashboard preferences that should survive a restart (the Download page's mode, folder)."""

import json
from pathlib import Path
from typing import Any

from max_cli.common.atomic import atomic_write_json
from max_cli.common.retry import retry

PREFS_FILE_NAME = "dashboard_prefs.json"
# The folder last picked on the Download page.
DOWNLOAD_FOLDER_PREF = "download_folder"


def _prefs_file() -> Path:
    return Path.home() / ".max_cli" / PREFS_FILE_NAME


def load_prefs() -> dict[str, Any]:
    try:
        data = json.loads(_prefs_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


# Windows refuses to replace a file another process holds open for a moment
# (an antivirus scan, a search indexer); a short wait usually clears it.
WRITE_ATTEMPTS = 3
WRITE_RETRY_SECONDS = 0.05


@retry(
    max_attempts=WRITE_ATTEMPTS,
    delay=WRITE_RETRY_SECONDS,
    exceptions=(PermissionError,),
)
def _write(prefs: dict[str, Any]) -> None:
    path = _prefs_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, prefs)


def save_pref(key: str, value: Any) -> None:
    """Remember `value` under `key`. A file Windows keeps locked past the
    retries skips this save: these are conveniences, and raising here closed
    the dashboard on a page change (it failed a Windows CI run)."""
    prefs = load_prefs()
    prefs[key] = value
    try:
        _write(prefs)
    except PermissionError:
        return


def download_folder() -> Path:
    """Where the Download page saves: the folder picked there last, else the
    Save to setting (GRAB_DEFAULT_PATH)."""
    from max_cli.config import settings

    saved = load_prefs().get(DOWNLOAD_FOLDER_PREF)
    if isinstance(saved, str) and saved.strip():
        return Path(saved.strip()).expanduser()
    return Path(settings.GRAB_DEFAULT_PATH).expanduser()
