import yt_dlp  # type: ignore[import-untyped]
from pathlib import Path
from typing import Optional, Dict, Any, Callable
import shutil


class NetworkEngine:
    """
    Advanced Media Downloader with Playlist and Metadata controls.
    """

    def __init__(self):
        # Check for JS Runtimes that yt-dlp supports
        self.has_js = any(
            shutil.which(cmd) for cmd in ["node", "deno", "cjs", "quickjs"]
        )

    def get_info(self, url: str) -> Dict[str, Any]:
        """Peeks at the URL to see if it's a playlist and count items."""
        ydl_opts = {"quiet": True, "noplaylist": False, "extract_flat": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

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
        vid_height = {"s": "480", "m": "720", "h": "1080", "x": "2160"}.get(q, "720")
        audio_bitrate = {"s": "64", "m": "128", "h": "192", "x": "320"}.get(q, "192")

        ydl_opts = {
            "outtmpl": str(output_path / "%(title)s.%(ext)s"),
            "quiet": True,
            "noprogress": True,
            "updatetime": False,
            "noplaylist": no_playlist,
            "playlist_items": playlist_items,
            "writethumbnail": include_metadata,  # Skip thumb if meta is off
        }

        if progress_hook:
            ydl_opts["progress_hooks"] = [progress_hook]

        # --- Format & Post-Processors ---
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
            if q == "x":
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
