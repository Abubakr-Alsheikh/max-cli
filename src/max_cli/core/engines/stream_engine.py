"""Streaming through FFmpeg: RTMP output and a local HLS preview server."""

from pathlib import Path


from max_cli.core.engines.ffmpeg_base import FFmpegEngine


class StreamEngine(FFmpegEngine):
    """Live streaming operations."""

    def stream_to_rtmp(
        self,
        input_path: Path,
        rtmp_url: str,
        bitrate: str = "4500k",
        preset: str = "veryfast",
    ) -> None:
        """
        Stream video to an RTMP server.

        Args:
            input_path: Input video file
            rtmp_url: RTMP server URL (e.g., rtmp://live.twitch.tv/app)
            bitrate: Video bitrate for streaming
            preset: Encoding preset for transcoding
        """
        cmd = [
            str(self.ffmpeg_path),
            "-re",
            "-i",
            str(input_path),
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-b:v",
            bitrate,
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-f",
            "flv",
            "-flvflags",
            "no_duration_filesize",
            rtmp_url,
        ]
        self._run(cmd)

    def live_preview(
        self,
        input_path: Path,
        port: int = 8080,
        bitrate: str = "2000k",
    ) -> None:
        """
        Start HTTP server for live preview streaming via HLS.

        Args:
            input_path: Input video file
            port: HTTP server port
            bitrate: Transcoding bitrate
        """
        import tempfile
        import threading
        from http.server import HTTPServer, SimpleHTTPRequestHandler

        hls_dir = Path(tempfile.gettempdir()) / "max_cli_hls"
        hls_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(self.ffmpeg_path),
            "-re",
            "-i",
            str(input_path),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-b:v",
            bitrate,
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-f",
            "hls",
            "-hls_time",
            "2",
            "-hls_list_size",
            "10",
            "-hls_flags",
            "delete_segments",
            "-start_number",
            "1",
            str(hls_dir / "live.m3u8"),
        ]

        class QuietHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(hls_dir), **kwargs)

            def log_message(self, format, *args):
                pass

        def run_server():
            server = HTTPServer(("", port), QuietHandler)
            server.serve_forever()

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()

        self._run(cmd)
