"""Video work through FFmpeg: compress, convert, trim, effects, recording."""

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from max_cli.core.engines.ffmpeg_base import FFmpegEngine

logger = logging.getLogger(__name__)


def resolve_concat_inputs(target: Path) -> List[Path]:
    """Video paths to join, from a glob pattern or a `.txt` list.

    A pattern such as `clips/*.mp4` returns the matches, sorted. A `.txt`
    file lists one path per line, with or without ffmpeg's `file '...'` form.
    Raises ValueError when `target` is neither or matches nothing.
    """
    if "*" in target.name or "?" in target.name:
        folder = target.parent if target.parent != Path(".") else Path.cwd()
        matches = sorted(folder.glob(target.name))
        if not matches:
            raise ValueError(f"No files found matching pattern: {target.name}")
        return matches
    if target.is_file() and target.suffix == ".txt":
        paths = []
        for line in target.read_text(encoding="utf-8").splitlines():
            entry = line.strip()
            if entry.startswith("file "):
                entry = entry[len("file ") :].strip().strip("'\"")
            if entry:
                paths.append(Path(entry))
        return paths
    raise ValueError(
        "Provide either a .txt file with file paths or a glob pattern (e.g., *.mp4)"
    )


class VideoEngine(FFmpegEngine):
    """Video operations."""

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
            with open(list_file, "w", encoding="utf-8") as f:
                for path in input_paths:
                    # Concat demuxer syntax: a literal ' is written as '\'' inside quotes.
                    quoted = str(path.absolute()).replace("'", "'\\''")
                    f.write(f"file '{quoted}'\n")

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
