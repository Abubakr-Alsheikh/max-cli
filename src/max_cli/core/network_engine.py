import yt_dlp
from pathlib import Path
from typing import Optional, Callable


class NetworkEngine:
    """
    Handles network operations, specifically media downloading via yt-dlp.
    """

    def download_media(
        self,
        url: str,
        output_path: Path,
        quality: str = "h",  # s, m, h, x
        audio_only: bool = False,
        audio_format: str = "mp3",
        video_format: str = "mp4",
        progress_hook: Optional[Callable] = None,
    ):
        # --- 1. Map Presets to Settings ---
        # Normalize input (handle 'small', 'Small', 's')
        q = quality.lower()[0]

        # Default defaults
        vid_height = "720"
        audio_bitrate = "192"

        if q == "s":  # Small / Saver
            vid_height = "480"
            audio_bitrate = "64"
        elif q == "m":  # Medium / Standard
            vid_height = "720"
            audio_bitrate = "128"
        elif q == "h":  # High / HD
            vid_height = "1080"
            audio_bitrate = "192"
        elif q == "x":  # X-High / Best
            vid_height = "2160"  # 4K limit, effectively "best"
            audio_bitrate = "320"

        # --- 2. Configure yt-dlp Options ---
        ydl_opts = {
            "outtmpl": str(output_path / "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "writethumbnail": True,
            "updatetime": False,  # Keep original upload date? False = use download time
        }

        if progress_hook:
            ydl_opts["progress_hooks"] = [progress_hook]

        # --- 3. Format Selection Logic ---
        if audio_only:
            # Audio Extraction Strategy
            ydl_opts.update(
                {
                    "format": "bestaudio/best",
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": audio_format,
                            "preferredquality": audio_bitrate,
                        },
                        {"key": "FFmpegMetadata"},
                        {"key": "EmbedThumbnail"},
                    ],
                }
            )
        else:
            # Video Strategy
            if q == "x":
                # Just get the absolute best, regardless of container/codec
                format_str = "bestvideo+bestaudio/best"
            else:
                # Constrain height, fallback to best available if height not found
                format_str = f"bestvideo[height<={vid_height}]+bestaudio/best[height<={vid_height}]"

            ydl_opts.update(
                {
                    "format": format_str,
                    "merge_output_format": video_format,
                    "postprocessors": [
                        {"key": "FFmpegMetadata"},
                        {"key": "EmbedThumbnail"},
                    ],
                }
            )

        # --- 4. Execution ---
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download([url])
            except yt_dlp.utils.DownloadError as e:
                # Clean error message
                msg = str(e).replace("ERROR: ", "")
                raise RuntimeError(f"Download failed: {msg}")
