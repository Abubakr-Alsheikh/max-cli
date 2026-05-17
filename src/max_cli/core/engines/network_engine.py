import yt_dlp  # type: ignore[import-untyped]
from pathlib import Path
from typing import Optional, Dict, Any, Callable, Union
import shutil


QUALITY_MAP: Dict[str, Dict[str, Union[str, int]]] = {
    "ss": {"height": 360, "bitrate": 64, "label": "360p"},
    "s": {"height": 480, "bitrate": 64, "label": "480p"},
    "m": {"height": 720, "bitrate": 128, "label": "720p"},
    "h": {"height": 1080, "bitrate": 192, "label": "1080p"},
    "x": {"height": 2160, "bitrate": 320, "label": "4K"},
}


class NetworkEngine:
    """
    Advanced Media Downloader with Playlist and Metadata controls.
    """

    def __init__(self):
        self.has_js = any(
            shutil.which(cmd) for cmd in ["node", "deno", "cjs", "quickjs"]
        )

    def get_info(self, url: str) -> Dict[str, Any]:
        """Peeks at the URL to see if it's a playlist and count items."""
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
    ):
        if not self.has_js:
            from max_cli.common.logger import console

            console.print(
                "[yellow]⚠️ Warning: No JavaScript runtime (Node.js/Deno) found.[/yellow]"
            )
            console.print(
                "[dim]YouTube downloads may be limited or fail. Please install Node.js.[/dim]\n"
            )

        q = quality.lower()[0]

        quality_info = self.get_quality_info(quality, custom_height)
        vid_height = quality_info["height"]
        audio_bitrate = quality_info["bitrate"]

        ydl_opts = {
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
        }

        if subtitles:
            ydl_opts["writesubtitles"] = True
            ydl_opts["writeautomaticsub"] = True
            ydl_opts["subtitleslangs"] = ["en", "all"]

        if progress_hook:
            ydl_opts["progress_hooks"] = [progress_hook]

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
                # Clean error message
                msg = str(e).replace("ERROR: ", "")
                raise RuntimeError(f"Download failed: {msg}")
