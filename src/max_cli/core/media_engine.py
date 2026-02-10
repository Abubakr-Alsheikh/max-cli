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
            # Decode stderr to see what FFmpeg complained about
            error_msg = e.stderr.decode().strip()
            raise RuntimeError(f"FFmpeg Error: {error_msg}")
