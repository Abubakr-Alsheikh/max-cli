"""Downloading part of a video: from a start time to an end time.

yt-dlp fetches only that stretch (`download_ranges`), through FFmpeg, which
seeks over HTTP. Without `exact`, the cut starts at the keyframe before the
start time, a second or two early; `exact` re-encodes so it starts on time,
which is slower. yt-dlp reports no progress for a part, only its end.
https://github.com/yt-dlp/yt-dlp#download-options (--download-sections)
"""

import re
from dataclasses import dataclass
from typing import Any, Optional

# "90", "1:30", "1:02:03", "1:30.5": the last part may have a fraction.
WHOLE_PART = re.compile(r"^\d+$")
LAST_PART = re.compile(r"^\d+(?:\.\d+)?$")
MAX_PARTS = 3  # hours:minutes:seconds
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
TIME_EXAMPLE = "Write times like 90, 1:30 or 1:02:03."


def parse_time(text: Optional[str]) -> Optional[float]:
    """Seconds in "90", "1:30" or "1:02:03"; None for empty text.

    Minutes and seconds after the first part stay under 60. Raises
    ValueError for anything else.
    """
    text = (text or "").strip()
    if not text:
        return None
    parts = text.split(":")
    shapes_ok = len(parts) <= MAX_PARTS and LAST_PART.match(parts[-1])
    if not shapes_ok or not all(WHOLE_PART.match(part) for part in parts[:-1]):
        raise ValueError(f"'{text}' isn't a time. {TIME_EXAMPLE}")
    numbers = [float(part) for part in parts]
    if any(number >= SECONDS_PER_MINUTE for number in numbers[1:]):
        raise ValueError(f"'{text}' isn't a time. {TIME_EXAMPLE}")
    seconds = 0.0
    for number in numbers:
        seconds = seconds * SECONDS_PER_MINUTE + number
    return seconds


def clock(seconds: float) -> str:
    """90 as "1:30", 3723 as "1:02:03"."""
    whole = int(round(seconds))
    hours, rest = divmod(whole, SECONDS_PER_HOUR)
    minutes, secs = divmod(rest, SECONDS_PER_MINUTE)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes}:{secs:02}"


@dataclass(frozen=True)
class DownloadSection:
    """The stretch to download; `end` None runs to the end of the video."""

    start: float = 0.0
    end: Optional[float] = None
    exact: bool = False

    @classmethod
    def parse(
        cls, start: Optional[str], end: Optional[str], exact: bool = False
    ) -> Optional["DownloadSection"]:
        """The section `start` and `end` name; None when both are empty (the
        whole video). Raises ValueError for a bad time or an end before the
        start."""
        start_seconds, end_seconds = parse_time(start), parse_time(end)
        if start_seconds is None and end_seconds is None:
            return None
        if end_seconds is not None and end_seconds <= (start_seconds or 0):
            raise ValueError("The end must come after the start.")
        return cls(start_seconds or 0.0, end_seconds, exact)

    def label(self) -> str:
        """For file names and messages: "1:00-5:00", "1:00-end"."""
        end = clock(self.end) if self.end is not None else "end"
        return f"{clock(self.start)}-{end}"

    def file_label(self) -> str:
        """`label` without colons, which Windows refuses in file names."""
        return self.label().replace(":", ".")

    def ydl_options(self) -> dict[str, Any]:
        """yt-dlp's options for this section."""
        from yt_dlp.utils import (  # type: ignore[import-untyped]  # yt-dlp ships no stubs
            download_range_func,
        )

        end = self.end if self.end is not None else float("inf")
        return {
            "download_ranges": download_range_func(None, [(self.start, end)]),
            "force_keyframes_at_cuts": self.exact,
        }
