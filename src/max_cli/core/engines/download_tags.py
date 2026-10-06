"""Tags and folders for downloads: artist, album, track numbers, Artist/Album.

`DownloadTags.apply` fills the fields yt-dlp's FFmpegMetadata writes into the
file, before yt-dlp names it, so the same fields can sort the files into
folders. `fix_id3v1` repairs the old ID3v1 tag ffmpeg adds to MP3s.

Why ID3v1 needs a repair: ffmpeg writes the link into its 30-byte comment.
`https://www.youtube.com/watch?` fills all 30 bytes, and ID3v1.1 readers
(mutagen, Windows Explorer) take the last byte as the track number: "?" is
63, so every downloaded song showed track 63.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from max_cli.core.presets import (
    DOWNLOAD_SORT_ALBUM,
    DOWNLOAD_SORT_ARTIST_ALBUM,
    DOWNLOAD_SORT_NONE,
)

# yt-dlp output fields for the two folder levels. A missing field becomes ".",
# the same folder, so a file without an album stays one level up.
FOLDER_FIELDS = ("max_folder_1", "max_folder_2")
TITLE_SEPARATOR = " - "
# DownloadTags' fields, as a queued download's payload keeps them.
TAG_OPTION_KEYS = (
    "artist",
    "album",
    "genre",
    "year",
    "track_numbers",
    "split_title",
    "sort_into",
)

ID3V1_SIZE = 128
ID3V1_MARKER = b"TAG"
# ID3v1.1 keeps this byte zero and the track number in the next one. In
# ID3v1.0 both belong to the comment.
ID3V1_TRACK_FLAG = 125
ID3V2_VERSIONS = (3, 4)


def output_template(sort_into: str) -> str:
    """yt-dlp's output template, relative to the download folder."""
    if sort_into == DOWNLOAD_SORT_NONE:
        return "%(title)s.%(ext)s"
    folders = "/".join(f"%({name}|.)s" for name in FOLDER_FIELDS)
    return f"{folders}/%(title)s.%(ext)s"


@dataclass(frozen=True)
class DownloadTags:
    """What to write into downloaded files. None keeps what the site says."""

    artist: Optional[str] = None
    album: Optional[str] = None
    genre: Optional[str] = None
    year: Optional[str] = None
    # Number a playlist's files by their place in it ("3/43").
    track_numbers: bool = True
    # A title such as "Artist - Song" gives the artist, when the site names none.
    split_title: bool = True
    sort_into: str = DOWNLOAD_SORT_NONE

    def apply(self, info: dict[str, Any]) -> None:
        """Set `info`'s fields for FFmpegMetadata and the output template."""
        site_artist = info.get("artist") or info.get("artists") or info.get("creator")
        if self.split_title and not site_artist and not self.artist:
            artist, song = _split_title(info.get("track") or info.get("title") or "")
            if artist:
                info["artist"] = artist
                info["track"] = song  # FFmpegMetadata writes it as the title
        if self.artist:
            info["artist"] = self.artist
            info["album_artist"] = self.artist

        from_playlist = False
        if self.album:
            info["album"] = self.album
        elif not info.get("album") and info.get("playlist_title"):
            info["album"] = info["playlist_title"]
            from_playlist = True
        # One album artist keeps a playlist's tracks together in music players.
        album_is_ours = bool(self.album) or from_playlist
        if (
            album_is_ours
            and info.get("playlist_title")
            and not info.get("album_artist")
        ):
            owner = info.get("playlist_uploader") or info.get("playlist_channel")
            if owner:
                info["album_artist"] = owner

        if self.genre:
            info["genre"] = self.genre
        if self.year:
            info["meta_date"] = self.year

        index = info.get("playlist_index")
        if self.track_numbers and index:
            total = info.get("playlist_count") or info.get("n_entries")
            info["track_number"] = int(index)
            info["meta_track"] = f"{index}/{total}" if total else str(index)

        if self.sort_into == DOWNLOAD_SORT_ARTIST_ALBUM:
            artist = (
                info.get("album_artist")
                or info.get("artist")
                or info.get("creator")
                or info.get("uploader")
            )
            _set_folders(info, artist, info.get("album"))
        elif self.sort_into == DOWNLOAD_SORT_ALBUM:
            _set_folders(info, info.get("album"), None)


def _split_title(title: str) -> tuple[Optional[str], str]:
    """("Artist", "Song") from "Artist - Song"; (None, title) otherwise."""
    artist, separator, song = title.partition(TITLE_SEPARATOR)
    if not separator or not artist.strip() or not song.strip():
        return None, title
    return artist.strip(), song.strip()


def _set_folders(info: dict[str, Any], first: Any, second: Any) -> None:
    for name, value in zip(FOLDER_FIELDS, (first, second)):
        if value:
            info[name] = ", ".join(value) if isinstance(value, list) else str(value)


def postprocessors(tags: DownloadTags) -> tuple[Any, Any]:
    """Two yt-dlp PostProcessors: one runs `tags.apply` before each download
    (add it `when="pre_process"`), one runs `fix_id3v1` on each finished file
    (`when="post_process"`, after FFmpegMetadata)."""
    from yt_dlp.postprocessor.common import (  # type: ignore[import-untyped]  # yt-dlp ships no stubs
        PostProcessor,
    )

    class _ApplyTags(PostProcessor):
        def run(self, info: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
            tags.apply(info)
            return [], info

    class _FixId3v1(PostProcessor):
        def run(self, info: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
            path = info.get("filepath")
            if path:
                fix_id3v1(Path(path))
            return [], info

    return _ApplyTags(), _FixId3v1()


def v1_track_is_comment(path: Path) -> bool:
    """True when `path` ends in an ID3v1.0 tag, whose last comment byte
    readers take for a track number (see the module docstring)."""
    if path.suffix.lower() != ".mp3":
        return False
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            if handle.tell() < ID3V1_SIZE:
                return False
            handle.seek(-ID3V1_SIZE, 2)
            data = handle.read(ID3V1_SIZE)
    except OSError:
        return False
    return data.startswith(ID3V1_MARKER) and data[ID3V1_TRACK_FLAG] != 0


def fix_id3v1(path: Path) -> bool:
    """Rewrite an MP3's ID3v1 tag from its ID3v2 tags, without the false track.

    Returns True when it changed the file.
    """
    if not v1_track_is_comment(path):
        return False
    from mutagen.id3 import ID3, ID3NoHeaderError, ID3v1SaveOptions

    try:
        tags = ID3(path, load_v1=False)
    except ID3NoHeaderError:
        tags = ID3()
    version = tags.version[1] if tags.version[1] in ID3V2_VERSIONS else 4
    tags.save(path, v1=ID3v1SaveOptions.CREATE, v2_version=version)
    return True
