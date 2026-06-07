import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from max_cli.common.events import ProgressEvent, get_emitter
from max_cli.core.engines.task_queue import TaskItem, TaskType, register_executor

RNNOISE_MODEL_DIR = Path.home() / ".max_cli" / "rnnoise"
RNNOISE_MODEL_FILENAME = "std.rnnn"
RNNOISE_MODEL_URL = (
    "https://raw.githubusercontent.com/richardpl/arnndn-models/master/std.rnnn"
)


class MediaEngine:
    """
    Wrapper around FFmpeg for video and audio manipulation.
    Requires FFmpeg to be installed in the system PATH.
    """

    def __init__(self, auto_resolve: bool = True) -> None:
        self.ffmpeg_path: Path = self._resolve_ffmpeg(auto_resolve)

    def _resolve_ffmpeg(self, auto_resolve: bool) -> Path:
        system_path = shutil.which("ffmpeg")
        if system_path:
            return Path(system_path)

        from max_cli.common.ffmpeg_resolver import FFmpegResolver

        resolver = FFmpegResolver()
        if resolver.local_path.exists() and resolver._validate_binary(
            resolver.local_path
        ):
            return resolver.local_path

        if auto_resolve:
            from max_cli.common.ffmpeg_resolver import resolve_ffmpeg

            return resolve_ffmpeg(auto_download=True)

        raise RuntimeError(
            "FFmpeg is not installed or not in PATH. "
            "Install it via: 'brew install ffmpeg', 'sudo apt install ffmpeg', or Download from ffmpeg.org"
        )

    def compress_video(
        self, input_path: Path, output_path: Path, crf: int = 28, preset: str = "medium"
    ) -> Dict[str, Any]:
        """
        Compress video using H.264 (safe compatibility).
        CRF: 0-51 (Lower is better quality). 23 is default, 28 is compressed.
        Preset: ultrafast, superfast, veryfast, faster, fast, medium, slow...
        """
        # cmd structure: ffmpeg -i input -vcodec libx264 -crf 28 -preset fast output
        cmd = [
            str(self.ffmpeg_path),
            "-y",  # Overwrite output without asking (Typer handles the safety check)
            "-i",
            str(input_path),
            "-vcodec",
            "libx264",
            "-crf",
            str(crf),
            "-preset",
            preset,
            "-acodec",
            "aac",  # Ensure audio is standard AAC
            "-b:a",
            "128k",  # Good enough audio bitrate
            "-movflags",
            "+faststart",  # Web optimization
            "-loglevel",
            "error",  # Suppress the wall of text
            "-stats",  # Show simple progress
            str(output_path),
        ]
        self._run(cmd)
        return {
            "output_path": str(output_path),
            "output_files": [str(output_path)],
            "message": f"Compressed: {input_path.name}",
        }

    def convert_format(self, input_path: Path, output_path: Path) -> Dict[str, Any]:
        """
        Smart convert (e.g., MKV -> MP4).
        Tries to 'copy' streams if possible (instant), otherwise re-encodes.
        """
        # Try copying streams first (Fastest)
        cmd = [
            str(self.ffmpeg_path),
            "-y",
            "-i",
            str(input_path),
            "-c",
            "copy",  # Direct stream copy
            "-loglevel",
            "error",
            str(output_path),
        ]

        try:
            self._run(cmd)
        except subprocess.CalledProcessError:
            # If copy fails (incompatible container), re-encode
            cmd_reencode = [
                str(self.ffmpeg_path),
                "-y",
                "-i",
                str(input_path),
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-loglevel",
                "error",
                str(output_path),
            ]
            self._run(cmd_reencode)
        return {
            "output_path": str(output_path),
            "output_files": [str(output_path)],
            "message": f"Converted: {input_path.name} -> {output_path.name}",
        }

    def extract_audio(
        self, input_path: Path, output_path: Path, bitrate: str = "192k"
    ) -> Dict[str, Any]:
        """
        Extracts audio from video and converts it to the desired format.
        Supported extensions: .mp3, .wav, .aac, .flac
        """
        # Map extension to the best FFmpeg codec
        codec_map = {
            ".mp3": "libmp3lame",
            ".wav": "pcm_s16le",
            ".aac": "aac",
            ".flac": "flac",
        }

        ext = output_path.suffix.lower()
        codec = codec_map.get(ext, "libmp3lame")

        cmd = [
            str(self.ffmpeg_path),
            "-y",
            "-i",
            str(input_path),
            "-vn",  # Disable video recording
            "-acodec",
            codec,
        ]

        # Only MP3 and AAC really benefit from explicit bitrate flags here
        if ext in [".mp3", ".aac"]:
            cmd.extend(["-b:a", bitrate])

        cmd.extend(["-loglevel", "error", str(output_path)])

        self._run(cmd)
        return {
            "output_path": str(output_path),
            "output_files": [str(output_path)],
            "message": f"Extracted audio: {output_path.name}",
        }

    def video_to_gif(
        self, input_path: Path, output_path: Path, fps: int = 15, scale: int = 480
    ) -> Dict[str, Any]:
        """
        Creates a high-quality GIF using a palette generator (prevents graininess).
        """
        # Complex filter graph for better GIF quality
        filters = f"fps={fps},scale={scale}:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"

        cmd = [
            str(self.ffmpeg_path),
            "-y",
            "-i",
            str(input_path),
            "-vf",
            filters,
            "-loglevel",
            "error",
            str(output_path),
        ]
        self._run(cmd)
        return {
            "output_path": str(output_path),
            "output_files": [str(output_path)],
            "message": f"Created GIF: {output_path.name}",
        }

    def trim_video(
        self,
        input_path: Path,
        output_path: Path,
        start: str,
        end: Optional[str] = None,
        duration: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Cuts a video clip.
        start: Timestamp (e.g., "00:01:30" or "90")
        end: Timestamp (e.g., "00:02:00")
        duration: Seconds to keep (e.g., "30")
        """
        cmd = [str(self.ffmpeg_path), "-y", "-i", str(input_path), "-ss", start]

        if end:
            cmd.extend(["-to", end])
        elif duration:
            cmd.extend(["-t", duration])

        audio_extensions = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"}
        is_audio = input_path.suffix.lower() in audio_extensions

        if is_audio:
            output_path = output_path.with_suffix(".mp3")
            cmd.extend(["-c:a", "libmp3lame", "-loglevel", "error", str(output_path)])
        else:
            cmd.extend(
                [
                    "-c:v",
                    "libx264",
                    "-c:a",
                    "aac",
                    "-loglevel",
                    "error",
                    str(output_path),
                ]
            )

        self._run(cmd)
        return {
            "output_path": str(output_path),
            "output_files": [str(output_path)],
            "message": f"Trimmed: {input_path.name}",
        }

    def get_thumbnail(
        self, input_path: Path, output_path: Path, time: str = "00:00:01"
    ) -> None:
        """
        Takes a snapshot at a specific time.
        """
        cmd = [
            str(self.ffmpeg_path),
            "-y",
            "-ss",
            time,
            "-i",
            str(input_path),
            "-vframes",
            "1",  # Stop after 1 frame
            "-q:v",
            "2",  # High quality JPEG
            "-loglevel",
            "error",
            str(output_path),
        ]
        self._run(cmd)

    def adjust_volume(self, input_path: Path, output_path: Path, db: float) -> None:
        """
        Changes audio volume.
        db > 0 (Louder), db < 0 (Quieter).
        Example: db=10 makes it perceived 2x louder roughly.
        """
        # We use the 'volume' filter.
        # Format: "volume=10dB"
        cmd = [
            str(self.ffmpeg_path),
            "-y",
            "-i",
            str(input_path),
            "-filter:a",
            f"volume={db}dB",
            "-vcodec",
            "copy",  # Don't re-encode video (Fast!)
            "-loglevel",
            "error",
            str(output_path),
        ]
        self._run(cmd)

    def mute_video(self, input_path: Path, output_path: Path) -> None:
        """
        Removes audio track completely.
        """
        cmd = [
            str(self.ffmpeg_path),
            "-y",
            "-i",
            str(input_path),
            "-c",
            "copy",
            "-an",  # No Audio flag
            "-loglevel",
            "error",
            str(output_path),
        ]
        self._run(cmd)

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

        from max_cli.common.logger import console

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
            console.print(
                f"[cyan]Live preview available at "
                f"http://localhost:{port}/live.m3u8[/cyan]"
            )
            server.serve_forever()

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()

        self._run(cmd)

    def _run(self, cmd: List[str]):
        """Runs the subprocess command."""
        try:
            subprocess.run(
                cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode().strip()
            raise RuntimeError(f"FFmpeg Error: {error_msg}")

    def concatenate_videos(
        self, input_paths: List[Path], output_path: Path, method: str = "concat"
    ) -> None:
        """
        Merge multiple video files into one.

        Args:
            input_paths: List of video files to concatenate
            output_path: Output file path
            method: Concatenation method - 'concat' (demuxer) or 'filter' (complex filter)
        """
        if not input_paths:
            raise ValueError("No input files provided")

        for path in input_paths:
            if not path.exists():
                raise FileNotFoundError(f"File not found: {path}")

        if method == "concat":
            self._concatenate_demuxer(input_paths, output_path)
        else:
            self._concatenate_filter(input_paths, output_path)

    def _concatenate_demuxer(self, input_paths: List[Path], output_path: Path) -> None:
        """Fast concatenation using concat demuxer (works when streams match)."""
        list_file = output_path.parent / f"{output_path.stem}_concat_list.txt"

        try:
            with open(list_file, "w") as f:
                for path in input_paths:
                    f.write(f"file '{path.absolute()}'\\n")

            cmd = [
                str(self.ffmpeg_path),
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c",
                "copy",
                "-loglevel",
                "error",
                str(output_path),
            ]
            self._run(cmd)
        finally:
            if list_file.exists():
                list_file.unlink()

    def _concatenate_filter(self, input_paths: List[Path], output_path: Path) -> None:
        """Filter-based concatenation (re-encodes, works with different codecs)."""
        filter_str = "".join(
            f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}];"
            f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a{i}];"
            for i in range(len(input_paths))
        )

        for i in range(len(input_paths)):
            filter_str += f"[v{i}][a{i}]"
        filter_str += f"concat=n={len(input_paths)}:v=1:a=1[outv][outa]"

        cmd = []
        for path in input_paths:
            cmd.extend(["-i", str(path)])

        cmd.extend(
            [
                "-y",
                "-filter_complex",
                filter_str,
                "-map",
                "[outv]",
                "-map",
                "[outa]",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-loglevel",
                "error",
                str(output_path),
            ]
        )

        self._run(cmd)

    def adjust_brightness(
        self,
        input_path: Path,
        output_path: Path,
        brightness: float = 1.0,
        contrast: float = 1.0,
    ) -> None:
        """
        Adjust brightness and contrast.

        Args:
            brightness: 0.0 (darker) to 2.0 (brighter), default 1.0
            contrast: 0.0 (grayscale) to 2.0 (more contrast), default 1.0
        """
        cmd = [
            str(self.ffmpeg_path),
            "-y",
            "-i",
            str(input_path),
            "-vf",
            f"eq=brightness={brightness - 1.0}:contrast={contrast}",
            "-c:a",
            "copy",
            "-loglevel",
            "error",
            str(output_path),
        ]
        self._run(cmd)

    def apply_color_preset(
        self, input_path: Path, output_path: Path, preset: str = "vivid"
    ) -> None:
        """
        Apply color grading presets.

        Args:
            preset: 'vintage', 'noir', 'vivid', 'warm', 'cool', 'fade'
        """
        preset_filters = {
            "vintage": "curves=vintage",
            "noir": "colorlevels=rimin=0.058:gimin=0.058:bimin=0.058,colortemperature=temperature=6500",
            "vivid": "eq=saturation=1.5:contrast=1.1",
            "warm": "colortemperature=temperature=9000",
            "cool": "colortemperature=temperature=4000",
            "fade": "eq=brightness=-0.1:saturation=0.8:gamma=1.2",
        }

        if preset not in preset_filters:
            raise ValueError(
                f"Unknown preset: {preset}. Available: {list(preset_filters.keys())}"
            )

        cmd = [
            str(self.ffmpeg_path),
            "-y",
            "-i",
            str(input_path),
            "-vf",
            preset_filters[preset],
            "-c:a",
            "copy",
            "-loglevel",
            "error",
            str(output_path),
        ]
        self._run(cmd)

    def stabilize_video(self, input_path: Path, output_path: Path) -> None:
        """
        Stabilize shaky video using vidstab filter.
        Two-pass process for best results.
        """
        temp_trf = input_path.parent / f"{input_path.stem}_stabilize.trf"

        try:
            cmd1 = [
                str(self.ffmpeg_path),
                "-y",
                "-i",
                str(input_path),
                "-vf",
                "vidstabdetect=shakiness=5:accuracy=15",
                "-f",
                "null",
                "-",
            ]
            self._run(cmd1)

            cmd2 = [
                str(self.ffmpeg_path),
                "-y",
                "-i",
                str(input_path),
                "-vf",
                f"vidstabtransform=input={temp_trf}:smoothing=10:optalgo=gauss:maxshift=50:maxangle=0.1:crop=black:zoom=0:interpol=linear",
                "-c:a",
                "copy",
                "-loglevel",
                "error",
                str(output_path),
            ]
            self._run(cmd2)
        finally:
            if temp_trf.exists():
                temp_trf.unlink()

    def normalize_audio(
        self, input_path: Path, output_path: Path, target_level: float = -20.0
    ) -> None:
        """
        Normalize audio to a target level.

        Args:
            input_path: Input audio/video file
            output_path: Output file path
            target_level: Target loudness in dB (default -20.0 LUFS)
        """
        cmd = [
            str(self.ffmpeg_path),
            "-y",
            "-i",
            str(input_path),
            "-af",
            f"loudnorm=I={target_level}",
            "-loglevel",
            "error",
            str(output_path),
        ]
        self._run(cmd)

    def compress_audio(
        self,
        input_path: Path,
        output_path: Path,
        bitrate: str = "128k",
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None,
    ) -> None:
        """
        Compress audio by re-encoding to a lower bitrate.

        Args:
            input_path: Input audio file
            output_path: Output audio file path (extension determines codec)
            bitrate: Target audio bitrate (e.g., 128k, 96k, 64k, 32k)
            sample_rate: Target sample rate in Hz (e.g., 44100, 22050, 16000)
            channels: Number of audio channels (1=mono, 2=stereo)
        """
        codec_map = {
            ".mp3": "libmp3lame",
            ".aac": "aac",
            ".m4a": "aac",
            ".ogg": "libvorbis",
            ".wav": "pcm_s16le",
            ".flac": "flac",
        }

        ext = output_path.suffix.lower()
        codec = codec_map.get(ext, "libmp3lame")

        cmd = [
            str(self.ffmpeg_path),
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-acodec",
            codec,
        ]

        if codec in ["libmp3lame", "aac", "libvorbis"]:
            cmd.extend(["-b:a", bitrate])

        if sample_rate is not None:
            cmd.extend(["-ar", str(sample_rate)])

        if channels is not None:
            cmd.extend(["-ac", str(channels)])

        cmd.extend(["-loglevel", "error", str(output_path)])

        self._run(cmd)

    def convert_audio(
        self,
        input_path: Path,
        output_path: Path,
        codec: str = "libmp3lame",
        bitrate: str = "192k",
    ) -> None:
        """
        Convert audio between formats.

        Args:
            input_path: Input audio/video file
            output_path: Output file path
            codec: Audio codec (libmp3lame, aac, flac, pcm_s16le)
            bitrate: Audio bitrate (e.g., 128k, 192k, 320k)
        """
        codec_map = {
            ".mp3": "libmp3lame",
            ".aac": "aac",
            ".flac": "flac",
            ".wav": "pcm_s16le",
            ".ogg": "libvorbis",
        }

        target_codec = codec_map.get(output_path.suffix.lower(), codec)

        cmd = [
            str(self.ffmpeg_path),
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-acodec",
            target_codec,
        ]

        if target_codec in ["libmp3lame", "aac", "libvorbis"]:
            cmd.extend(["-b:a", bitrate])

        cmd.extend(["-loglevel", "error", str(output_path)])
        self._run(cmd)

    def screen_record(
        self,
        output_path: Path,
        duration: Optional[int] = None,
        fps: int = 30,
        audio: bool = False,
    ) -> None:
        """
        Record screen using platform-specific capture.

        Args:
            output_path: Output video file
            duration: Recording duration in seconds (None for manual stop)
            fps: Frames per second
            audio: Include system audio (if supported)
        """
        import platform

        system = platform.system()
        input_source = ""

        if system == "Windows":
            input_source = "desktop"
        elif system == "Darwin":
            input_source = ":0.0"
        else:
            input_source = ":0.0"

        cmd = [
            str(self.ffmpeg_path),
            "-y",
            "-f",
            "gdigrab" if system == "Windows" else "x11grab",
        ]

        if system == "Windows":
            cmd.extend(["-i", "desktop"])
        else:
            cmd.extend(["-framerate", str(fps), "-i", input_source])

        if audio:
            if system == "Windows":
                cmd.extend(["-f", "dshow", "-i", "audio=virtual-audio-capture"])
            elif system == "Darwin":
                cmd.extend(["-f", "avfoundation", "-i", "none:0"])
            else:
                cmd.extend(["-f", "pulse", "-i", "default"])

        if duration:
            cmd.extend(["-t", str(duration)])

        cmd.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                " ultrafast",
                "-c:a",
                "aac",
                "-loglevel",
                "error",
                str(output_path),
            ]
        )

        self._run(cmd)

    def _get_duration(self, input_path: Path) -> float:
        ffprobe_path = Path(
            str(self.ffmpeg_path).rsplit(".", 1)[0] + "_probe" + self.ffmpeg_path.suffix
        )
        if not ffprobe_path.is_file():
            ffprobe_path = self.ffmpeg_path.parent / (
                "ffprobe" + self.ffmpeg_path.suffix
            )
        cmd = [
            str(ffprobe_path),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception:
            pass
        return 0.0

    def _resolve_rnn_model(self) -> Path:
        model_path = RNNOISE_MODEL_DIR / RNNOISE_MODEL_FILENAME
        if model_path.is_file():
            return model_path

        RNNOISE_MODEL_DIR.mkdir(parents=True, exist_ok=True)

        from max_cli.common.logger import console

        console.print(
            "[yellow]Downloading speech denoising model (RNNoise)...[/yellow]"
        )

        import requests

        response = requests.get(RNNOISE_MODEL_URL, stream=True, timeout=30)
        response.raise_for_status()

        with open(model_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        return model_path

    def denoise_audio(
        self,
        input_path: Path,
        output_path: Path,
        mode: str = "auto",
        strength: str = "medium",
        profile: Optional[str] = None,
        hum_cutoff: int = 80,
    ) -> Dict[str, Any]:
        """
        Denoise audio using FFmpeg audio filters.
        Emits ProgressEvent via the global event bus for CLI progress bars.

        Args:
            input_path: Path to input audio/video file
            output_path: Path for the denoised output file
            mode: Denoise mode - "auto", "hiss", or "hum"
            strength: Denoise strength (only for "auto" mode) - "mild", "medium", or "aggressive"
            profile: Optional denoising profile (reserved for future use)
            hum_cutoff: Cutoff frequency in Hz for hum removal mode (default: 80)
        """
        if not input_path.is_file():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        valid_modes = {"auto", "hiss", "hum", "speech"}
        if mode not in valid_modes:
            raise ValueError(
                f"Invalid mode '{mode}'. Must be one of: {', '.join(sorted(valid_modes))}"
            )

        if mode == "auto":
            strength_map = {
                "mild": "0.0001:0.016:0.016",
                "medium": "0.0005:0.016:0.016",
                "aggressive": "0.003:0.016:0.016",
            }
            if strength not in strength_map:
                raise ValueError(
                    f"Invalid strength '{strength}'. Must be one of: {', '.join(sorted(strength_map))}"
                )
            params = strength_map[strength]
            af_filter = f"anlmdn=s={params}"
        elif mode == "hiss":
            af_filter = "afftdn=nr=12:nf=-40"
        elif mode == "hum":
            af_filter = f"highpass=f={hum_cutoff}"
        elif mode == "speech":
            model_path = self._resolve_rnn_model()
            win_path = model_path.as_posix()
            if win_path[1] == ":":
                win_path = win_path[2:]
            af_filter = f"arnndn=m={win_path}"
        else:
            raise ValueError(f"Unhandled mode: {mode}")

        duration = self._get_duration(input_path)
        emitter = get_emitter()

        cmd = [
            str(self.ffmpeg_path),
            "-y",
            "-i",
            str(input_path),
            "-af",
            af_filter,
            "-c:v",
            "copy",
            "-loglevel",
            "error",
            "-progress",
            "pipe:1",
            str(output_path),
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        stderr_collected: List[str] = []
        stderr_lock = threading.Lock()

        def _collect_stderr():
            if process.stderr:
                for line in process.stderr:
                    with stderr_lock:
                        stderr_collected.append(line)

        stderr_thread = threading.Thread(target=_collect_stderr, daemon=True)
        stderr_thread.start()

        if process.stdout:
            for line in process.stdout:
                line = line.strip()
                if line.startswith("out_time_us="):
                    try:
                        time_us = int(line.split("=", 1)[1])
                        time_sec = time_us / 1_000_000
                        if duration > 0:
                            pct = min((time_sec / duration) * 100, 99.9)
                            emitter.emit(
                                ProgressEvent(
                                    file=input_path.name,
                                    percentage=pct,
                                    current=int(time_sec),
                                    total=int(duration),
                                    extra={"mode": mode},
                                )
                            )
                    except (ValueError, IndexError):
                        pass

        process.wait()
        stderr_thread.join(timeout=2)

        if process.returncode != 0:
            with stderr_lock:
                error_msg = "".join(stderr_collected).strip()
            raise RuntimeError(f"FFmpeg Error: {error_msg}")

        emitter.emit(
            ProgressEvent(
                file=input_path.name,
                percentage=100.0,
                current=int(duration) if duration > 0 else 0,
                total=int(duration) if duration > 0 else 0,
            )
        )

        return {
            "output_path": str(output_path),
            "output_files": [str(output_path)],
            "message": f"Denoised: {input_path.name} (mode={mode})",
        }


def _video_compress_executor(task: TaskItem) -> Dict[str, Any]:
    engine = MediaEngine()
    payload = task.payload
    input_path = Path(payload["input_path"])
    output_path = Path(
        payload.get(
            "output_path", input_path.parent / f"{input_path.stem}_compressed.mp4"
        )
    )
    engine.compress_video(
        input_path=input_path,
        output_path=output_path,
        crf=payload.get("crf", 28),
        preset=payload.get("preset", "medium"),
    )
    return {
        "output_path": str(output_path),
        "output_files": [str(output_path)],
    }


def _video_convert_executor(task: TaskItem) -> Dict[str, Any]:
    engine = MediaEngine()
    payload = task.payload
    input_path = Path(payload["input_path"])
    output_path = Path(
        payload.get("output_path", input_path.parent / f"{input_path.stem}.mp4")
    )
    engine.convert_format(input_path=input_path, output_path=output_path)
    return {
        "output_path": str(output_path),
        "output_files": [str(output_path)],
    }


def _video_to_audio_executor(task: TaskItem) -> Dict[str, Any]:
    engine = MediaEngine()
    payload = task.payload
    input_path = Path(payload["input_path"])
    ext = payload.get("format", "mp3")
    output_path = Path(
        payload.get("output_path", input_path.parent / f"{input_path.stem}.{ext}")
    )
    engine.extract_audio(
        input_path=input_path,
        output_path=output_path,
        bitrate=payload.get("bitrate", "192k"),
    )
    return {
        "output_path": str(output_path),
        "output_files": [str(output_path)],
    }


register_executor(TaskType.VIDEO_COMPRESS, _video_compress_executor)
register_executor(TaskType.VIDEO_CONVERT, _video_convert_executor)
register_executor(TaskType.VIDEO_TO_AUDIO, _video_to_audio_executor)


def _video_denoise_executor(task: TaskItem) -> Dict[str, Any]:
    engine = MediaEngine()
    payload = task.payload
    input_path = Path(payload["input_path"])
    output_path = Path(
        payload.get(
            "output_path",
            input_path.parent / f"{input_path.stem}_denoised{input_path.suffix}",
        )
    )
    engine.denoise_audio(
        input_path=input_path,
        output_path=output_path,
        mode=payload.get("mode", "auto"),
        strength=payload.get("strength", "medium"),
        hum_cutoff=payload.get("hum_cutoff", 80),
    )
    return {
        "output_path": str(output_path),
        "output_files": [str(output_path)],
    }


register_executor(TaskType.VIDEO_DENOISE, _video_denoise_executor)
register_executor(TaskType.AUDIO_DENOISE, _video_denoise_executor)
