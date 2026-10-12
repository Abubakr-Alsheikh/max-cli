"""Is a newer Max out, how was this one installed, and how to update it.

PyPI's JSON says the latest version. Max asks at most once a day
(`CHECK_EVERY`) and keeps the answer in ~/.max_cli/update_check.json, so the
notice after a command and the dashboard's never wait on the network.
`UPDATE_CHECK` off stops the checks.

Updating replaces the files Max runs from. On Windows a running program's
files are locked: uv failed with "Access is denied" halfway through and left
an install that couldn't import max_cli. So on Windows `hand_off` opens a
small PowerShell window that waits for this Max to close, then updates;
elsewhere `run_update` updates in place.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PACKAGE = "max-cli"
PYPI_URL = f"https://pypi.org/pypi/{PACKAGE}/json"
CHECK_EVERY = timedelta(hours=24)
CHECK_TIMEOUT_SECONDS = 4
STATE_NAME = "update_check.json"
# "1.10.2" -> (1, 10, 2). Pre-releases ("1.2.0rc1") never count as newer.
RELEASE_VERSION = re.compile(r"^\d+(?:\.\d+)*$")

UV, PIPX, PIP, SOURCE = "uv", "pipx", "pip", "source"
# uv-receipt.toml's inline tables: { name = "pytesseract", specifier = ">=0.3" }.
RECEIPT_TABLE = re.compile(r"\{[^{}]*\}")
RECEIPT_NAME = re.compile(r'\bname\s*=\s*"([^"]+)"')
RECEIPT_SPECIFIER = re.compile(r'\bspecifier\s*=\s*"([^"]+)"')
RECEIPT_EXTRAS = re.compile(r"\bextras\s*=\s*\[([^\]]*)\]")
QUOTED = re.compile(r'"([^"]+)"')
# Files a tool installer leaves in the environment it made for Max.
UV_RECEIPT = "uv-receipt.toml"
PIPX_METADATA = "pipx_metadata.json"
# How each install reads in a sentence: "1.1.0, installed with uv".
INSTALL_LABELS = {
    UV: "installed with uv",
    PIPX: "installed with pipx",
    PIP: "installed with pip",
    SOURCE: "run from a source folder",
}
SOURCE_UPDATE_HINT = (
    "Max runs from a source folder: run git pull there, then pip install -e ."
)


def current_version() -> str:
    from importlib import metadata

    try:
        return metadata.version(PACKAGE)
    except metadata.PackageNotFoundError:
        return "0"


def version_key(text: str) -> Optional[tuple[int, ...]]:
    """(1, 10, 2) for "1.10.2"; None for a pre-release or nonsense."""
    text = (text or "").strip()
    if not RELEASE_VERSION.match(text):
        return None
    return tuple(int(part) for part in text.split("."))


def is_newer(latest: Optional[str], current: str) -> bool:
    latest_key, current_key = version_key(latest or ""), version_key(current)
    if latest_key is None or current_key is None:
        return False
    width = max(len(latest_key), len(current_key))
    return latest_key + (0,) * (width - len(latest_key)) > current_key + (0,) * (
        width - len(current_key)
    )


@dataclass
class UpdateStatus:
    current: str
    latest: Optional[str] = None  # None until a check succeeds
    checked_at: Optional[datetime] = None
    error: str = ""  # why the last check failed

    @property
    def available(self) -> bool:
        return is_newer(self.latest, self.current)


def _state_file() -> Path:
    return Path.home() / ".max_cli" / STATE_NAME


def cached_status() -> UpdateStatus:
    """What the last check found, without the network."""
    status = UpdateStatus(current_version())
    try:
        saved = json.loads(_state_file().read_text(encoding="utf-8"))
        status.latest = saved.get("latest") or None
        status.checked_at = datetime.fromisoformat(saved["checked_at"])
    except (OSError, ValueError, KeyError, TypeError):
        pass  # never checked, or an unreadable file: the next check rewrites it
    return status


def check_due(status: Optional[UpdateStatus] = None) -> bool:
    status = status or cached_status()
    return status.checked_at is None or datetime.now() - status.checked_at > CHECK_EVERY


def fetch_latest(timeout: float = CHECK_TIMEOUT_SECONDS) -> str:
    """The newest version on PyPI. Raises NetworkError when PyPI can't say."""
    import requests

    from max_cli.common.exceptions import NetworkError

    try:
        response = requests.get(PYPI_URL, timeout=timeout)
        response.raise_for_status()
        return str(response.json()["info"]["version"])
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise NetworkError(f"Couldn't ask PyPI for the latest Max: {exc}") from exc


def check(force: bool = False) -> UpdateStatus:
    """Ask PyPI when a day has passed since the last answer (or `force`),
    save the answer, and return the status. Never raises: a failed check
    keeps the last answer and says why in `error`."""
    from max_cli.common.atomic import atomic_write_json
    from max_cli.common.exceptions import NetworkError

    status = cached_status()
    if not force and not check_due(status):
        return status
    try:
        status.latest = fetch_latest()
    except NetworkError as exc:
        status.error = str(exc)
        return status
    status.checked_at = datetime.now()
    try:
        atomic_write_json(
            _state_file(),
            {"latest": status.latest, "checked_at": status.checked_at.isoformat()},
        )
    except OSError as exc:
        logger.warning("Couldn't save the update check: %s", exc)
    return status


# --- how Max was installed, and how to update it -------------------------------


def _is_editable() -> bool:
    from importlib import metadata

    try:
        # Distribution.read_text(name) reads package metadata, which is
        # always utf-8; it takes no encoding argument.
        read_metadata = metadata.distribution(PACKAGE).read_text
        direct_url = read_metadata("direct_url.json")
    except metadata.PackageNotFoundError:
        return True  # running from a source tree without installing
    try:
        return bool(json.loads(direct_url or "{}").get("dir_info", {}).get("editable"))
    except ValueError:
        return False


def install_method(prefix: Optional[Path] = None) -> str:
    """uv, pipx, pip or source: how this Max was installed."""
    if _is_editable():
        return SOURCE
    environment = Path(prefix or sys.prefix)
    if (environment / UV_RECEIPT).is_file():
        return UV
    if (environment / PIPX_METADATA).is_file():
        return PIPX
    return PIP


def uv_requirements(prefix: Optional[Path] = None) -> tuple[str, list[str]]:
    """Max's own requirement ("max-cli" or "max-cli[ocr]", never a pinned
    version) and the packages added with --with, from uv's receipt."""
    try:
        receipt = (Path(prefix or sys.prefix) / UV_RECEIPT).read_text(encoding="utf-8")
    except OSError:
        return PACKAGE, []
    own, added = PACKAGE, []
    for table in RECEIPT_TABLE.findall(receipt):
        name = RECEIPT_NAME.search(table)
        if not name or "install-path" in table:
            continue  # an entrypoint, not a requirement
        if name.group(1) == PACKAGE:
            extras = RECEIPT_EXTRAS.search(table)
            if extras:
                names = QUOTED.findall(extras.group(1))
                own = f"{PACKAGE}[{','.join(names)}]"
            continue
        specifier = RECEIPT_SPECIFIER.search(table)
        added.append(name.group(1) + (specifier.group(1) if specifier else ""))
    return own, added


def update_command(method: str) -> Optional[list[str]]:
    """The command that updates Max; None for a source install (git pull).

    uv: `tool install --upgrade` with the receipt's extras and --with
    packages. `uv tool upgrade` stops at a version the install pinned, and
    `install --upgrade` alone drops the --with packages (tried both).
    """
    if method == UV:
        own, added = uv_requirements()
        command = [shutil.which("uv") or "uv", "tool", "install", "--upgrade", own]
        for package in added:
            command += ["--with", package]
        return command
    if method == PIPX:
        return [shutil.which("pipx") or "pipx", "upgrade", PACKAGE]
    if method == PIP:
        return [sys.executable, "-m", "pip", "install", "--upgrade", PACKAGE]
    return None


def needs_hand_off() -> bool:
    """Windows locks a running program's files: update after Max closes."""
    return sys.platform == "win32"


def run_update(command: list[str]) -> int:
    """Update in place, showing the installer's own output. Returns its exit code."""
    return subprocess.run(command, check=False).returncode


def _powershell_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def hand_off_script(command: list[str], wait_for: list[int]) -> str:
    """PowerShell that waits for Max's processes to end, updates, and says
    how it went before the window closes."""
    program, *arguments = command
    call = " ".join(
        ["&", _powershell_quote(program), *map(_powershell_quote, arguments)]
    )
    pids = ",".join(str(pid) for pid in wait_for)
    return "; ".join(
        [
            "$host.UI.RawUI.WindowTitle = 'Updating Max'",
            "Write-Host 'Waiting for Max to close...' -ForegroundColor Cyan",
            f"Wait-Process -Id {pids} -ErrorAction SilentlyContinue",
            call,
            "if ($LASTEXITCODE -eq 0) { Write-Host 'Max is up to date. Open a new "
            "terminal and type: max' -ForegroundColor Green } else { Write-Host "
            "'The update failed. Close every Max window and run: max update' "
            "-ForegroundColor Red }",
            "Read-Host 'Press Enter to close this window'",
        ]
    )


def hand_off(command: list[str]) -> None:
    """Open a window that updates Max once this Max (and the launcher that
    started it, which holds max.exe) has closed."""
    powershell = shutil.which("powershell") or "powershell"
    script = hand_off_script(command, [os.getpid(), os.getppid()])
    subprocess.Popen(  # noqa: S603 - a list of arguments, no shell
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        close_fds=True,
    )
