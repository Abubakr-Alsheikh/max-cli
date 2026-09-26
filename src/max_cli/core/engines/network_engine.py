import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional, Union

QUALITY_MAP: dict[str, dict[str, Union[str, int]]] = {
    "ss": {"height": 360, "bitrate": 64, "label": "360p"},
    "s": {"height": 480, "bitrate": 64, "label": "480p"},
    "m": {"height": 720, "bitrate": 128, "label": "720p"},
    "h": {"height": 1080, "bitrate": 192, "label": "1080p"},
    "x": {"height": 2160, "bitrate": 320, "label": "4K"},
}

DEFAULT_DOWNLOAD_DIR = Path.home() / "Max Downloads"
POT_PROVIDER_PACKAGE = "bgutil-ytdlp-pot-provider"
POT_TIMEOUT_ATTEMPTS = 2
POT_TIMEOUT_MESSAGE = (
    "The YouTube token helper (bgutil POT provider) didn't answer in time. "
    "Try again; it's often slow on its first start. If it keeps failing, run "
    "`max grab pot-setup` or pick another player client in Advanced mode."
)
POT_PROVIDER_VERSION = "1.3.1"
POT_SERVER_DIR = Path.home() / "bgutil-ytdlp-pot-provider"
POT_SERVER_URL = (
    "https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git"
)
CANVAS_MIRROR_URL = (
    "https://registry.npmmirror.com/-/binary/canvas/v3.2.1/"
    "canvas-v3.2.1-napi-v7-win32-x64.tar.gz"
)


class NetworkEngine:
    """
    Advanced Media Downloader with Playlist and Metadata controls.
    """

    def __init__(self):
        self.has_js = any(
            shutil.which(cmd) for cmd in ["node", "deno", "cjs", "quickjs"]
        )

    def pot_provider_available(self) -> bool:
        """Check if a PO token provider plugin is registered with yt-dlp."""
        import yt_dlp  # type: ignore[import-untyped]

        yt_dlp.YoutubeDL({"quiet": True})
        from yt_dlp.extractor.youtube.pot._registry import (  # type: ignore[import-untyped]  # private yt-dlp module, no stubs
            _pot_providers,
        )

        return bool(_pot_providers.value)

    def _run_command(
        self, args: list, cwd: Optional[Path] = None, timeout: int = 600
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def install_pot_provider(self) -> dict[str, Any]:
        """Install the bgutil POT provider plugin via pip."""
        result = self._run_command(
            [shutil.which("pip") or "pip", "install", "-U", POT_PROVIDER_PACKAGE],
            timeout=900,
        )
        return {
            "ok": result.returncode == 0,
            "output": (result.stdout + result.stderr).strip(),
        }

    def setup_pot_server(self) -> dict[str, Any]:
        """Clone the bgutil server repo and install its Deno dependencies."""
        deno = shutil.which("deno")
        if not deno:
            return {"ok": False, "output": "Deno not found. Install it first."}

        steps: list[str] = []
        if not POT_SERVER_DIR.exists():
            steps.append("Cloning bgutil-ytdlp-pot-provider repository...")
            result = self._run_command(
                [
                    "git",
                    "clone",
                    "--single-branch",
                    "--branch",
                    POT_PROVIDER_VERSION,
                    "--depth",
                    "1",
                    POT_SERVER_URL,
                    str(POT_SERVER_DIR),
                ],
                timeout=900,
            )
            if result.returncode != 0:
                return {
                    "ok": False,
                    "output": (result.stdout + result.stderr).strip(),
                }
        else:
            steps.append("Using existing bgutil-ytdlp-pot-provider repository.")

        server_dir = POT_SERVER_DIR / "server"
        steps.append("Installing Deno dependencies (may take a few minutes)...")
        result = self._run_command(
            [
                deno,
                "install",
                "--allow-scripts=npm:canvas",
                "--frozen",
            ],
            cwd=server_dir,
            timeout=1800,
        )
        if result.returncode != 0:
            return {
                "ok": False,
                "output": (result.stdout + result.stderr).strip(),
            }

        canvas_fixed = self._ensure_canvas_binary(server_dir)
        if canvas_fixed:
            steps.append("Downloaded canvas native binary (GitHub mirror fallback).")

        return {"ok": True, "output": "\n".join(steps)}

    def _ensure_canvas_binary(self, server_dir: Path) -> bool:
        """Ensure the canvas native binary exists; download from mirror if missing."""
        canvas_pkgs = sorted(
            server_dir.glob("node_modules/.deno/canvas@*/node_modules/canvas")
        )
        if not canvas_pkgs:
            return False
        canvas_pkg = canvas_pkgs[-1]
        if (canvas_pkg / "build" / "Release" / "canvas.node").exists():
            return False

        from max_cli.common.archives import UnsafeArchiveError, safe_extract_tar

        with tempfile.TemporaryDirectory() as tmp:
            tarball = Path(tmp) / "canvas.tar.gz"
            try:
                urllib.request.urlretrieve(CANVAS_MIRROR_URL, tarball)
                with tarfile.open(tarball, "r:gz") as archive:
                    safe_extract_tar(archive, canvas_pkg)
                return (canvas_pkg / "build" / "Release" / "canvas.node").exists()
            except (OSError, tarfile.TarError, UnsafeArchiveError):
                return False

    def get_info(self, url: str) -> dict[str, Any]:
        """Peeks at the URL to see if it's a playlist and count items."""
        import yt_dlp

        ydl_opts = {"quiet": True, "noplaylist": False, "extract_flat": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    def probe_info(self, url: str) -> dict[str, Any]:
        """Full info for a video, or a playlist with its items listed but not resolved.

        The YouTube token helper (bgutil POT provider) often needs longer than
        its 15-second limit on its first start, so a timeout gets one retry.
        """
        import yt_dlp

        ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist"}
        for attempt in range(POT_TIMEOUT_ATTEMPTS):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    return ydl.extract_info(url, download=False) or {}
                except subprocess.TimeoutExpired as e:
                    if attempt + 1 == POT_TIMEOUT_ATTEMPTS:
                        raise RuntimeError(POT_TIMEOUT_MESSAGE) from e
                except yt_dlp.utils.DownloadError as e:
                    msg = str(e).replace("ERROR: ", "")
                    raise RuntimeError(f"Couldn't read the link: {msg}") from e
        return {}

    def get_quality_info(
        self, quality: str, custom_height: Optional[int] = None
    ) -> dict[str, Any]:
        """Get quality information based on quality code or custom height."""
        if custom_height:
            return {
                "height": custom_height,
                "bitrate": max(32, custom_height // 10),
                "label": f"{custom_height}p",
            }

        if quality.lower() == "ss":
            return QUALITY_MAP["ss"]

        q = quality.lower()[0]
        return QUALITY_MAP.get(q, QUALITY_MAP["m"])

    def download_media(
        self,
        url: str,
        output_path: Path,
        quality: str = "h",
        audio_only: bool = False,
        include_metadata: bool = True,
        playlist_items: Optional[str] = None,
        no_playlist: bool = False,
        progress_hook: Optional[Callable] = None,
        subtitles: bool = False,
        custom_height: Optional[int] = None,
        player_client: Optional[str] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> dict[str, Any]:
        """Download `url` into `output_path`.

        Returns the output folder and `files`, the final paths on disk (after
        merging and audio extraction). `should_cancel` is polled on every
        progress update; when it returns True the download stops, partial
        files are removed and OperationCancelled is raised.
        """
        import yt_dlp

        from max_cli.common.events import (
            DownloadCompleteEvent,
            DownloadProgressEvent,
            get_emitter,
        )
        from max_cli.common.exceptions import OperationCancelled

        q = quality.lower()[0]

        quality_info = self.get_quality_info(quality, custom_height)
        vid_height = quality_info["height"]
        audio_bitrate = quality_info["bitrate"]

        emitter = get_emitter()
        # Final path per video: the progress hook reports each downloaded
        # file, and post-processors (merge, extract audio) report the renamed
        # result, which replaces it.
        final_paths: dict[str, str] = {}
        partial_paths: set[str] = set()

        def _yt_dlp_hook(d: dict) -> None:
            status = d.get("status")
            filename = d.get("filename") or ""
            if filename:
                partial_paths.add(filename)
            # Checked after recording the file, so a cancel can clean it up.
            if should_cancel is not None and should_cancel():
                raise yt_dlp.utils.DownloadCancelled("Cancelled by user")
            if status == "finished" and filename:
                video_id = (d.get("info_dict") or {}).get("id") or filename
                final_paths.setdefault(video_id, filename)
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                downloaded = d.get("downloaded_bytes", 0)
                pct = (downloaded / total * 100) if total > 0 else 0.0
                raw_speed = d.get("speed")
                raw_eta = d.get("eta")
                emitter.emit(
                    DownloadProgressEvent(
                        url=url,
                        filename=d.get("filename", ""),
                        downloaded_bytes=downloaded,
                        total_bytes=total,
                        speed=float(raw_speed) if raw_speed is not None else 0.0,
                        eta=int(raw_eta) if raw_eta is not None else 0,
                        percentage=pct,
                    )
                )
            elif status == "finished":
                total = d.get("total_bytes", 0)
                emitter.emit(
                    DownloadCompleteEvent(
                        url=url,
                        filename=d.get("filename", ""),
                        total_bytes=total,
                    )
                )

        def _postprocessor_hook(d: dict) -> None:
            info = d.get("info_dict") or {}
            if d.get("status") == "finished" and info.get("filepath"):
                final_paths[info.get("id") or info["filepath"]] = info["filepath"]

        ydl_opts: dict[str, Any] = {
            "outtmpl": str(output_path / "%(title)s.%(ext)s"),
            "quiet": True,
            "noprogress": True,
            "updatetime": False,
            "noplaylist": no_playlist,
            "playlist_items": playlist_items,
            "writethumbnail": include_metadata,
            "socket_timeout": 60,
            "retries": 10,
            "fragment_retries": 10,
            "file_access_retries": 5,
            "extractor_retries": 5,
            "progress_hooks": [_yt_dlp_hook],
            "postprocessor_hooks": [_postprocessor_hook],
        }

        if progress_hook:
            ydl_opts["progress_hooks"].append(progress_hook)

        if subtitles:
            ydl_opts["writesubtitles"] = True
            ydl_opts["writeautomaticsub"] = True
            ydl_opts["subtitleslangs"] = ["en", "all"]

        if player_client and player_client.lower() != "auto":
            ydl_opts["extractor_args"] = {
                "youtube": {"player_client": [player_client]}
            }
        elif self.pot_provider_available() and (
            "youtube.com" in url or "youtu.be" in url
        ):
            ydl_opts["extractor_args"] = {
                "youtube": {"player_client": ["android"], "fetch_pot": "always"}
            }

        post_processors = []
        if include_metadata:
            post_processors.append({"key": "FFmpegMetadata", "add_metadata": True})
            post_processors.append({"key": "EmbedThumbnail"})

        if audio_only:
            ydl_opts.update(
                {
                    "format": "bestaudio/best",
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": audio_bitrate,
                        }
                    ]
                    + post_processors,
                }
            )
        else:
            format_str = (
                f"bestvideo[height<={vid_height}]+bestaudio/best[height<={vid_height}]"
            )
            if q == "x" or custom_height is not None:
                format_str = "bestvideo+bestaudio/best"

            ydl_opts.update(
                {
                    "format": format_str,
                    "merge_output_format": "mp4",
                    "postprocessors": post_processors,
                }
            )

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download([url])
            except yt_dlp.utils.DownloadCancelled:
                _remove_partial_files(partial_paths)
                raise OperationCancelled("Download cancelled") from None
            except subprocess.TimeoutExpired as e:
                _remove_partial_files(partial_paths)
                raise RuntimeError(POT_TIMEOUT_MESSAGE) from e
            except yt_dlp.utils.DownloadError as e:
                msg = str(e).replace("ERROR: ", "")
                raise RuntimeError(f"Download failed: {msg}") from e
        return {
            "output_path": str(output_path),
            "files": [path for path in final_paths.values() if Path(path).is_file()],
            "message": f"Downloaded: {url[:50]}",
        }


PARTIAL_SUFFIXES = (".part", ".ytdl")


def _remove_partial_files(reported_paths: set[str]) -> None:
    """Delete yt-dlp's leftovers for a cancelled download: only .part and .ytdl files."""
    for reported in reported_paths:
        path = Path(reported)
        candidates = [path] if path.suffix in PARTIAL_SUFFIXES else []
        candidates += [path.with_name(path.name + suffix) for suffix in PARTIAL_SUFFIXES]
        for candidate in candidates:
            if candidate.suffix in PARTIAL_SUFFIXES:
                candidate.unlink(missing_ok=True)


def strip_playlist_params(url: str) -> str:
    """Drop `list`/`index` from a URL that names one video (`v=...`).

    Keeps `v` and the `t` timestamp. Returns the URL unchanged otherwise.
    """
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if "v" not in query or "list" not in query:
        return url
    kept_query = {"v": query["v"]}
    if "t" in query:
        kept_query["t"] = query["t"]
    return urllib.parse.urlunparse(
        parsed._replace(query=urllib.parse.urlencode(kept_query, doseq=True))
    )


def make_download_task(url: str, **options: Any) -> "TaskItem":
    """Build a queued DOWNLOAD task. `options` are download_media keywords."""
    from max_cli.core.engines.task_migration import DOWNLOAD_OPTION_KEYS

    payload: dict[str, Any] = {"url": url}
    for key in DOWNLOAD_OPTION_KEYS:
        if key in options:
            value = options[key]
            payload[key] = str(value) if isinstance(value, Path) else value
    return TaskItem(
        type=TaskType.DOWNLOAD,
        title=url,
        description=url,
        payload=payload,
        output_path=payload.get("output_path"),
    )


def _download_executor(task: "TaskItem") -> dict[str, Any]:
    engine = NetworkEngine()
    payload = task.payload
    url = payload["url"]
    out = Path(payload.get("output_path") or DEFAULT_DOWNLOAD_DIR)
    finished_files: list[str] = []

    def track_progress(status: dict[str, Any]) -> None:
        if status.get("status") == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
            if total:
                task.progress = status.get("downloaded_bytes", 0) / total * 100
        elif status.get("status") == "finished":
            title = (status.get("info_dict") or {}).get("title")
            if title and task.title == url:
                task.title = title
            filename = status.get("filename")
            if filename and filename not in finished_files:
                finished_files.append(filename)

    engine.download_media(
        url=url,
        output_path=out,
        quality=payload.get("quality", "h"),
        audio_only=payload.get("audio_only", False),
        include_metadata=payload.get("include_metadata", True),
        playlist_items=payload.get("playlist_items"),
        no_playlist=payload.get("no_playlist", False),
        progress_hook=track_progress,
        subtitles=payload.get("subtitles", False),
        custom_height=payload.get("custom_height"),
        player_client=payload.get("player_client"),
    )
    # Post-processing (merge, audio extraction) can rename or remove the
    # files yt-dlp reported, so keep only the ones still on disk.
    output_files = [name for name in finished_files if Path(name).is_file()]
    return {
        "output_path": str(out),
        "output_files": output_files,
        "file_size": sum(Path(name).stat().st_size for name in output_files),
        "message": f"Downloaded: {url[:50]}",
    }


from max_cli.core.engines.task_queue import (  # noqa: E402
    TaskItem,
    TaskType,
    register_executor,
)

register_executor(TaskType.DOWNLOAD, _download_executor)
