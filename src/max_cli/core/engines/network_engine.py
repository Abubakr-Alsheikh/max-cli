from pathlib import Path
from typing import Optional, Dict, Any, Callable, Union
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request


QUALITY_MAP: Dict[str, Dict[str, Union[str, int]]] = {
    "ss": {"height": 360, "bitrate": 64, "label": "360p"},
    "s": {"height": 480, "bitrate": 64, "label": "480p"},
    "m": {"height": 720, "bitrate": 128, "label": "720p"},
    "h": {"height": 1080, "bitrate": 192, "label": "1080p"},
    "x": {"height": 2160, "bitrate": 320, "label": "4K"},
}

POT_PROVIDER_PACKAGE = "bgutil-ytdlp-pot-provider"
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
        from yt_dlp.extractor.youtube.pot._registry import _pot_providers  # type: ignore[import-untyped]  # private yt-dlp module, no stubs

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

    def install_pot_provider(self) -> Dict[str, Any]:
        """Install the bgutil POT provider plugin via pip."""
        result = self._run_command(
            [shutil.which("pip") or "pip", "install", "-U", POT_PROVIDER_PACKAGE],
            timeout=900,
        )
        return {
            "ok": result.returncode == 0,
            "output": (result.stdout + result.stderr).strip(),
        }

    def setup_pot_server(self) -> Dict[str, Any]:
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

        with tempfile.TemporaryDirectory() as tmp:
            tarball = Path(tmp) / "canvas.tar.gz"
            try:
                urllib.request.urlretrieve(CANVAS_MIRROR_URL, tarball)
                with tarfile.open(tarball, "r:gz") as archive:
                    archive.extractall(canvas_pkg)  # noqa: S202 - trusted mirror binary
                return (canvas_pkg / "build" / "Release" / "canvas.node").exists()
            except Exception:
                return False

    def get_info(self, url: str) -> Dict[str, Any]:
        """Peeks at the URL to see if it's a playlist and count items."""
        import yt_dlp

        ydl_opts = {"quiet": True, "noplaylist": False, "extract_flat": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    def get_quality_info(
        self, quality: str, custom_height: Optional[int] = None
    ) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
        import yt_dlp

        from max_cli.common.events import (
            DownloadCompleteEvent,
            DownloadProgressEvent,
            get_emitter,
        )

        if not self.has_js:
            from max_cli.common.logger import console

            console.print(
                "[yellow]⚠️ Warning: No JavaScript runtime (Node.js/Deno) found.[/yellow]"
            )
            console.print(
                "[dim]YouTube downloads may be limited or fail. Install Deno: winget install DenoLand.Deno[/dim]\n"
            )

        q = quality.lower()[0]

        quality_info = self.get_quality_info(quality, custom_height)
        vid_height = quality_info["height"]
        audio_bitrate = quality_info["bitrate"]

        emitter = get_emitter()

        def _yt_dlp_hook(d: dict) -> None:
            status = d.get("status")
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

        ydl_opts: Dict[str, Any] = {
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
            except yt_dlp.utils.DownloadError as e:
                msg = str(e).replace("ERROR: ", "")
                raise RuntimeError(f"Download failed: {msg}")
        return {
            "output_path": str(output_path),
            "message": f"Downloaded: {url[:50]}",
        }


def _download_executor(task: "TaskItem") -> Dict[str, Any]:
    engine = NetworkEngine()
    payload = task.payload
    url = payload["url"]
    out = Path(payload.get("output_path", Path.home() / "Max Downloads"))
    quality = payload.get("quality", "h")
    audio_only = payload.get("audio_only", False)
    subs = payload.get("subtitles", False)
    meta = payload.get("include_metadata", True)
    custom_h = payload.get("custom_height")
    player_client = payload.get("player_client")

    engine.download_media(
        url=url,
        output_path=out,
        quality=quality,
        audio_only=audio_only,
        subtitles=subs,
        include_metadata=meta,
        custom_height=custom_h,
        player_client=player_client,
    )
    return {
        "output_path": str(out),
        "output_files": [str(out)],
        "message": f"Downloaded: {url[:50]}",
    }


from max_cli.core.engines.task_queue import TaskItem, TaskType, register_executor  # noqa: E402

register_executor(TaskType.DOWNLOAD, _download_executor)
