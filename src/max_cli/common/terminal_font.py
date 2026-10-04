"""The Nerd Font that gives the dashboard its page icons.

A Nerd Font is a coding font with thousands of icons added. Max uses
CaskaydiaMono Nerd Font: Microsoft's Cascadia Mono (Windows Terminal's
default font) with the icons, from the Nerd Fonts project (SIL Open Font
License). `max config setup-font` downloads it, installs it for this user
only (no admin rights) and offers to make it Windows Terminal's font.

The dashboard turns its icons on when the terminal's font is a Nerd Font
(`terminal_has_nerd_font`, Windows Terminal only: other terminals don't say
which font they use). Elsewhere you pick "Nerd Font" on the Settings page.

Nothing here prompts or prints; the CLI asks first.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Optional

from max_cli.common.archives import safe_extract_tar
from max_cli.common.atomic import atomic_write_json
from max_cli.common.exceptions import ProcessingError

logger = logging.getLogger(__name__)

NERD_FONT_URL = (
    "https://github.com/ryanoasis/nerd-fonts/releases/latest/download/"
    "CascadiaMono.tar.xz"
)
NERD_FONT_SIZE_TEXT = "3.6 MB"
NERD_FONT_FACE = "CaskaydiaMono Nerd Font"
NERD_FONT_STYLES = ("Regular", "Bold", "Italic", "BoldItalic")
NERD_FONT_FILES = tuple(
    f"CaskaydiaMonoNerdFont-{style}.ttf" for style in NERD_FONT_STYLES
)
# A face name with one of these is a Nerd Font: "CaskaydiaMono Nerd Font",
# "Cascadia Code NF", "JetBrainsMono NFM".
NERD_FACE_MARKERS = ("nerd font", " nf", " nfm", " nfp")
DOWNLOAD_CHUNK_SIZE = 64 * 1024
USER_AGENT = "MaxCLI/1.0 (font setup)"
# Windows Terminal keeps its settings here (the Store app, its Preview, and
# the unpackaged build).
TERMINAL_PACKAGES = (
    "Microsoft.WindowsTerminal_8wekyb3d8bbwe",
    "Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe",
)
TERMINAL_BACKUP_SUFFIX = ".max-backup"
FONTS_REGISTRY_KEY = r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"
HWND_BROADCAST = 0xFFFF
WM_FONTCHANGE = 0x001D
BROADCAST_TIMEOUT_MS = 1000

DownloadProgress = Callable[[int, Optional[int]], None]


def user_font_dir() -> Path:
    """Where fonts go for this user alone."""
    if sys.platform == "win32":
        local = Path(
            os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        )
        return local / "Microsoft" / "Windows" / "Fonts"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Fonts"
    return Path.home() / ".local" / "share" / "fonts"


def font_installed() -> bool:
    folder = user_font_dir()
    return all((folder / name).exists() for name in NERD_FONT_FILES)


def download_font(
    work_dir: Path, on_progress: Optional[DownloadProgress] = None
) -> list[Path]:
    """Download the font archive and unpack its four styles into `work_dir`."""
    from urllib.error import URLError
    from urllib.request import Request, urlopen

    from max_cli.config import settings

    archive_path = work_dir / "font.tar.xz"
    try:
        request = Request(NERD_FONT_URL, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=settings.DOWNLOAD_TIMEOUT) as response:
            length = response.getheader("Content-Length")
            total = int(length) if length else None
            done = 0
            with archive_path.open("wb") as archive_file:
                while chunk := response.read(DOWNLOAD_CHUNK_SIZE):
                    archive_file.write(chunk)
                    done += len(chunk)
                    if on_progress is not None:
                        on_progress(done, total)
    except (URLError, OSError) as e:
        raise ProcessingError(f"Couldn't download the font: {e}") from e
    try:
        with tarfile.open(archive_path, "r:xz") as archive:
            wanted = [m for m in archive.getmembers() if m.name in NERD_FONT_FILES]
            if len(wanted) != len(NERD_FONT_FILES):
                raise ProcessingError(
                    "The font download doesn't hold the expected files."
                )
            safe_extract_tar(archive, work_dir, wanted)
    except (tarfile.TarError, EOFError) as e:
        raise ProcessingError(f"The font download is damaged: {e}") from e
    return [work_dir / name for name in NERD_FONT_FILES]


def install_font(files: list[Path]) -> Path:
    """Copy the font files into the user's font folder and tell the system.
    Returns the folder."""
    folder = user_font_dir()
    folder.mkdir(parents=True, exist_ok=True)
    installed = []
    for source in files:
        target = folder / source.name
        shutil.copy2(source, target)
        installed.append(target)
    if sys.platform == "win32":
        _register_on_windows(installed)
    elif sys.platform != "darwin":
        _refresh_font_cache()
    return folder


def _register_on_windows(files: list[Path]) -> None:
    """A per-user font is one registry value per file; programs started
    afterwards see it, and WM_FONTCHANGE tells the ones already running."""
    if sys.platform == "win32":  # mypy checks this only for Windows
        import ctypes
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, FONTS_REGISTRY_KEY) as key:
            for path, style in zip(files, NERD_FONT_STYLES):
                winreg.SetValueEx(
                    key,
                    f"{NERD_FONT_FACE} {style} (TrueType)",
                    0,
                    winreg.REG_SZ,
                    str(path),
                )
        for path in files:
            ctypes.windll.gdi32.AddFontResourceW(str(path))
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_FONTCHANGE, 0, 0, 0, BROADCAST_TIMEOUT_MS, None
        )


def _refresh_font_cache() -> None:
    fc_cache = shutil.which("fc-cache")
    if fc_cache is None:
        return
    result = subprocess.run([fc_cache, "-f"], capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning("fc-cache failed: %s", result.stderr.strip())


def setup_font(on_progress: Optional[DownloadProgress] = None) -> Path:
    """Download and install the font; returns the font folder."""
    with tempfile.TemporaryDirectory(prefix="max-font-") as work:
        files = download_font(Path(work), on_progress)
        return install_font(files)


# --- Windows Terminal ---------------------------------------------------------


def terminal_settings_path() -> Optional[Path]:
    """Windows Terminal's settings.json, when Windows Terminal is installed."""
    if sys.platform != "win32":
        return None
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    candidates = [
        local / "Packages" / package / "LocalState" / "settings.json"
        for package in TERMINAL_PACKAGES
    ]
    candidates.append(local / "Microsoft" / "Windows Terminal" / "settings.json")
    return next((path for path in candidates if path.exists()), None)


def _read_terminal_settings(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        # Windows Terminal allows comments; Max won't rewrite such a file.
        raise ProcessingError(
            "Windows Terminal's settings file has comments, so Max won't change "
            f"it. Set the font yourself: Settings > Defaults > Appearance > Font "
            f"face > {NERD_FONT_FACE}."
        ) from e
    if not isinstance(data, dict) or not isinstance(data.get("profiles", {}), dict):
        raise ProcessingError(
            "Windows Terminal's settings file has an older layout. Set the font "
            f"yourself: Settings > Defaults > Appearance > Font face > {NERD_FONT_FACE}."
        )
    return data


def terminal_font_face(path: Optional[Path] = None) -> str:
    """The font Windows Terminal's profiles use by default ("" for its own
    default, Cascadia Mono, or without Windows Terminal)."""
    path = path or terminal_settings_path()
    if path is None:
        return ""
    try:
        data = _read_terminal_settings(path)
    except (ProcessingError, OSError):
        return ""
    defaults = data.get("profiles", {}).get("defaults", {})
    font = defaults.get("font", {})
    face = font.get("face") if isinstance(font, dict) else None
    return str(face or defaults.get("fontFace") or "")


def is_nerd_face(face: str) -> bool:
    lowered = f" {face.lower()}"
    return any(marker in lowered for marker in NERD_FACE_MARKERS)


@lru_cache(maxsize=1)
def terminal_has_nerd_font() -> bool:
    """True inside Windows Terminal when its font is a Nerd Font. Read once."""
    if not os.environ.get("WT_SESSION"):
        return False
    return is_nerd_face(terminal_font_face())


def set_terminal_font(face: str = NERD_FONT_FACE, path: Optional[Path] = None) -> Path:
    """Make `face` the font of every Windows Terminal profile that doesn't
    choose its own. Keeps a copy of the file first; returns the copy.
    Windows Terminal picks up the change at once."""
    path = path or terminal_settings_path()
    if path is None:
        raise ProcessingError("Windows Terminal isn't installed.")
    data = _read_terminal_settings(path)
    backup = path.with_name(path.name + TERMINAL_BACKUP_SUFFIX)
    shutil.copy2(path, backup)
    defaults = data.setdefault("profiles", {}).setdefault("defaults", {})
    font = defaults.get("font")
    if not isinstance(font, dict):
        font = defaults["font"] = {}
    font["face"] = face
    defaults.pop("fontFace", None)  # the older spelling would win in some versions
    atomic_write_json(path, data, indent=4)
    terminal_has_nerd_font.cache_clear()
    return backup
