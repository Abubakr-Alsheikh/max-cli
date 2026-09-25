"""Terminal prompt and progress line for the FFmpeg auto-download.

The resolver in `common/ffmpeg_resolver.py` never talks to the user. CLI
commands pass these callbacks to `MediaEngine` or `resolve_ffmpeg`.
"""

from typing import Any, Optional

from max_cli.common.logger import console

BYTES_PER_MB = 1024 * 1024


def confirm_ffmpeg_download(question: str) -> bool:
    """Ask before downloading FFmpeg. Declines when no one can answer."""
    if not console.is_terminal:
        return False

    from rich.prompt import Confirm

    approved = Confirm.ask(f"[yellow]{question}[/yellow]", default=True)
    if approved:
        console.print("[cyan]Downloading FFmpeg...[/cyan]")
    return approved


def show_ffmpeg_progress(downloaded: int, total: Optional[int]) -> None:
    """Redraw one progress line while FFmpeg downloads."""
    progress = f"Downloading... {downloaded / BYTES_PER_MB:.1f}MB"
    if total:
        progress += f" / {total / BYTES_PER_MB:.1f}MB ({downloaded / total * 100:.0f}%)"
    console.print(f"\r[cyan]{progress}[/cyan]", end="")
    if total and downloaded >= total:
        console.print()


def ffmpeg_prompt_callbacks() -> dict[str, Any]:
    """Keyword arguments that let MediaEngine / resolve_ffmpeg ask the user."""
    return {
        "confirm_download": confirm_ffmpeg_download,
        "on_progress": show_ffmpeg_progress,
    }
