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
        audio_only: bool = False,
        audio_format: str = "mp3",
        video_format: str = "mp4",
        resolution: Optional[str] = None,
        progress_hook: Optional[Callable] = None
    ):
        """
        Downloads video or audio from a URL (YouTube, Twitter, TikTok, etc).
        
        :param progress_hook: A function that accepts the yt-dlp progress dict.
        """
        
        # 1. Base Options
        ydl_opts = {
            'outtmpl': str(output_path / '%(title)s.%(ext)s'),
            'quiet': True,        # specific progress hooks handle output
            'no_warnings': True,
            'noprogress': True,   # Disable default text progress
            'writethumbnail': True, # Download thumbnail
            'updatetime': False,   # Don't mess with file mtime
        }

        # 2. Attach Progress Hook
        if progress_hook:
            ydl_opts['progress_hooks'] = [progress_hook]

        # 3. Configure Format Logic
        if audio_only:
            # --- AUDIO MODE ---
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [
                    {
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': audio_format,
                        'preferredquality': '192', # High quality bitrate
                    },
                    {'key': 'FFmpegMetadata'}, # Embed ID3 tags
                    {'key': 'EmbedThumbnail'}, # Embed album art
                ],
            })
        else:
            # --- VIDEO MODE ---
            # "bv+ba" downloads best video and best audio separately, then merges them.
            # This is critical for 1080p/4K on YouTube.
            
            format_str = f"bestvideo[ext={video_format}]+bestaudio[ext=m4a]/best[ext={video_format}]/best"
            
            # Handle Resolution constraints
            if resolution:
                # e.g., "bestvideo[height<=1080]+bestaudio..."
                res_clean = resolution.replace("p", "") # 1080p -> 1080
                format_str = f"bestvideo[height<={res_clean}]+bestaudio/best[height<={res_clean}]"

            ydl_opts.update({
                'format': format_str,
                'merge_output_format': video_format, # Ensure final container is mp4/mkv
                'postprocessors': [
                    {'key': 'FFmpegMetadata'},
                    {'key': 'EmbedThumbnail'},
                ],
            })

        # 4. Execute
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download([url])
            except yt_dlp.utils.DownloadError as e:
                # Strip technical stack trace, return friendly error
                raise RuntimeError(f"Download failed: {str(e).split(';')[0]}")