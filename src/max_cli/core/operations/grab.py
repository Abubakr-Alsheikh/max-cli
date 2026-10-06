"""`max grab` operations: look at a link, and download it.

Used by the dashboard's Download page, the Tools page and (later) the CLI and
the AI agent. Nothing here prompts or prints. See PLANS/active/grab-page-redesign.md.
"""

import dataclasses
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from max_cli.common.exceptions import ValidationError
from max_cli.core.operations.result import ActionResult
from max_cli.core.presets import DOWNLOAD_SORT_CHOICES, DOWNLOAD_SORT_NONE

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
# Above this frame rate the label says so: 1080p60.
SMOOTH_FPS = 30
# yt-dlp lists YouTube's live chat replay as a subtitle track.
NOT_SUBTITLES = frozenset({"live_chat"})


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
    fps: Optional[int] = None

    @property
    def label(self) -> str:
        name = "4K" if self.height >= 2160 else f"{self.height}p"
        return f"{name}{self.fps}" if self.fps and self.fps > SMOOTH_FPS else name

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
    audio_codec: str = ""
    audio_bitrate: Optional[int] = None  # kbps of the best audio track
    site: str = ""  # e.g. youtube.com
    upload_date: str = ""  # 2024-05-01
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    subtitle_languages: list[str] = field(default_factory=list)
    has_auto_captions: bool = False
    chapter_count: int = 0
    is_live: bool = False

    @property
    def total_duration(self) -> Optional[float]:
        """A playlist's length when every item says how long it is."""
        if not self.is_playlist:
            return self.duration
        durations = [entry.duration for entry in self.entries]
        if not durations or None in durations:
            return None
        return float(sum(d for d in durations if d))


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


def _best_audio(formats: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    audio_only = [
        fmt
        for fmt in formats
        if fmt.get("vcodec") == "none" and fmt.get("acodec") not in (None, "none")
    ]
    return max(audio_only, key=lambda fmt: fmt.get("abr") or 0, default=None)


def _qualities(
    formats: list[dict[str, Any]],
) -> tuple[list[QualityOption], Optional[int]]:
    """One option per video height (largest first), plus the best audio's size."""
    best_audio = _best_audio(formats)
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
        fps = best_by_height[height].get("fps")
        options.append(
            QualityOption(
                height=height, size_bytes=total, fps=round(fps) if fps else None
            )
        )
    return options, audio_size


def _upload_date(raw: Any) -> str:
    """yt-dlp's 20240501 as 2024-05-01."""
    text = str(raw or "")
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}" if len(text) == 8 else ""


def _site(url: str, info: dict[str, Any]) -> str:
    from urllib.parse import urlparse

    domain = info.get("webpage_url_domain") or urlparse(url).netloc
    return str(domain).removeprefix("www.") if domain else ""


def _count(value: Any) -> Optional[int]:
    return int(value) if isinstance(value, (int, float)) else None


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
            site=_site(url, info),
            view_count=_count(info.get("view_count")),
        )
    formats = info.get("formats") or []
    qualities, audio_size = _qualities(formats)
    best_audio = _best_audio(formats) or {}
    codec = str(best_audio.get("acodec") or "")
    return MediaInfo(
        url=url,
        title=info.get("title") or url,
        uploader=info.get("uploader") or info.get("channel") or "",
        duration=info.get("duration"),
        qualities=qualities,
        audio_size_bytes=audio_size,
        # "mp4a.40.2" is AAC's full name; the part before the dot is enough.
        audio_codec=codec.split(".")[0],
        audio_bitrate=_count(best_audio.get("abr")),
        site=_site(url, info),
        upload_date=_upload_date(info.get("upload_date")),
        view_count=_count(info.get("view_count")),
        like_count=_count(info.get("like_count")),
        subtitle_languages=sorted(set(info.get("subtitles") or {}) - NOT_SUBTITLES),
        has_auto_captions=bool(info.get("automatic_captions")),
        chapter_count=len(info.get("chapters") or []),
        is_live=info.get("live_status") == "is_live",
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


def _text_or_none(value: Optional[str]) -> Optional[str]:
    text = (value or "").strip()
    return text or None


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
    artist: Optional[str] = None,
    album: Optional[str] = None,
    genre: Optional[str] = None,
    year: Optional[str] = None,
    track_numbers: bool = True,
    split_title: bool = True,
    sort_into: str = DOWNLOAD_SORT_NONE,
    *,
    engine: Optional["NetworkEngine"] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    progress_hook: Optional[Callable[[dict[str, Any]], None]] = None,
    record_history: bool = True,
) -> ActionResult:
    """Download `url`. Options left as None use the user's grab settings.

    `artist`, `album`, `genre` and `year` go into every file; empty ones keep
    what the site says, and a playlist's name becomes the album when the site
    names none. `track_numbers` numbers a playlist's files by their place in
    it, `split_title` reads the artist from titles like "Artist - Song", and
    `sort_into` saves into Album or Artist/Album folders.

    Raises OperationCancelled when `should_cancel` returns True mid-download.
    """
    from max_cli.config import settings
    from max_cli.core.engines.download_tags import DownloadTags
    from max_cli.core.engines.network_engine import strip_playlist_params

    url = url.strip()
    if not url:
        raise ValidationError("Paste a link first.")
    output = output or settings.GRAB_DEFAULT_PATH
    media_type = media_type or settings.GRAB_DEFAULT_TYPE
    if media_type not in MEDIA_TYPES:
        raise ValidationError(f"media_type must be one of {', '.join(MEDIA_TYPES)}")
    quality = quality or settings.GRAB_QUALITY
    if sort_into not in DOWNLOAD_SORT_CHOICES:
        choices = ", ".join(DOWNLOAD_SORT_CHOICES)
        raise ValidationError(f"sort_into must be one of {choices}")
    tags = DownloadTags(
        artist=_text_or_none(artist),
        album=_text_or_none(album),
        genre=_text_or_none(genre),
        year=_text_or_none(year),
        track_numbers=track_numbers,
        split_title=split_title,
        sort_into=sort_into,
    )
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
        tags=tags,
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
            settings_used={
                **options,
                **dataclasses.asdict(tags),
                "output_path": str(output),
            },
            file_size=total_size,
        )

    return ActionResult(
        ok=True,
        message=f"Downloaded: {title}",
        output_files=files,
        details={"title": title, "url": url, "size_bytes": total_size},
    )


# --- the YouTube fix (`max grab pot-setup`) ----------------------------------

INSTALL_OUTPUT_TAIL = 800
DENO_HINT = "Install Deno first (winget install DenoLand.Deno), then restart max."


@dataclass
class YoutubeFixStatus:
    """Whether the PO token provider that gets past YouTube's HTTP 403 is set up."""

    installed: bool
    deno_found: bool


def youtube_fix_status(*, engine: Optional["NetworkEngine"] = None) -> YoutubeFixStatus:
    import shutil

    return YoutubeFixStatus(
        installed=_engine(engine).pot_provider_available(),
        deno_found=shutil.which("deno") is not None,
    )


def install_youtube_fix(*, engine: Optional["NetworkEngine"] = None) -> ActionResult:
    """Install the bgutil PO token provider: a yt-dlp plugin plus its Deno server.

    Takes minutes. The CLI's `max grab pot-setup` asks before each step; the
    dashboard asks once before calling this.
    """
    import shutil

    from max_cli.common.exceptions import ProcessingError

    network = _engine(engine)
    if not shutil.which("deno"):
        raise ValidationError(DENO_HINT)
    if network.pot_provider_available():
        return ActionResult(True, "The YouTube fix is already installed.")
    for step, run in (
        ("Installing the yt-dlp plugin", network.install_pot_provider),
        ("Setting up the token server", network.setup_pot_server),
    ):
        outcome = run()
        if not outcome["ok"]:
            raise ProcessingError(
                f"{step} failed:\n{outcome['output'][-INSTALL_OUTPUT_TAIL:]}"
            )
    if not network.pot_provider_available():
        raise ProcessingError(
            "Installed, but yt-dlp doesn't see the provider yet. Restart max and "
            "try again, or run `max grab pot-setup` in a terminal."
        )
    return ActionResult(
        True, "YouTube fix installed. Blocked downloads should work now."
    )
