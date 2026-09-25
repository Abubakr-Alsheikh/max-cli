"""Audio work through FFmpeg: extraction, volume, compression, denoising."""

import logging
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from max_cli.common.events import ProgressEvent, get_emitter
from max_cli.core.engines.ffmpeg_base import FFmpegEngine

logger = logging.getLogger(__name__)

RNNOISE_MODEL_DIR = Path.home() / ".max_cli" / "rnnoise"
RNNOISE_MODEL_FILENAME = "std.rnnn"
RNNOISE_MODEL_URL = (
    "https://raw.githubusercontent.com/richardpl/arnndn-models/master/std.rnnn"
)


class AudioEngine(FFmpegEngine):
    """Audio operations on audio and video files."""

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

    def _resolve_rnn_model(self) -> Path:
        model_path = RNNOISE_MODEL_DIR / RNNOISE_MODEL_FILENAME
        if model_path.is_file():
            return model_path

        RNNOISE_MODEL_DIR.mkdir(parents=True, exist_ok=True)

        from max_cli.common.events import StatusEvent

        get_emitter().emit(
            StatusEvent(
                message="Downloading speech denoising model (RNNoise)...",
                source="media_engine",
            )
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

        duration = self._get_duration(input_path) or 0.0  # 0 = unknown, no percent
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
