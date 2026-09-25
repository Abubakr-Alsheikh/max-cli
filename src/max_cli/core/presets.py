"""Defaults shared by the CLI and the TUI (hardening Phase 4).

Both front ends import these values, so `max video compress --level max` and
the dashboard's "max" level produce the same file. The drift test in
`tests/interface/tui/test_preset_drift.py` checks that they stay in sync.
"""

from pathlib import Path
from typing import Dict, Optional

# --- video compress ---------------------------------------------------------
VIDEO_CRF_BY_LEVEL: Dict[str, int] = {"high": 23, "balanced": 28, "max": 35}
DEFAULT_VIDEO_LEVEL = "balanced"
DEFAULT_VIDEO_PRESET = "medium"

# --- audio bitrates, keyed by the first letter of --quality -----------------
VIDEO_TO_AUDIO_BITRATES: Dict[str, str] = {
    "s": "96k",
    "m": "128k",
    "h": "192k",
    "x": "320k",
}
DEFAULT_VIDEO_TO_AUDIO_QUALITY = "h"
AUDIO_CONVERT_BITRATES: Dict[str, str] = {"s": "128k", "m": "192k", "h": "320k"}
DEFAULT_AUDIO_CONVERT_QUALITY = "h"
AUDIO_COMPRESS_BITRATES: Dict[str, str] = {
    "s": "64k",
    "m": "96k",
    "h": "128k",
    "x": "192k",
}
DEFAULT_AUDIO_COMPRESS_QUALITY = "h"

# --- video concat: user-facing method -> MediaEngine.concatenate_videos -----
CONCAT_METHODS: Dict[str, str] = {"fast": "concat", "safe": "filter"}
DEFAULT_CONCAT_METHOD = "fast"

# --- pdf --------------------------------------------------------------------
PDF_COMPRESS_DPI = 150
PDF_COMPRESS_QUALITY = 80

# --- images and audio metadata ----------------------------------------------
STRIP_IMAGE_METADATA = True
DEFAULT_AUDIO_ORGANIZE_PATTERN = "artist"


def crf_for_level(level: str) -> int:
    """CRF for a compress level name; unknown names get the balanced CRF."""
    return VIDEO_CRF_BY_LEVEL.get(
        level.lower(), VIDEO_CRF_BY_LEVEL[DEFAULT_VIDEO_LEVEL]
    )


def bitrate_for_quality(
    bitrates: Dict[str, str], quality: str, default_quality: str
) -> str:
    """Look up a bitrate by the first letter of `quality` ("high" -> "h")."""
    key = quality.lower()[:1]
    return bitrates.get(key, bitrates[default_quality])


def sibling_path(
    input_path: Path, suffix: str = "", extension: Optional[str] = None
) -> Path:
    """`input_path`'s folder / stem + suffix + extension (default: same one).

    `sibling_path(Path("a/clip.mov"), "_compressed", "mp4")` is
    `a/clip_compressed.mp4`.
    """
    if extension is None:
        new_extension = input_path.suffix
    else:
        new_extension = f".{extension.lstrip('.')}"
    return input_path.parent / f"{input_path.stem}{suffix}{new_extension}"
