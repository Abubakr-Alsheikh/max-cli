"""FFmpeg binary auto-resolution and download module."""

import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from max_cli.common.exceptions import ResourceNotFoundError
from max_cli.common.logger import console, log_error, log_success

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

    def resolve(self, auto_download: bool = True) -> Path:
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
            return self._download_and_install()

        raise ResourceNotFoundError(
            "FFmpeg not found. Install manually or run 'max config setup-ffmpeg'"
        )

    def _download_and_install(self) -> Path:
        if self.system not in FFMPEG_DOWNLOADS:
            raise ResourceNotFoundError(
                f"Unsupported platform for auto-download: {self.system}. "
                "Please install FFmpeg manually from https://ffmpeg.org/download.html"
            )

        console.print("[yellow]FFmpeg is not installed.[/yellow]")
        console.print(
            f"[dim]Max CLI can automatically download a static FFmpeg binary "
            f"to {self.bin_dir} (~60-100MB).[/dim]"
        )

        if not console.is_terminal or os.environ.get("MAX_CLI_NON_INTERACTIVE"):
            raise ResourceNotFoundError(
                "FFmpeg is required. Install manually or set MAX_CLI_NON_INTERACTIVE=0 "
                "to enable interactive prompts."
            )

        from rich.prompt import Confirm

        if not Confirm.ask("Download FFmpeg automatically?", default=True):
            raise ResourceNotFoundError(
                "FFmpeg download declined. Install manually:\n"
                "  Windows: https://www.gyan.dev/ffmpeg/builds/\n"
                "  macOS:   brew install ffmpeg\n"
                "  Linux:   sudo apt install ffmpeg"
            )

        self.bin_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"[cyan]Downloading FFmpeg for {self.system}...[/cyan]")

        try:
            download_info = FFMPEG_DOWNLOADS[self.system]
            self._download_binary(
                url=download_info["url"],
                binary_name=self.binary_name,
                extract_path=download_info.get("extract_path"),
            )
        except ResourceNotFoundError:
            raise
        except Exception as e:
            log_error(f"FFmpeg download failed: {e}")
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
        log_success(f"FFmpeg installed to {self.local_path}")
        return self.local_path

    def _download_binary(
        self,
        url: str,
        binary_name: str,
        extract_path: Optional[str] = None,
    ) -> None:
        import tarfile
        import zipfile
        from urllib.request import Request, urlopen

        headers = {"User-Agent": "MaxCLI/1.0 (FFmpeg Auto-Resolver)"}
        request = Request(url, headers=headers)

        with urlopen(request, timeout=120) as response:
            total_size = response.getheader("Content-Length")
            total_size = int(total_size) if total_size else None

            with tempfile.NamedTemporaryFile(
                dir=self.bin_dir,
                suffix=".download",
                delete=False,
            ) as tmp_file:
                downloaded = 0
                chunk_size = 8192

                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    tmp_file.write(chunk)
                    downloaded += len(chunk)

                    if total_size:
                        pct = (downloaded / total_size) * 100
                        console.print(
                            f"\r[cyan]Downloading... {downloaded / 1024 / 1024:.1f}MB "
                            f"/ {total_size / 1024 / 1024:.1f}MB ({pct:.0f}%)[/cyan]",
                            end="",
                        )
                    else:
                        console.print(
                            f"\r[cyan]Downloading... {downloaded / 1024 / 1024:.1f}MB[/cyan]",
                            end="",
                        )

                console.print()
                tmp_path = Path(tmp_file.name)

        if url.endswith(".zip"):
            with zipfile.ZipFile(tmp_path, "r") as zf:
                for member in zf.namelist():
                    if member.endswith(extract_path) or member.endswith(binary_name):
                        zf.extract(member, self.bin_dir)
                        extracted = self.bin_dir / member
                        if extracted != self.local_path:
                            extracted.rename(self.local_path)
                        break
        elif url.endswith(".tar.xz") or url.endswith(".tar.bz2"):
            with tarfile.open(tmp_path, "r:*") as tf:
                for member in tf.getmembers():
                    if member.name.endswith(binary_name):
                        tf.extract(member, self.bin_dir)
                        extracted = self.bin_dir / member.name
                        if extracted != self.local_path:
                            extracted.rename(self.local_path)
                        break
        else:
            tmp_path.rename(self.local_path)

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
        RESOLUTION_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        RESOLUTION_CACHE_FILE.write_text(str(path))

    @staticmethod
    def get_cached_resolution() -> Optional[Path]:
        if not RESOLUTION_CACHE_FILE.exists():
            return None

        cached_path = Path(RESOLUTION_CACHE_FILE.read_text().strip())
        if cached_path.exists():
            resolver = FFmpegResolver()
            if resolver._validate_binary(cached_path):
                return cached_path
            RESOLUTION_CACHE_FILE.unlink()

        return None


def resolve_ffmpeg(auto_download: bool = True) -> Path:
    cached = FFmpegResolver.get_cached_resolution()
    if cached:
        return cached

    resolver = FFmpegResolver()
    return resolver.resolve(auto_download=auto_download)
