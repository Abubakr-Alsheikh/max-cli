"""`max grab` operations: look at a link, and download it.

Used by the dashboard's Download page, the Tools page and (later) the CLI and
the AI agent. Nothing here prompts or prints. See PLANS/active/grab-page-redesign.md.
"""

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from max_cli.common.exceptions import ValidationError
from max_cli.core.operations.result import ActionResult

if TYPE_CHECKING:
    from max_cli.core.engines.network_engine import NetworkEngine

# Height -> the --quality code that asks for it. Other heights go through
# --resolution.
QUALITY_CODES = {360: "ss", 480: "s", 720: "m", 1080: "h", 2160: "x"}
# Same list as the CLI's --player-client (cli_network.PlayerClient).
PLAYER_CLIENTS = (
    "auto",
    "default",
    "web",
    "tv",
    "ios",
    "android",
    "mweb",
    "tv_embedded",
)
MEDIA_TYPES = ("video", "audio")
PROBE_CACHE_SIZE = 64


@dataclass
class PlaylistEntry:
    index: int  # 1-based, as yt-dlp's playlist_items expects
    title: str
    url: str
    duration: Optional[float] = None


@dataclass
class QualityOption:
    height: int
    size_bytes: Optional[int]  # video plus best audio; None when the site doesn't say

    @property
    def label(self) -> str:
        return "4K" if self.height >= 2160 else f"{self.height}p"

    @property
    def quality_code(self) -> Optional[str]:
        return QUALITY_CODES.get(self.height)


@dataclass
class MediaInfo:
    url: str
    title: str
    uploader: str = ""
    duration: Optional[float] = None
    is_playlist: bool = False
    entries: list[PlaylistEntry] = field(default_factory=list)
    qualities: list[QualityOption] = field(default_factory=list)
    audio_size_bytes: Optional[int] = None


_probe_cache: "OrderedDict[str, MediaInfo]" = OrderedDict()
_probe_lock = threading.Lock()


def _engine(engine: Optional["NetworkEngine"]) -> "NetworkEngine":
    if engine is not None:
        return engine
    from max_cli.core.engines.network_engine import NetworkEngine

    return NetworkEngine()


def _size(fmt: dict[str, Any]) -> Optional[int]:
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    return int(size) if size else None


def _qualities(
    formats: list[dict[str, Any]],
) -> tuple[list[QualityOption], Optional[int]]:
    """One option per video height (largest first), plus the best audio's size."""
    audio_only = [
        fmt
        for fmt in formats
        if fmt.get("vcodec") == "none" and fmt.get("acodec") not in (None, "none")
    ]
    best_audio = max(audio_only, key=lambda fmt: fmt.get("abr") or 0, default=None)
    audio_size = _size(best_audio) if best_audio else None

    best_by_height: dict[int, dict[str, Any]] = {}
    for fmt in formats:
        height = fmt.get("height")
        if not height or fmt.get("vcodec") in (None, "none"):
            continue
        current = best_by_height.get(height)
        if current is None or (fmt.get("tbr") or 0) > (current.get("tbr") or 0):
            best_by_height[height] = fmt

    options = []
    for height in sorted(best_by_height, reverse=True):
        video_size = _size(best_by_height[height])
        has_audio = best_by_height[height].get("acodec") not in (None, "none")
        total = video_size
        if video_size is not None and not has_audio and audio_size is not None:
            total = video_size + audio_size
        options.append(QualityOption(height=height, size_bytes=total))
    return options, audio_size


def _media_info(url: str, info: dict[str, Any]) -> MediaInfo:
    if info.get("_type") == "playlist":
        entries = [
            PlaylistEntry(
                index=position,
                title=entry.get("title") or f"Item {position}",
                url=entry.get("url") or entry.get("webpage_url") or "",
                duration=entry.get("duration"),
            )
            for position, entry in enumerate(info.get("entries") or [], start=1)
            if entry
        ]
        return MediaInfo(
            url=url,
            title=info.get("title") or url,
            uploader=info.get("uploader") or info.get("channel") or "",
            is_playlist=True,
            entries=entries,
        )
    qualities, audio_size = _qualities(info.get("formats") or [])
    return MediaInfo(
        url=url,
        title=info.get("title") or url,
        uploader=info.get("uploader") or info.get("channel") or "",
        duration=info.get("duration"),
        qualities=qualities,
        audio_size_bytes=audio_size,
    )


def probe(url: str, *, engine: Optional["NetworkEngine"] = None) -> MediaInfo:
    """What a link points to: a video with its qualities, or a playlist's items.

    Results are cached for the session, so the preview and the download don't
    ask the site twice.
    """
    url = url.strip()
    if not url:
        raise ValidationError("Paste a link first.")
    with _probe_lock:
        if url in _probe_cache:
            _probe_cache.move_to_end(url)
            return _probe_cache[url]

    media = _media_info(url, _engine(engine).probe_info(url))
    with _probe_lock:
        _probe_cache[url] = media
        while len(_probe_cache) > PROBE_CACHE_SIZE:
            _probe_cache.popitem(last=False)
    return media


def _cached_title(url: str) -> Optional[str]:
    with _probe_lock:
        media = _probe_cache.get(url)
    return media.title if media else None


def download(
    url: str,
    output: Optional[Path] = None,
    media_type: Optional[str] = None,
    quality: Optional[str] = None,
    resolution: Optional[int] = None,
    playlist_items: Optional[str] = None,
    no_playlist: bool = False,
    subtitles: bool = False,
    include_metadata: Optional[bool] = None,
    strip_playlist: Optional[bool] = None,
    player_client: str = "auto",
    *,
    engine: Optional["NetworkEngine"] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    progress_hook: Optional[Callable[[dict[str, Any]], None]] = None,
    record_history: bool = True,
) -> ActionResult:
    """Download `url`. Options left as None use the user's grab settings.

    Raises OperationCancelled when `should_cancel` returns True mid-download.
    """
    from max_cli.config import settings
    from max_cli.core.engines.network_engine import strip_playlist_params

    url = url.strip()
    if not url:
        raise ValidationError("Paste a link first.")
    output = output or settings.GRAB_DEFAULT_PATH
    media_type = media_type or settings.GRAB_DEFAULT_TYPE
    if media_type not in MEDIA_TYPES:
        raise ValidationError(f"media_type must be one of {', '.join(MEDIA_TYPES)}")
    quality = quality or settings.GRAB_QUALITY
    if include_metadata is None:
        include_metadata = settings.GRAB_INCLUDE_METADATA
    if strip_playlist is None:
        strip_playlist = settings.GRAB_STRIP_PLAYLIST
    if strip_playlist and not playlist_items and not no_playlist:
        url = strip_playlist_params(url)

    output.mkdir(parents=True, exist_ok=True)
    options: dict[str, Any] = {
        "quality": quality,
        "audio_only": media_type == "audio",
        "include_metadata": include_metadata,
        "playlist_items": playlist_items or None,
        "no_playlist": no_playlist,
        "subtitles": subtitles,
        "custom_height": resolution,
        "player_client": None if player_client == "auto" else player_client,
    }
    result = _engine(engine).download_media(
        url=url,
        output_path=output,
        progress_hook=progress_hook,
        should_cancel=should_cancel,
        **options,
    )
    files = [Path(path) for path in result.get("files", [])]
    total_size = sum(path.stat().st_size for path in files if path.is_file())
    title = _cached_title(url) or (files[0].stem if files else url)

    if record_history:
        from max_cli.core.engines.download_history import DownloadHistory

        DownloadHistory().record_download(
            url=url,
            title=title,
            output_files=[str(path) for path in files],
            settings_used={**options, "output_path": str(output)},
            file_size=total_size,
        )

    return ActionResult(
        ok=True,
        message=f"Downloaded: {title}",
        output_files=files,
        details={"title": title, "url": url, "size_bytes": total_size},
    )
