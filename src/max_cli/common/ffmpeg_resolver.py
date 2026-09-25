"""FFmpeg binary auto-resolution and download module."""

import logging
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

from max_cli.common.archives import safe_extract_tar
from max_cli.common.atomic import atomic_write_text
from max_cli.common.exceptions import ResourceNotFoundError

logger = logging.getLogger(__name__)

# Asked before downloading; gets a message and returns True to download.
ConfirmDownload = Callable[[str], bool]
# Called while downloading with (bytes so far, total bytes or None).
DownloadProgress = Callable[[int, Optional[int]], None]

DOWNLOAD_CHUNK_SIZE = 8192
DOWNLOAD_TIMEOUT_SECONDS = 120

MAX_CLI_BIN_DIR = Path.home() / ".max_cli" / "bin"
RESOLUTION_CACHE_FILE = Path.home() / ".max_cli" / ".ffmpeg_resolved_path"

FFMPEG_DOWNLOADS: dict[str, dict[str, object]] = {
    "Windows": {
        "url": "https://github.com/niutech/ffmpeg/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip",
        "binary_name": "ffmpeg.exe",
        "extract_path": "bin/ffmpeg.exe",
    },
    "Darwin": {
        "url": "https://evermeet.cx/ffmpeg/get/ffmpeg",
        "binary_name": "ffmpeg",
        "extract_path": None,
    },
    "Linux": {
        "url": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
        "binary_name": "ffmpeg",
        "extract_path": None,
    },
}


class FFmpegResolver:
    """Resolves FFmpeg binary path with auto-download fallback."""

    def __init__(self) -> None:
        self.system = platform.system()
        self.bin_dir = MAX_CLI_BIN_DIR
        self.binary_name = self._get_binary_name()
        self.local_path = self.bin_dir / self.binary_name

    def _get_binary_name(self) -> str:
        return "ffmpeg.exe" if self.system == "Windows" else "ffmpeg"

    def resolve(
        self,
        auto_download: bool = True,
        confirm_download: Optional[ConfirmDownload] = None,
        on_progress: Optional[DownloadProgress] = None,
    ) -> Path:
        """Find FFmpeg, downloading it when allowed.

        Downloading needs `confirm_download`, which the interface supplies
        (a prompt). Without it the resolver raises instead of asking.
        """
        cached = FFmpegResolver.get_cached_resolution()
        if cached:
            return cached

        system_path = shutil.which(self.binary_name)
        if system_path:
            resolved = Path(system_path)
            self._cache_resolution(resolved)
            return resolved

        if self.local_path.exists():
            if self._validate_binary(self.local_path):
                self._cache_resolution(self.local_path)
                return self.local_path
            self.local_path.unlink()

        if auto_download:
            return self._download_and_install(confirm_download, on_progress)

        raise ResourceNotFoundError(
            "FFmpeg not found. Install manually or run 'max config setup-ffmpeg'"
        )

    def _download_and_install(
        self,
        confirm_download: Optional[ConfirmDownload] = None,
        on_progress: Optional[DownloadProgress] = None,
    ) -> Path:
        if self.system not in FFMPEG_DOWNLOADS:
            raise ResourceNotFoundError(
                f"Unsupported platform for auto-download: {self.system}. "
                "Please install FFmpeg manually from https://ffmpeg.org/download.html"
            )

        if confirm_download is None or os.environ.get("MAX_CLI_NON_INTERACTIVE"):
            raise ResourceNotFoundError(
                "FFmpeg is required. Install it manually or run "
                "'max config setup-ffmpeg'."
            )

        question = (
            "FFmpeg is not installed. Max CLI can download a static FFmpeg "
            f"binary to {self.bin_dir} (~60-100MB). Download it now?"
        )
        if not confirm_download(question):
            raise ResourceNotFoundError(
                "FFmpeg download declined. Install manually:\n"
                "  Windows: https://www.gyan.dev/ffmpeg/builds/\n"
                "  macOS:   brew install ffmpeg\n"
                "  Linux:   sudo apt install ffmpeg"
            )

        self.bin_dir.mkdir(parents=True, exist_ok=True)

        try:
            download_info = FFMPEG_DOWNLOADS[self.system]
            extract_path = download_info.get("extract_path")
            self._download_binary(
                url=str(download_info["url"]),
                binary_name=self.binary_name,
                extract_path=str(extract_path) if extract_path else None,
                on_progress=on_progress,
            )
        except ResourceNotFoundError:
            raise
        except Exception as e:  # noqa: BLE001 - any failure means "install manually"
            logger.exception("FFmpeg download failed")
            if self.local_path.exists():
                self.local_path.unlink()
            raise ResourceNotFoundError(
                f"Failed to download FFmpeg: {e}\n"
                "Please install manually from https://ffmpeg.org/download.html"
            )

        if not self._validate_binary(self.local_path):
            self.local_path.unlink()
            raise ResourceNotFoundError(
                "Downloaded FFmpeg binary failed validation. Please install manually."
            )

        if self.system != "Windows":
            os.chmod(self.local_path, 0o755)

        self._cache_resolution(self.local_path)
        return self.local_path

    def _download_binary(
        self,
        url: str,
        binary_name: str,
        extract_path: Optional[str] = None,
        on_progress: Optional[DownloadProgress] = None,
    ) -> None:
        import tarfile
        import zipfile
        from urllib.request import Request, urlopen

        headers = {"User-Agent": "MaxCLI/1.0 (FFmpeg Auto-Resolver)"}
        request = Request(url, headers=headers)

        with urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            content_length = response.getheader("Content-Length")
            total_size = int(content_length) if content_length else None

            with tempfile.NamedTemporaryFile(
                dir=self.bin_dir,
                suffix=".download",
                delete=False,
            ) as tmp_file:
                downloaded = 0
                while True:
                    chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    tmp_file.write(chunk)
                    downloaded += len(chunk)
                    if on_progress:
                        on_progress(downloaded, total_size)
                tmp_path = Path(tmp_file.name)

        # Path.replace (not rename) so an existing, possibly corrupt binary is
        # overwritten; rename raises FileExistsError on Windows.
        suffixes = tuple(s for s in (extract_path, binary_name) if s)
        if url.endswith(".zip"):
            with zipfile.ZipFile(tmp_path, "r") as zf:
                for member_name in zf.namelist():
                    if member_name.endswith(suffixes):
                        # ZipFile.extract strips absolute paths and ".." itself.
                        extracted = Path(zf.extract(member_name, self.bin_dir))
                        if extracted != self.local_path:
                            extracted.replace(self.local_path)
                        break
        elif url.endswith(".tar.xz") or url.endswith(".tar.bz2"):
            with tarfile.open(tmp_path, "r:*") as tf:
                for tar_member in tf.getmembers():
                    if tar_member.name.endswith(binary_name):
                        safe_extract_tar(tf, self.bin_dir, members=[tar_member])
                        extracted = self.bin_dir / tar_member.name
                        if extracted != self.local_path:
                            extracted.replace(self.local_path)
                        break
        else:
            tmp_path.replace(self.local_path)

        if tmp_path.exists():
            tmp_path.unlink()

    def _validate_binary(self, path: Path) -> bool:
        try:
            result = subprocess.run(
                [str(path), "-version"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0 and b"ffmpeg" in result.stdout.lower()
        except (subprocess.TimeoutExpired, OSError, ValueError):
            return False

    def _cache_resolution(self, path: Path) -> None:
        atomic_write_text(RESOLUTION_CACHE_FILE, str(path))

    @staticmethod
    def get_cached_resolution() -> Optional[Path]:
        if not RESOLUTION_CACHE_FILE.exists():
            return None

        cached_path = Path(RESOLUTION_CACHE_FILE.read_text(encoding="utf-8").strip())
        if cached_path.exists():
            resolver = FFmpegResolver()
            if resolver._validate_binary(cached_path):
                return cached_path
            RESOLUTION_CACHE_FILE.unlink()

        return None


def resolve_ffmpeg(
    auto_download: bool = True,
    confirm_download: Optional[ConfirmDownload] = None,
    on_progress: Optional[DownloadProgress] = None,
) -> Path:
    cached = FFmpegResolver.get_cached_resolution()
    if cached:
        return cached

    resolver = FFmpegResolver()
    return resolver.resolve(
        auto_download=auto_download,
        confirm_download=confirm_download,
        on_progress=on_progress,
    )
