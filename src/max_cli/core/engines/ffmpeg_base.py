"""Shared FFmpeg plumbing for the video, audio and stream engines."""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from max_cli.common.ffmpeg_resolver import ConfirmDownload, DownloadProgress

logger = logging.getLogger(__name__)

FFPROBE_TIMEOUT_SECONDS = 15


class FFmpegEngine:
    """Resolves the FFmpeg binary and runs FFmpeg/ffprobe commands."""

    def __init__(
        self,
        auto_resolve: bool = True,
        confirm_download: Optional["ConfirmDownload"] = None,
        on_progress: Optional["DownloadProgress"] = None,
    ) -> None:
        self._confirm_download = confirm_download
        self._on_progress = on_progress
        self.ffmpeg_path: Path = self._resolve_ffmpeg(auto_resolve)

    def _resolve_ffmpeg(self, auto_resolve: bool) -> Path:
        system_path = shutil.which("ffmpeg")
        if system_path:
            return Path(system_path)

        from max_cli.common.ffmpeg_resolver import FFmpegResolver

        resolver = FFmpegResolver()
        if resolver.local_path.exists() and resolver._validate_binary(
            resolver.local_path
        ):
            return resolver.local_path

        if auto_resolve:
            from max_cli.common.ffmpeg_resolver import resolve_ffmpeg

            return resolve_ffmpeg(
                auto_download=True,
                confirm_download=self._confirm_download,
                on_progress=self._on_progress,
            )

        raise RuntimeError(
            "FFmpeg is not installed or not in PATH. "
            "Install it via: 'brew install ffmpeg', 'sudo apt install ffmpeg', or Download from ffmpeg.org"
        )

    def _run(self, cmd: List[str]):
        """Runs the subprocess command."""
        try:
            subprocess.run(
                cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode().strip()
            raise RuntimeError(f"FFmpeg Error: {error_msg}") from e

    def _get_duration(self, input_path: Path) -> Optional[float]:
        """Media duration in seconds, or None when ffprobe cannot tell.

        Duration only drives progress reporting, so a missing ffprobe must not
        fail the operation; it is logged instead of silently returning 0.0.
        """
        ffprobe_path = self.ffmpeg_path.with_name("ffprobe" + self.ffmpeg_path.suffix)
        if not ffprobe_path.is_file():
            ffprobe_path = Path(shutil.which("ffprobe") or ffprobe_path)
        cmd = [
            str(ffprobe_path),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=FFPROBE_TIMEOUT_SECONDS
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("Could not read duration of %s: %s", input_path, exc)
            return None
        if result.returncode != 0:
            logger.warning(
                "ffprobe could not read duration of %s: %s",
                input_path,
                (result.stderr or "").strip(),
            )
            return None
        try:
            return float(result.stdout.strip())
        except ValueError:
            logger.warning("ffprobe returned no numeric duration for %s", input_path)
            return None
