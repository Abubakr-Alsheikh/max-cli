"""`max doctor`: check Max's setup, one thing at a time, each with its fix.

Each check returns a `Check`: OK, a WARN for something that limits a
feature, a FAIL for something broken, or INFO. A check that itself breaks
reports that instead of stopping the rest. Nothing here changes anything.
"""

import platform
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

OK, INFO, WARN, FAIL = "ok", "info", "warn", "fail"
MIN_PYTHON = (3, 9)


@dataclass(frozen=True)
class Check:
    name: str
    state: str  # OK, INFO, WARN or FAIL
    detail: str
    fix: str = ""  # what to run or do; "" when nothing is needed


def _max_version(online: bool) -> Check:
    from max_cli.core.engines import updates

    status = updates.check(force=True) if online else updates.cached_status()
    method = updates.INSTALL_LABELS[updates.install_method()]
    if status.available:
        return Check(
            "Max",
            WARN,
            f"{status.current}, {method}. {status.latest} is out.",
            "max update",
        )
    if status.latest is None:
        return Check(
            "Max",
            INFO,
            f"{status.current}, {method}. Couldn't ask PyPI for "
            f"the newest: {status.error or 'not checked'}",
        )
    return Check("Max", OK, f"{status.current}, the newest, {method}.")


def _python() -> Check:
    version = platform.python_version()
    if sys.version_info[:2] < MIN_PYTHON:
        return Check(
            "Python",
            FAIL,
            f"{version} is too old; Max needs 3.9 or newer.",
            "Reinstall Max with uv, which brings its own Python: see the Start "
            "Here guide",
        )
    return Check("Python", OK, f"{version} ({sys.executable})")


def _ffmpeg() -> Check:
    from max_cli.core.engines.ffmpeg_base import FFmpegEngine

    try:
        path = FFmpegEngine(auto_resolve=False).ffmpeg_path
    except RuntimeError:
        return Check(
            "FFmpeg",
            WARN,
            "Not found. Video and audio commands need it; Max offers to get it "
            "the first time.",
            "max config setup-ffmpeg",
        )
    return Check("FFmpeg", OK, str(path))


def _ai() -> Check:
    from max_cli.core.engines.ai_providers import fallback_provider, main_provider

    main = main_provider()
    if not main.is_set_up():
        return Check(
            "AI",
            WARN,
            f"{main.label}: {main.missing()}. The AI agent and `max ai` need it.",
            "max config setup, or Settings in the dashboard",
        )
    fallback = fallback_provider()
    backup = f"; fallback {fallback.label}" if fallback else "; no fallback"
    return Check("AI", OK, f"{main.label}, model {main.model()}{backup}.")


def _transcripts() -> Check:
    from max_cli.config import settings

    if settings.GEMINI_API_KEY:
        return Check("Transcripts", OK, "A Gemini key is set for max audio transcribe.")
    return Check(
        "Transcripts",
        INFO,
        "No Gemini key: max audio transcribe needs one (free at "
        "aistudio.google.com/apikey).",
        "Add GEMINI_API_KEY on the dashboard's Settings page",
    )


def _youtube() -> Check:
    from max_cli.core.operations import grab

    status = grab.youtube_fix_status()
    if status.installed:
        return Check("YouTube", OK, "The YouTube fix (PO token provider) is installed.")
    if not status.deno_found:
        return Check(
            "YouTube",
            INFO,
            "Most downloads work. If YouTube answers HTTP 403, the fix needs Deno.",
            "Install Deno (winget install DenoLand.Deno), then max grab pot-setup",
        )
    return Check(
        "YouTube",
        INFO,
        "Most downloads work. If YouTube answers HTTP 403, install the fix.",
        "max grab pot-setup",
    )


def _writable(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=folder):
            return True
    except OSError:
        return False


def _folders() -> Check:
    from max_cli.config import settings

    data = Path.home() / ".max_cli"
    downloads = Path(settings.GRAB_DEFAULT_PATH)
    blocked = [str(folder) for folder in (data, downloads) if not _writable(folder)]
    if blocked:
        return Check(
            "Folders",
            FAIL,
            f"Max can't write to {', '.join(blocked)}.",
            "Pick another download folder in Settings, or check the folder's "
            "permissions",
        )
    return Check("Folders", OK, f"Data in {data}; downloads in {downloads}.")


def _settings_file() -> Check:
    from max_cli.common.settings_file import removed_settings_in_file

    stale = removed_settings_in_file()
    if stale:
        return Check(
            "Settings",
            WARN,
            f"Your settings file still sets {', '.join(stale)}, which Max no "
            "longer uses.",
            "Settings > Maintenance > Remove them, or max config validate",
        )
    return Check("Settings", OK, str(Path.home() / ".max_config.env"))


def _ocr() -> Check:
    if shutil.which("tesseract"):
        return Check("OCR", OK, "Tesseract is installed for max pdf ocr.")
    return Check(
        "OCR",
        INFO,
        "Tesseract isn't installed; only max pdf ocr needs it.",
        "Install Tesseract, then: uv tool install max-cli --with pytesseract "
        "(or pip install max-cli[ocr])",
    )


def checks(online: bool = True) -> list[tuple[str, Callable[[], Check]]]:
    """The checks, named, in the order `max doctor` shows them."""
    return [
        ("Max", lambda: _max_version(online)),
        ("Python", _python),
        ("FFmpeg", _ffmpeg),
        ("AI", _ai),
        ("Transcripts", _transcripts),
        ("YouTube", _youtube),
        ("Folders", _folders),
        ("Settings", _settings_file),
        ("OCR", _ocr),
    ]


def run(online: bool = True) -> list[Check]:
    """Every check's result. `online` asks PyPI for the newest Max."""
    results = []
    for name, check in checks(online):
        try:
            results.append(check())
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            results.append(Check(name, WARN, f"Couldn't check: {exc}"))
    return results
