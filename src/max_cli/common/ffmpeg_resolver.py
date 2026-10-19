"""Find FFmpeg, or install it: through the system's package manager, else a
download checked against its published SHA-256.

Where Max looks: PATH, the places winget and Homebrew put it (a fresh
install isn't on this process's PATH yet), then ~/.max_cli/bin.

How Max installs it, after the interface's `confirm_download` says yes:
1. winget (Windows: Gyan's build) or Homebrew (macOS), when present. These
   check their own downloads, and antivirus tools know them.
2. Otherwise the first source in `ffmpeg_sources` that works: an archive
   (or one per program) whose SHA-256 must match the one its site publishes,
   unpacked into ~/.max_cli/bin with ffprobe beside ffmpeg (Max reads media
   facts with ffprobe).

Sources move: the old Windows link answered 404, evermeet.cx (macOS) shut its
API, and johnvansickle.com stopped answering, so every system has a fallback
and a failure names each source tried and the manual fix, never a traceback.
"""

import hashlib
import logging
import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Callable, Optional

from max_cli.common.atomic import atomic_write_text
from max_cli.common.exceptions import ResourceNotFoundError

logger = logging.getLogger(__name__)

# Asked before installing; gets a message and returns True to go ahead.
ConfirmDownload = Callable[[str], bool]
# Called while downloading with (bytes so far, total bytes or None).
DownloadProgress = Callable[[int, Optional[int]], None]

DOWNLOAD_CHUNK_SIZE = 8192
PACKAGE_MANAGER_TIMEOUT_SECONDS = 900
USER_AGENT = "MaxCLI (FFmpeg installer)"

MAX_CLI_BIN_DIR = Path.home() / ".max_cli" / "bin"
RESOLUTION_CACHE_FILE = Path.home() / ".max_cli" / ".ffmpeg_resolved_path"
# The agent runs actions side by side: one of them installs FFmpeg, the
# others wait for it.
_resolve_lock = threading.Lock()

SUPPORTED_SYSTEMS = ("Windows", "Darwin", "Linux")
ARM_MACHINES = frozenset({"arm64", "aarch64"})
GYAN = "https://www.gyan.dev/ffmpeg/builds"
BTBN = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest"
JOHNVANSICKLE = "https://johnvansickle.com/ffmpeg/releases"
MARTIN_RIEDL = "https://ffmpeg.martin-riedl.de"
# Release builds on Martin Riedl's page: /download/macos/arm64/<time>_9.0.2/
MARTIN_RIEDL_RELEASE = re.compile(
    r"/download/macos/(?P<arch>arm64|amd64)/(?P<time>\d+)_(?P<version>\d+(?:\.\d+)+)/"
)
# (package manager, its arguments after the program) per system.
PACKAGE_MANAGERS: dict[str, tuple[str, tuple[str, ...]]] = {
    "Windows": (
        "winget",
        (
            "install",
            "--id",
            "Gyan.FFmpeg",
            "--exact",
            "--accept-source-agreements",
            "--accept-package-agreements",
            "--disable-interactivity",
        ),
    ),
    "Darwin": ("brew", ("install", "ffmpeg")),
}
MANUAL_INSTALL = {
    "Windows": (
        "Install it yourself: winget install Gyan.FFmpeg, or download a build "
        f"from {GYAN}/ and put ffmpeg.exe and ffprobe.exe in {MAX_CLI_BIN_DIR}"
    ),
    "Darwin": "Install it yourself: brew install ffmpeg (Homebrew: https://brew.sh)",
    "Linux": "Install it yourself: sudo apt install ffmpeg (or your system's package manager)",
}


@dataclass(frozen=True)
class Download:
    """One file to fetch, and where its SHA-256 is published."""

    url: str
    checksum_url: str = ""  # "" when the source publishes none
    checksum_name: str = ""  # the line naming this file in a list of checksums


@dataclass(frozen=True)
class FFmpegSource:
    name: str  # shown when it fails: "gyan.dev"
    downloads: tuple[Download, ...]  # one archive, or one per program


def _windows_sources() -> list[FFmpegSource]:
    btbn = "ffmpeg-master-latest-win64-gpl.zip"
    return [
        FFmpegSource(
            "gyan.dev",
            (
                Download(
                    f"{GYAN}/ffmpeg-release-essentials.zip",
                    f"{GYAN}/ffmpeg-release-essentials.zip.sha256",
                ),
            ),
        ),
        FFmpegSource(
            "BtbN (GitHub)",
            (Download(f"{BTBN}/{btbn}", f"{BTBN}/checksums.sha256", btbn),),
        ),
    ]


def _linux_sources(arm: bool) -> list[FFmpegSource]:
    btbn = f"ffmpeg-master-latest-{'linuxarm64' if arm else 'linux64'}-gpl.tar.xz"
    static = f"ffmpeg-release-{'arm64' if arm else 'amd64'}-static.tar.xz"
    return [
        FFmpegSource(
            "BtbN (GitHub)",
            (Download(f"{BTBN}/{btbn}", f"{BTBN}/checksums.sha256", btbn),),
        ),
        FFmpegSource("johnvansickle.com", (Download(f"{JOHNVANSICKLE}/{static}"),)),
    ]


def _read_text(url: str) -> str:
    from urllib.request import Request, urlopen

    from max_cli.config import settings

    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=settings.DOWNLOAD_TIMEOUT) as response:
        return response.read().decode("utf-8", errors="replace")


def _macos_sources(arm: bool) -> list[FFmpegSource]:
    """Martin Riedl's newest release build for this Mac (ffmpeg.org's
    download page lists it). His page names the builds; there's no fixed
    "latest" link, so Max reads it."""
    from urllib.error import URLError

    arch = "arm64" if arm else "amd64"
    try:
        page = _read_text(f"{MARTIN_RIEDL}/")
    except (URLError, OSError) as exc:
        logger.warning("Couldn't read Martin Riedl's build list: %s", exc)
        return []
    builds = [
        match
        for match in MARTIN_RIEDL_RELEASE.finditer(page)
        if match.group("arch") == arch
    ]
    if not builds:
        return []
    newest = max(builds, key=lambda match: int(match.group("time")))
    folder = f"{MARTIN_RIEDL}{newest.group(0)}"
    return [
        FFmpegSource(
            f"Martin Riedl ({newest.group('version')})",
            tuple(
                Download(f"{folder}{name}.zip", f"{folder}{name}.zip.sha256")
                for name in ("ffmpeg", "ffprobe")
            ),
        )
    ]


def ffmpeg_sources(
    system: Optional[str] = None, machine: Optional[str] = None
) -> list[FFmpegSource]:
    """Where to download FFmpeg from on this system, best first."""
    system = system or platform.system()
    arm = (machine or platform.machine()).lower() in ARM_MACHINES
    if system == "Windows":
        return _windows_sources()
    if system == "Linux":
        return _linux_sources(arm)
    if system == "Darwin":
        return _macos_sources(arm)
    return []


def _expected_checksum(download: Download) -> Optional[str]:
    """The SHA-256 the source publishes for `download`; None when it has none."""
    if not download.checksum_url:
        return None
    text = _read_text(download.checksum_url)
    for line in text.splitlines():
        words = line.split()
        if words and (not download.checksum_name or download.checksum_name in line):
            return words[0].lower()
    raise ValueError(f"no checksum for {download.checksum_name or download.url}")


class FFmpegResolver:
    """Finds FFmpeg, and installs it when allowed."""

    def __init__(self) -> None:
        self.system = platform.system()
        self.bin_dir = MAX_CLI_BIN_DIR
        self.binary_name = self._get_binary_name()
        self.local_path = self.bin_dir / self.binary_name

    def _get_binary_name(self) -> str:
        return "ffmpeg.exe" if self.system == "Windows" else "ffmpeg"

    def _probe_name(self) -> str:
        return "ffprobe.exe" if self.system == "Windows" else "ffprobe"

    def known_locations(self) -> list[Path]:
        """Where winget and Homebrew put FFmpeg, for a process started before
        the install changed PATH."""
        if self.system == "Windows":
            local = Path(
                os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local"
            )
            winget = local / "Microsoft" / "WinGet"
            return [
                winget / "Links" / self.binary_name,
                *sorted(
                    (winget / "Packages").glob(f"Gyan.FFmpeg*/*/bin/{self.binary_name}")
                ),
            ]
        if self.system == "Darwin":
            return [Path("/opt/homebrew/bin/ffmpeg"), Path("/usr/local/bin/ffmpeg")]
        return []

    def find_installed(self) -> Optional[Path]:
        """FFmpeg already on this computer: PATH, a package manager's place,
        or a working copy in ~/.max_cli/bin. A broken copy there is removed."""
        on_path = shutil.which(self.binary_name)
        if on_path:
            return Path(on_path)
        for candidate in self.known_locations():
            if candidate.is_file() and self._validate_binary(candidate):
                return candidate
        if self.local_path.exists():
            if self._validate_binary(self.local_path):
                return self.local_path
            self.local_path.unlink()
        return None

    def resolve(
        self,
        auto_download: bool = True,
        confirm_download: Optional[ConfirmDownload] = None,
        on_progress: Optional[DownloadProgress] = None,
    ) -> Path:
        """Find FFmpeg, installing it when allowed.

        Installing needs `confirm_download`, which the interface supplies
        (a prompt). Without it the resolver raises instead of asking.
        """
        cached = FFmpegResolver.get_cached_resolution()
        if cached:
            return cached

        found = self.find_installed()
        if found:
            self._cache_resolution(found)
            return found

        if auto_download:
            return self._download_and_install(confirm_download, on_progress)

        raise ResourceNotFoundError(
            "FFmpeg not found. Install manually or run 'max config setup-ffmpeg'"
        )

    def _package_manager(self) -> Optional[list[str]]:
        entry = PACKAGE_MANAGERS.get(self.system)
        if entry is None:
            return None
        program, arguments = entry
        found = shutil.which(program)
        return [found, *arguments] if found else None

    def _question(self, manager: Optional[list[str]]) -> str:
        if manager:
            name = Path(manager[0]).stem
            return (
                f"FFmpeg isn't installed. Max can install it with {name}, your "
                "system's package manager (about 100 MB). Install it now?"
            )
        return (
            "FFmpeg isn't installed. Max can download it into "
            f"{self.bin_dir} (about 100 MB) and check it against the checksum "
            "its site publishes. Download it now?"
        )

    def _download_and_install(
        self,
        confirm_download: Optional[ConfirmDownload] = None,
        on_progress: Optional[DownloadProgress] = None,
    ) -> Path:
        if self.system not in SUPPORTED_SYSTEMS:
            raise ResourceNotFoundError(
                f"Unsupported platform for auto-download: {self.system}. "
                "Please install FFmpeg manually from https://ffmpeg.org/download.html"
            )

        if confirm_download is None or os.environ.get("MAX_CLI_NON_INTERACTIVE"):
            raise ResourceNotFoundError(
                "FFmpeg is required. Install it manually or run "
                "'max config setup-ffmpeg'."
            )

        manager = self._package_manager()
        if not confirm_download(self._question(manager)):
            raise ResourceNotFoundError(
                f"FFmpeg download declined. {MANUAL_INSTALL[self.system]}"
            )

        failures: list[str] = []
        if manager:
            installed = self._install_with(manager)
            if installed:
                self._cache_resolution(installed)
                return installed
            failures.append(f"{Path(manager[0]).stem} didn't install it")

        self.bin_dir.mkdir(parents=True, exist_ok=True)
        for source in ffmpeg_sources(self.system):
            try:
                for download in source.downloads:
                    self._download_binary(
                        download.url,
                        self.binary_name,
                        on_progress=on_progress,
                        sha256=_expected_checksum(download),
                    )
            except (OSError, ValueError, RuntimeError) as exc:
                # OSError covers URLError, HTTPError and timeouts.
                logger.warning("FFmpeg from %s failed: %s", source.name, exc)
                failures.append(f"{source.name}: {exc}")
                continue
            if self._validate_binary(self.local_path):
                if self.system != "Windows":
                    for program in (self.local_path, self.bin_dir / self._probe_name()):
                        if program.exists():
                            os.chmod(program, 0o755)
                self._cache_resolution(self.local_path)
                return self.local_path
            failures.append(f"{source.name}: the program didn't start")
            self.local_path.unlink(missing_ok=True)

        tried = "; ".join(failures) or "no download source for this system"
        raise ResourceNotFoundError(
            f"Couldn't install FFmpeg ({tried}). {MANUAL_INSTALL[self.system]}"
        )

    def _install_with(self, manager: list[str]) -> Optional[Path]:
        """Run the package manager in this terminal; the FFmpeg it installed,
        or None when it failed."""
        try:
            finished = subprocess.run(
                manager, check=False, timeout=PACKAGE_MANAGER_TIMEOUT_SECONDS
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("%s failed: %s", manager[0], exc)
            return None
        if finished.returncode != 0:
            logger.warning("%s exited with %s", manager[0], finished.returncode)
            return None
        return self.find_installed()

    def _download_binary(
        self,
        url: str,
        binary_name: str,
        on_progress: Optional[DownloadProgress] = None,
        sha256: Optional[str] = None,
    ) -> None:
        """Fetch `url` into bin_dir: an archive gives its ffmpeg and ffprobe,
        anything else is saved as `binary_name`. A `sha256` that doesn't
        match the download raises ValueError and keeps nothing."""
        import tarfile
        import zipfile
        from urllib.request import Request, urlopen

        from max_cli.config import settings

        request = Request(url, headers={"User-Agent": USER_AGENT})
        digest = hashlib.sha256()
        with urlopen(request, timeout=settings.DOWNLOAD_TIMEOUT) as response:
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
                    digest.update(chunk)
                    downloaded += len(chunk)
                    if on_progress:
                        on_progress(downloaded, total_size)
                tmp_path = Path(tmp_file.name)

        try:
            if sha256 and digest.hexdigest() != sha256:
                raise ValueError(
                    "the download doesn't match the checksum its site publishes"
                )
            # Copy each program out under its own name: no folders from the
            # archive land in bin_dir, and a member's path can't point
            # outside it. Path.replace overwrites a broken copy, which
            # rename refuses on Windows.
            wanted = {binary_name, self._probe_name()}
            if url.endswith(".zip"):
                with zipfile.ZipFile(tmp_path, "r") as zf:
                    for member_name in zf.namelist():
                        name = Path(member_name).name
                        if name in wanted:
                            with zf.open(member_name) as packed:
                                self._place(packed, name)
            elif url.endswith(".tar.xz") or url.endswith(".tar.bz2"):
                with tarfile.open(tmp_path, "r:*") as tf:
                    for tar_member in tf.getmembers():
                        name = Path(tar_member.name).name
                        packed_file = tf.extractfile(tar_member)
                        if name in wanted and tar_member.isfile() and packed_file:
                            with packed_file:
                                self._place(packed_file, name)
            else:
                tmp_path.replace(self.local_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def _place(self, packed: IO[bytes], name: str) -> None:
        """Write one program from an archive to bin_dir/name, atomically."""
        with tempfile.NamedTemporaryFile(
            dir=self.bin_dir, suffix=".part", delete=False
        ) as part:
            shutil.copyfileobj(packed, part)
        Path(part.name).replace(self.bin_dir / name)

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
    with _resolve_lock:
        cached = FFmpegResolver.get_cached_resolution()
        if cached:
            return cached

        resolver = FFmpegResolver()
        return resolver.resolve(
            auto_download=auto_download,
            confirm_download=confirm_download,
            on_progress=on_progress,
        )
