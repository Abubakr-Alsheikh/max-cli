import shutil
import subprocess
from pathlib import Path
from typing import List, Optional


class MediaEngine:
    """
    Wrapper around FFmpeg for video and audio manipulation.
    Requires FFmpeg to be installed in the system PATH.
    """

    def __init__(self):
        self.ffmpeg_path = shutil.which("ffmpeg")
        if not self.ffmpeg_path:
            raise RuntimeError(
                "FFmpeg is not installed or not in PATH. "
                "Install it via: 'brew install ffmpeg', 'sudo apt install ffmpeg', or Download from ffmpeg.org"
            )

    def compress_video(
        self, input_path: Path, output_path: Path, crf: int = 28, preset: str = "medium"
    ) -> None:
        """
        Compress video using H.264 (safe compatibility).
        CRF: 0-51 (Lower is better quality). 23 is default, 28 is compressed.
        Preset: ultrafast, superfast, veryfast, faster, fast, medium, slow...
        """
        # cmd structure: ffmpeg -i input -vcodec libx264 -crf 28 -preset fast output
        cmd = [
            "ffmpeg",
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

    def convert_format(self, input_path: Path, output_path: Path) -> None:
        """
        Smart convert (e.g., MKV -> MP4).
        Tries to 'copy' streams if possible (instant), otherwise re-encodes.
        """
        # Try copying streams first (Fastest)
        cmd = [
            "ffmpeg",
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
                "ffmpeg",
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

    def extract_audio(
        self, input_path: Path, output_path: Path, bitrate: str = "192k"
    ) -> None:
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
            "ffmpeg",
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

    def video_to_gif(
        self, input_path: Path, output_path: Path, fps: int = 15, scale: int = 480
    ) -> None:
        """
        Creates a high-quality GIF using a palette generator (prevents graininess).
        """
        # Complex filter graph for better GIF quality
        filters = f"fps={fps},scale={scale}:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"

        cmd = [
            "ffmpeg",
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

    def trim_video(
        self,
        input_path: Path,
        output_path: Path,
        start: str,
        end: Optional[str] = None,
        duration: Optional[str] = None,
    ) -> None:
        """
        Cuts a video clip.
        start: Timestamp (e.g., "00:01:30" or "90")
        end: Timestamp (e.g., "00:02:00")
        duration: Seconds to keep (e.g., "30")
        """
        cmd = ["ffmpeg", "-y", "-i", str(input_path), "-ss", start]

        if end:
            cmd.extend(["-to", end])
        elif duration:
            cmd.extend(["-t", duration])

        # We re-encode to ensure the cut is frame-perfect.
        # Using "copy" (-c copy) is faster but can result in black frames at the start.
        cmd.extend(
            ["-c:v", "libx264", "-c:a", "aac", "-loglevel", "error", str(output_path)]
        )

        self._run(cmd)

    def get_thumbnail(
        self, input_path: Path, output_path: Path, time: str = "00:00:01"
    ) -> None:
        """
        Takes a snapshot at a specific time.
        """
        cmd = [
            "ffmpeg",
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
            "ffmpeg",
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
            "ffmpeg",
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
                "ffmpeg",
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
            "ffmpeg",
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
            "ffmpeg",
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
                "ffmpeg",
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
                "ffmpeg",
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
            "ffmpeg",
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
            "ffmpeg",
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

        cmd = ["ffmpeg", "-y", "-f", "gdigrab" if system == "Windows" else "x11grab"]

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
