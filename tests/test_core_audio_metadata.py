"""AudioMetadataEngine tests on real, tiny audio files built without network.

FLAC files are hand-built (fLaC marker + STREAMINFO block), WAV files come from
the stdlib `wave` module and MP3 files are a run of silent MPEG frames. Mutagen
reads all three, so the engine runs against the real library.
"""

import struct
import wave
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from max_cli.core.engines.audio_metadata_engine import (
    AudioMetadataEngine,
    find_audio_files,
)

SAMPLE_RATE = 8000
FLAC_BLOCK_SIZE = 4096
FLAC_BITS_PER_SAMPLE = 16
STREAMINFO_LAST_BLOCK = 0x80
MP3_FRAME = b"\xff\xfb\x90\x64" + b"\x00" * 413
MP3_FRAME_COUNT = 5


def make_flac(path: Path, sample_count: int = SAMPLE_RATE) -> Path:
    """Write a metadata-only FLAC file lasting sample_count / SAMPLE_RATE seconds."""
    packed_fields = (
        (SAMPLE_RATE << 44)
        | (0 << 41)  # channels - 1
        | ((FLAC_BITS_PER_SAMPLE - 1) << 36)
        | sample_count
    )
    stream_info = (
        struct.pack(">HH", FLAC_BLOCK_SIZE, FLAC_BLOCK_SIZE)
        + b"\x00" * 6
        + packed_fields.to_bytes(8, "big")
        + b"\x00" * 16
    )
    block_header = bytes([STREAMINFO_LAST_BLOCK]) + len(stream_info).to_bytes(3, "big")
    path.write_bytes(b"fLaC" + block_header + stream_info)
    return path


def make_wav(path: Path) -> Path:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(b"\x00\x00" * SAMPLE_RATE)
    return path


def make_mp3(path: Path) -> Path:
    path.write_bytes(MP3_FRAME * MP3_FRAME_COUNT)
    return path


def read_flac_tags(path: Path) -> Dict[str, List[str]]:
    from mutagen.flac import FLAC

    tags = FLAC(path).tags
    return {key.lower(): list(values) for key, values in (tags or {}).items()}


@pytest.fixture
def engine() -> AudioMetadataEngine:
    return AudioMetadataEngine()


@pytest.fixture
def flac_file(tmp_path: Path) -> Path:
    return make_flac(tmp_path / "song.flac")


# --- find_audio_files --------------------------------------------------------


def test_find_audio_files_returns_supported_files_sorted(tmp_path):
    for name in ["b.mp3", "a.FLAC", "c.wav", "notes.txt", "cover.jpg"]:
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "nested.mp3").mkdir()
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.mp3").write_bytes(b"x")

    found = find_audio_files(tmp_path)

    assert [path.name for path in found] == ["a.FLAC", "b.mp3", "c.wav"]


def test_find_audio_files_empty_folder(tmp_path):
    assert find_audio_files(tmp_path) == []


# --- get_metadata ------------------------------------------------------------


def test_get_metadata_missing_file_raises(engine, tmp_path):
    with pytest.raises(FileNotFoundError):
        engine.get_metadata(tmp_path / "missing.mp3")


def test_get_metadata_unsupported_extension_raises(engine, tmp_path):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("hello", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported format"):
        engine.get_metadata(text_file)


def test_get_metadata_unrecognised_content_raises(engine, tmp_path):
    fake_ogg = tmp_path / "fake.ogg"
    fake_ogg.write_text("not audio at all", encoding="utf-8")

    with pytest.raises(ValueError, match="Unable to read metadata"):
        engine.get_metadata(fake_ogg)


def test_get_metadata_reads_wav_stream_info(engine, tmp_path):
    metadata = engine.get_metadata(make_wav(tmp_path / "tone.wav"))

    assert metadata["duration"] == 1.0
    assert metadata["sample_rate"] == SAMPLE_RATE
    assert metadata["channels"] == 1


def test_get_metadata_maps_id3_frames_to_friendly_names(engine, tmp_path):
    from mutagen.id3 import APIC, ID3, TALB, TCON, TIT2, TPE1, TPE2, TXXX

    mp3_path = make_mp3(tmp_path / "track.mp3")
    id3_tags = ID3()
    id3_tags.add(TIT2(encoding=3, text="Song"))
    id3_tags.add(TPE1(encoding=3, text="Singer"))
    id3_tags.add(TALB(encoding=3, text="Record"))
    id3_tags.add(TPE2(encoding=3, text="Band"))
    id3_tags.add(TCON(encoding=3, text="Jazz"))
    id3_tags.add(TXXX(encoding=3, desc="mood", text="calm"))
    id3_tags.add(APIC(encoding=3, mime="image/png", type=3, desc="", data=b"png"))
    id3_tags.save(mp3_path)

    metadata = engine.get_metadata(mp3_path)

    assert metadata["title"] == "Song"
    assert metadata["artist"] == "Singer"
    assert metadata["album"] == "Record"
    assert metadata["albumartist"] == "Band"
    assert metadata["genre"] == "Jazz"
    assert metadata["TXXX:mood"] == "calm"
    assert not any(key.startswith("APIC") for key in metadata)
    assert metadata["sample_rate"] == 44100


def test_get_metadata_returns_plain_strings_for_flac(engine, flac_file):
    engine.set_metadata(flac_file, title="T")

    assert engine.get_metadata(flac_file)["title"] == "T"


# --- set_metadata ------------------------------------------------------------


def test_set_metadata_writes_all_fields_to_flac(engine, flac_file):
    result = engine.set_metadata(
        flac_file,
        title="Title",
        artist="Artist",
        album="Album",
        albumartist="Album Artist",
        genre="Rock",
        date="2024",
        tracknumber="3",
        discnumber="1",
        composer="Composer",
        comment="Nice",
    )

    assert result == flac_file
    assert read_flac_tags(flac_file) == {
        "title": ["Title"],
        "artist": ["Artist"],
        "album": ["Album"],
        "albumartist": ["Album Artist"],
        "genre": ["Rock"],
        "date": ["2024"],
        "tracknumber": ["3"],
        "discnumber": ["1"],
        "composer": ["Composer"],
        "comment": ["Nice"],
    }


def test_set_metadata_leaves_unspecified_fields_alone(engine, flac_file):
    engine.set_metadata(flac_file, title="Old", artist="Kept")

    engine.set_metadata(flac_file, title="New")

    assert read_flac_tags(flac_file) == {"title": ["New"], "artist": ["Kept"]}


def test_set_metadata_missing_file_raises(engine, tmp_path):
    with pytest.raises(FileNotFoundError):
        engine.set_metadata(tmp_path / "missing.flac", title="x")


def test_set_metadata_unsupported_extension_raises(engine, tmp_path):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("hello", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported format"):
        engine.set_metadata(text_file, title="x")


@pytest.mark.parametrize("builder", [make_mp3, make_wav], ids=["mp3", "wav"])
def test_set_metadata_on_id3_formats(engine, tmp_path, builder):
    suffix = ".mp3" if builder is make_mp3 else ".wav"
    audio_path = builder(tmp_path / f"track{suffix}")

    engine.set_metadata(audio_path, title="x")

    assert engine.get_metadata(audio_path)["title"] == "x"


def test_set_metadata_to_new_output_path(engine, flac_file, tmp_path):
    output_path = tmp_path / "copy.flac"

    engine.set_metadata(flac_file, output_path=output_path, title="Copy")

    assert read_flac_tags(output_path) == {"title": ["Copy"]}


# --- clear_metadata ----------------------------------------------------------


def test_clear_metadata_removes_tags_and_keeps_stream_info(engine, flac_file):
    engine.set_metadata(flac_file, title="T", artist="A", album="Al")

    result = engine.clear_metadata(flac_file)

    assert result == flac_file
    assert read_flac_tags(flac_file) == {}
    metadata = engine.get_metadata(flac_file)
    assert "title" not in metadata
    assert metadata["duration"] == 1.0


def test_clear_metadata_missing_file_raises(engine, tmp_path):
    with pytest.raises(FileNotFoundError):
        engine.clear_metadata(tmp_path / "missing.flac")


def test_clear_metadata_unsupported_extension_raises(engine, tmp_path):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("hello", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported format"):
        engine.clear_metadata(text_file)


# --- batch_set_metadata ------------------------------------------------------


def test_batch_set_metadata_tags_every_file(engine, tmp_path):
    paths = [make_flac(tmp_path / f"track{index}.flac") for index in range(3)]

    results = engine.batch_set_metadata(paths, album="Shared", genre="Pop")

    assert results == paths
    for path in paths:
        assert read_flac_tags(path) == {"album": ["Shared"], "genre": ["Pop"]}


def test_batch_set_metadata_wraps_failure_with_path(engine, tmp_path):
    good_path = make_flac(tmp_path / "good.flac")
    missing_path = tmp_path / "missing.flac"

    with pytest.raises(RuntimeError, match="missing.flac"):
        engine.batch_set_metadata([good_path, missing_path], album="X")

    assert read_flac_tags(good_path) == {"album": ["X"]}


# --- auto_tag_from_filename --------------------------------------------------


def test_auto_tag_splits_artist_and_title(engine, tmp_path):
    audio_path = make_flac(tmp_path / "Daft Punk - One More Time.flac")

    engine.auto_tag_from_filename(audio_path)

    assert read_flac_tags(audio_path) == {
        "artist": ["Daft Punk"],
        "title": ["One More Time"],
    }


def test_auto_tag_without_separator_sets_title_only(engine, tmp_path):
    audio_path = make_flac(tmp_path / "Intro.flac")

    engine.auto_tag_from_filename(audio_path)

    assert read_flac_tags(audio_path) == {"title": ["Intro"]}


def test_auto_tag_missing_file_raises(engine, tmp_path):
    with pytest.raises(FileNotFoundError):
        engine.auto_tag_from_filename(tmp_path / "A - B.flac")


def test_auto_tag_handles_track_artist_title(engine, tmp_path):
    audio_path = make_flac(tmp_path / "01 - Artist - Title.flac")

    engine.auto_tag_from_filename(audio_path)

    tags = read_flac_tags(audio_path)
    assert tags["artist"] == ["Artist"]
    assert tags["title"] == ["Title"]


# --- organize ----------------------------------------------------------------


def _engine_with_metadata(
    monkeypatch, metadata_by_name: Dict[str, Dict[str, Any]]
) -> AudioMetadataEngine:
    """Engine whose get_metadata returns canned tags keyed by file name."""
    engine = AudioMetadataEngine()

    def fake_get_metadata(file_path: Path) -> Dict[str, Any]:
        return dict(metadata_by_name.get(file_path.name, {}))

    monkeypatch.setattr(engine, "get_metadata", fake_get_metadata)
    return engine


def _make_sources(source_dir: Path, names: List[str]) -> List[Path]:
    source_dir.mkdir(exist_ok=True)
    paths = []
    for name in names:
        path = source_dir / name
        path.write_bytes(b"audio")
        paths.append(path)
    return paths


TAGGED = {
    "a.mp3": {
        "artist": "Adele",
        "album": "25",
        "genre": "Pop",
        "title": "Hello",
    },
}


@pytest.mark.parametrize(
    "pattern, expected_relative",
    [
        ("artist", Path("Adele") / "Hello.mp3"),
        ("album", Path("25") / "Hello.mp3"),
        ("genre", Path("Pop") / "Hello.mp3"),
        ("artist-album", Path("Adele") / "25" / "Hello.mp3"),
        ("contributing-artists", Path("Adele") / "Hello.mp3"),
    ],
)
def test_organize_patterns(monkeypatch, tmp_path, pattern, expected_relative):
    engine = _engine_with_metadata(monkeypatch, TAGGED)
    sources = _make_sources(tmp_path / "in", ["a.mp3"])
    target_dir = tmp_path / "out"

    result = engine.organize(sources, target_dir, pattern=pattern)

    assert result["total_moved"] == 1
    assert result["total_errors"] == 0
    assert (target_dir / expected_relative).read_bytes() == b"audio"
    assert not sources[0].exists()


def test_organize_uses_unknown_placeholders(monkeypatch, tmp_path):
    engine = _engine_with_metadata(monkeypatch, {})
    sources = _make_sources(tmp_path / "in", ["untagged.mp3"])
    target_dir = tmp_path / "out"

    engine.organize(sources, target_dir, pattern="artist-album")

    assert (target_dir / "Unknown Artist" / "Unknown Album" / "untagged.mp3").exists()


@pytest.mark.parametrize(
    "file_name, metadata, expected_folder",
    [
        ("x.mp3", {"albumartist": "Band", "artist": "Solo"}, "Band"),
        ("x.mp3", {"artist": "Solo"}, "Solo"),
        ("x.mp3", {"title": "Guest - Song"}, "Guest"),
        ("Stem Artist - Song.mp3", {}, "Stem Artist"),
        ("x.mp3", {}, "Unknown Artist"),
    ],
)
def test_organize_contributing_artists_fallback_chain(
    monkeypatch, tmp_path, file_name, metadata, expected_folder
):
    engine = _engine_with_metadata(monkeypatch, {file_name: metadata})
    sources = _make_sources(tmp_path / "in", [file_name])
    target_dir = tmp_path / "out"

    engine.organize(sources, target_dir, pattern="contributing-artists")

    moved_files = list((target_dir / expected_folder).iterdir())
    assert len(moved_files) == 1


def test_organize_filter_value_skips_other_folders(monkeypatch, tmp_path):
    engine = _engine_with_metadata(
        monkeypatch,
        {"a.mp3": {"artist": "Keep"}, "b.mp3": {"artist": "Skip"}},
    )
    sources = _make_sources(tmp_path / "in", ["a.mp3", "b.mp3"])
    target_dir = tmp_path / "out"

    result = engine.organize(sources, target_dir, filter_value="Keep")

    assert result["total_moved"] == 1
    assert result["total_skipped"] == 1
    assert result["skipped"] == ["b.mp3 (filter: Keep)"]
    assert sources[1].exists()
    assert not (target_dir / "Skip").exists()


def test_organize_renames_on_collision(monkeypatch, tmp_path):
    engine = _engine_with_metadata(
        monkeypatch,
        {"a.mp3": {"artist": "X", "title": "Same"}},
    )
    target_dir = tmp_path / "out"
    (target_dir / "X").mkdir(parents=True)
    (target_dir / "X" / "Same.mp3").write_bytes(b"existing")
    (target_dir / "X" / "Same (1).mp3").write_bytes(b"existing")
    sources = _make_sources(tmp_path / "in", ["a.mp3"])

    engine.organize(sources, target_dir)

    assert (target_dir / "X" / "Same (2).mp3").read_bytes() == b"audio"
    assert (target_dir / "X" / "Same.mp3").read_bytes() == b"existing"


def test_organize_sanitizes_folder_and_file_names(monkeypatch, tmp_path):
    engine = _engine_with_metadata(
        monkeypatch,
        {"a.mp3": {"artist": "AC/DC", "title": 'What? "Now"'}},
    )
    sources = _make_sources(tmp_path / "in", ["a.mp3"])
    target_dir = tmp_path / "out"

    engine.organize(sources, target_dir)

    assert (target_dir / "AC_DC" / "What_ _Now_.mp3").exists()


def test_organize_reports_missing_and_failing_files(monkeypatch, tmp_path):
    engine = AudioMetadataEngine()

    def failing_get_metadata(file_path: Path) -> Dict[str, Any]:
        raise ValueError("corrupt")

    monkeypatch.setattr(engine, "get_metadata", failing_get_metadata)
    sources = _make_sources(tmp_path / "in", ["bad.mp3"])
    missing = tmp_path / "in" / "gone.mp3"

    result = engine.organize([missing, *sources], tmp_path / "out")

    assert result["total_moved"] == 0
    assert result["errors"] == ["gone.mp3: File not found", "bad.mp3: corrupt"]
    assert sources[0].exists()


def test_organize_records_moves_in_transaction_log(monkeypatch, tmp_path):
    from max_cli.common.transaction_log import TransactionLog

    engine = _engine_with_metadata(monkeypatch, TAGGED)
    sources = _make_sources(tmp_path / "in", ["a.mp3"])
    target_dir = tmp_path / "out"
    transaction_log = MagicMock()

    engine.organize(sources, target_dir, transaction_log=transaction_log)

    transaction_log.record.assert_called_once_with(
        op_type=TransactionLog.OP_MOVE,
        original_path=sources[0],
        new_path=target_dir / "Adele" / "Hello.mp3",
    )


def test_organize_real_flac_by_artist(engine, tmp_path):
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    audio_path = make_flac(source_dir / "track.flac")
    engine.set_metadata(audio_path, artist="Artist", title="Song")
    target_dir = tmp_path / "out"

    engine.organize([audio_path], target_dir, pattern="artist")

    assert (target_dir / "Artist" / "Song.flac").exists()


def test_sanitize_filename_empty_values(engine):
    assert engine._sanitize_filename("") == "Unknown"
    assert engine._sanitize_filename("   ") == "Unknown"
    assert engine._sanitize_filename('a<b>c:d"e|f?g*h\\i') == "a_b_c_d_e_f_g_h_i"
