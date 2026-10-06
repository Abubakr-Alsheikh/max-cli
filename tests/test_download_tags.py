"""core/engines/download_tags.py: the tags and folders a download gets, and
the repair of the ID3v1 tag that gave every downloaded song track 63."""

from pathlib import Path
from typing import Any

import pytest

from max_cli.core.engines.audio_metadata_engine import AudioMetadataEngine
from max_cli.core.engines.download_tags import (
    DownloadTags,
    fix_id3v1,
    output_template,
    v1_track_is_comment,
)

MP3_FRAME = b"\xff\xfb\x90\x64" + b"\x00" * 413
MP3_FRAME_COUNT = 5
# What ffmpeg writes into the 30-byte ID3v1 comment of a YouTube download.
YOUTUBE_COMMENT = b"https://www.youtube.com/watch?"
QUESTION_MARK = 63


def _playlist_entry(**fields: Any) -> dict[str, Any]:
    info = {
        "id": "abc",
        "title": "A.L.I.S.O.N - Before I Go",
        "ext": "mp3",
        "uploader": "Electronic Gems",
        "playlist_title": "Electronic Gems Mix",
        "playlist_uploader": "Electronic Gems",
        "playlist_index": 3,
        "playlist_count": 43,
    }
    info.update(fields)
    return info


def _ffmpeg_metadata(info: dict[str, Any]) -> dict[str, str]:
    """The -metadata values yt-dlp's FFmpegMetadata would write for `info`."""
    from yt_dlp.postprocessor.ffmpeg import FFmpegMetadataPP

    options = list(FFmpegMetadataPP(None)._get_metadata_opts(info))
    return dict(value.split("=", 1) for flag, value in options if flag == "-metadata")


def _youtube_mp3(path: Path, title: str = "Song") -> Path:
    """An MP3 shaped like a yt-dlp download: ID3v2 title, ID3v1 with the link."""
    from mutagen.id3 import ID3, TIT2

    path.write_bytes(MP3_FRAME * MP3_FRAME_COUNT)
    tags = ID3()
    tags.add(TIT2(encoding=3, text=[title]))
    tags.save(path, v1=0)
    v1 = (
        b"TAG"
        + title.encode("latin1").ljust(30, b"\x00")
        + b"\x00" * 30  # artist
        + b"\x00" * 30  # album
        + b"2023"
        + YOUTUBE_COMMENT
        + b"\xff"  # genre
    )
    with path.open("ab") as handle:
        handle.write(v1)
    return path


# --- the tags --------------------------------------------------------------------


def test_a_playlist_gives_the_album_and_numbers_the_tracks():
    info = _playlist_entry()

    DownloadTags().apply(info)

    written = _ffmpeg_metadata(info)
    assert written["album"] == "Electronic Gems Mix"
    assert written["album_artist"] == "Electronic Gems"
    assert written["track"] == "3/43"
    assert written["artist"] == "A.L.I.S.O.N"
    assert written["title"] == "Before I Go"


def test_typed_tags_win_over_the_site_and_the_playlist():
    info = _playlist_entry(artist="Site Artist", album="Site Album")

    DownloadTags(artist="Me", album="Mine", genre="Synthwave", year="2024").apply(info)

    written = _ffmpeg_metadata(info)
    assert written["artist"] == "Me"
    assert written["album_artist"] == "Me"
    assert written["album"] == "Mine"
    assert written["genre"] == "Synthwave"
    assert written["date"] == "2024"


def test_a_typed_album_for_a_playlist_keeps_the_tracks_together():
    info = _playlist_entry()

    DownloadTags(album="Mine").apply(info)

    written = _ffmpeg_metadata(info)
    assert written["album"] == "Mine"
    assert written["album_artist"] == "Electronic Gems"
    assert written["artist"] == "A.L.I.S.O.N"


def test_the_sites_own_artist_and_album_stay():
    info = _playlist_entry(artist="Real Artist", album="Real Album")

    DownloadTags().apply(info)

    written = _ffmpeg_metadata(info)
    assert written["artist"] == "Real Artist"
    assert written["album"] == "Real Album"
    assert written["title"] == "A.L.I.S.O.N - Before I Go"


def test_track_numbers_can_be_turned_off():
    info = _playlist_entry()

    DownloadTags(track_numbers=False).apply(info)

    assert "track" not in _ffmpeg_metadata(info)


def test_title_splitting_can_be_turned_off():
    info = _playlist_entry()

    DownloadTags(split_title=False).apply(info)

    written = _ffmpeg_metadata(info)
    assert written["title"] == "A.L.I.S.O.N - Before I Go"
    assert written["artist"] == "Electronic Gems"


def test_a_single_video_gets_no_track_or_album():
    info = _playlist_entry(playlist_title=None, playlist_index=None, title="Song")

    DownloadTags().apply(info)

    written = _ffmpeg_metadata(info)
    assert "track" not in written
    assert "album" not in written


# --- the folders -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sort_into", "fields", "expected"),
    [
        ("none", {}, Path("A.L.I.S.O.N - Before I Go.mp3")),
        (
            "album",
            {},
            Path("Electronic Gems Mix", "A.L.I.S.O.N - Before I Go.mp3"),
        ),
        (
            "artist/album",
            {},
            Path(
                "Electronic Gems",
                "Electronic Gems Mix",
                "A.L.I.S.O.N - Before I Go.mp3",
            ),
        ),
        (
            "artist/album",
            {"playlist_title": None, "playlist_index": None},
            Path("A.L.I.S.O.N", "A.L.I.S.O.N - Before I Go.mp3"),
        ),
        (
            "album",
            {"playlist_title": None, "playlist_index": None},
            Path("A.L.I.S.O.N - Before I Go.mp3"),
        ),
    ],
)
def test_downloads_sort_into_album_and_artist_folders(
    tmp_path, sort_into, fields, expected
):
    import yt_dlp

    info = _playlist_entry(**fields)
    DownloadTags(sort_into=sort_into).apply(info)
    ydl = yt_dlp.YoutubeDL(
        {"outtmpl": str(tmp_path / output_template(sort_into)), "quiet": True}
    )

    assert Path(ydl.prepare_filename(info)).resolve() == (tmp_path / expected).resolve()


def test_a_slash_in_an_album_name_makes_no_extra_folder(tmp_path):
    import yt_dlp

    info = _playlist_entry(album="AC/DC Live")
    DownloadTags(sort_into="album").apply(info)
    ydl = yt_dlp.YoutubeDL(
        {"outtmpl": str(tmp_path / output_template("album")), "quiet": True}
    )

    saved = Path(ydl.prepare_filename(info))

    assert saved.parent.parent == tmp_path


# --- ID3v1 ---------------------------------------------------------------------------


def test_the_link_in_the_id3v1_comment_reads_as_track_63(tmp_path):
    from mutagen.id3 import ID3

    song = _youtube_mp3(tmp_path / "song.mp3")

    assert v1_track_is_comment(song)
    assert str(ID3(song)["TRCK"]) == str(QUESTION_MARK)


def test_fix_id3v1_removes_the_false_track_and_keeps_the_tags(tmp_path):
    from mutagen.id3 import ID3

    song = _youtube_mp3(tmp_path / "song.mp3", title="Cycles")

    changed = fix_id3v1(song)

    tags = ID3(song)
    assert changed
    assert not v1_track_is_comment(song)
    assert "TRCK" not in tags
    assert str(tags["TIT2"]) == "Cycles"
    assert song.read_bytes()[-128:].startswith(b"TAG")
    assert fix_id3v1(song) is False  # nothing left to repair


def test_fix_id3v1_leaves_other_files_alone(tmp_path):
    flac = tmp_path / "song.flac"
    flac.write_bytes(b"fLaC" + b"\x00" * 200)
    short = tmp_path / "short.mp3"
    short.write_bytes(b"TAG")

    assert fix_id3v1(flac) is False
    assert fix_id3v1(short) is False


def test_the_audio_engine_ignores_the_false_track(tmp_path):
    song = _youtube_mp3(tmp_path / "song.mp3")
    engine = AudioMetadataEngine()

    shown = engine.get_metadata(song)
    engine.set_metadata(song, album="Electronic Gems")

    assert "tracknumber" not in shown
    after = engine.get_metadata(song)
    assert "tracknumber" not in after
    assert after["album"] == "Electronic Gems"
    assert not v1_track_is_comment(song)


def test_a_real_track_number_stays(tmp_path):
    song = _youtube_mp3(tmp_path / "song.mp3")
    engine = AudioMetadataEngine()

    engine.set_metadata(song, tracknumber="7")

    assert engine.get_metadata(song)["tracknumber"] == "7"
