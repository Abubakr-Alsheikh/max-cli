"""`core/operations/audio.py` on real files: a few silent MP3 frames and a
short WAV, so mutagen reads and writes real tags. No FFmpeg needed."""

import wave
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from max_cli.common.exceptions import ResourceNotFoundError, ValidationError
from max_cli.core.operations import audio

# One MPEG-1 Layer III frame at 128 kbps, 44.1 kHz: a 4-byte header, then
# silence. Twenty of them make a 0.5 second file mutagen opens like any MP3.
MP3_FRAME = bytes([0xFF, 0xFB, 0x90, 0x64]) + bytes(413)
MP3_FRAMES = 20
WAV_RATE = 8000


def _mp3(path: Path) -> Path:
    path.write_bytes(MP3_FRAME * MP3_FRAMES)
    return path


def _wav(path: Path) -> Path:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(WAV_RATE)
        out.writeframes(bytes(WAV_RATE * 2))
    return path


@pytest.fixture
def song(tmp_path):
    return _mp3(tmp_path / "song.mp3")


# --- set and get -----------------------------------------------------------------


def test_every_tag_round_trips_on_an_mp3(song):
    """`set --comment` failed on MP3: mutagen's easy ID3 has no "comment"."""
    tags = {
        "title": "My Song",
        "artist": "Ana",
        "album": "Album X",
        "albumartist": "Various",
        "genre": "Pop",
        "date": "2024",
        "tracknumber": "3",
        "discnumber": "1",
        "composer": "Bob",
        "comment": "nice one",
    }
    audio.set_tags(song, **tags)

    read = audio.get(song).details["tags"]

    assert read == tags
    assert list(read) == list(tags)  # the same order every time


def test_tags_on_a_wav(tmp_path):
    clip = _wav(tmp_path / "clip.wav")

    audio.set_tags(clip, title="Take 1", comment="room mic")
    result = audio.get(clip)

    assert result.details["tags"] == {"title": "Take 1", "comment": "room mic"}
    assert result.details["stream"]["duration"] == pytest.approx(1.0)


def test_m4a_knows_the_composer_tag():
    """`set --composer` failed on M4A: mutagen's easy MP4 has no "composer"."""
    from mutagen.easymp4 import EasyMP4Tags

    from max_cli.core.engines.audio_metadata_engine import _register_easy_keys

    _register_easy_keys()

    assert "composer" in EasyMP4Tags.Get


def test_set_writes_to_a_new_file_when_asked(song, tmp_path):
    copy = tmp_path / "out" / "copy.mp3"

    result = audio.set_tags(song, title="New", output=copy)

    assert result.output_files == [copy]
    assert audio.get(copy).details["tags"] == {"title": "New"}
    assert audio.get(song).details["tags"] == {}


def test_set_without_tags_is_an_error(song):
    with pytest.raises(ValidationError, match="No tags given"):
        audio.set_tags(song)


def test_a_file_that_isnt_audio_is_refused(tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("hi", encoding="utf-8")

    with pytest.raises(ValidationError, match="can't edit tags in .txt"):
        audio.get(notes)
    with pytest.raises(ResourceNotFoundError):
        audio.get(tmp_path / "gone.mp3")


def test_clear_removes_every_tag(song):
    audio.set_tags(song, title="X", artist="Y")

    audio.clear(song)

    assert audio.get(song).details["tags"] == {}


# --- batch -------------------------------------------------------------------------


def _album(folder: Path, count: int) -> list[Path]:
    folder.mkdir(exist_ok=True)
    return [_mp3(folder / f"{index}.mp3") for index in range(1, count + 1)]


def test_batch_numbers_tracks_from_start(tmp_path):
    files = _album(tmp_path / "lp", 3)

    result = audio.batch(files, album="LP", start=1)

    assert result.ok and result.message == "Updated 3 files successfully."
    tracks = [audio.get(path).details["tags"]["tracknumber"] for path in files]
    assert tracks == ["1", "2", "3"]


def test_batch_track_without_start_writes_that_number(tmp_path):
    """--track 5 alone wrote "0" into every file."""
    files = _album(tmp_path / "lp", 2)

    audio.batch(files, tracknumber="5")

    assert {audio.get(path).details["tags"]["tracknumber"] for path in files} == {"5"}


def test_batch_takes_a_folder_and_a_wildcard(tmp_path):
    files = _album(tmp_path / "lp", 2)
    (tmp_path / "lp" / "cover.jpg").write_bytes(b"x")

    by_folder = audio.batch([tmp_path / "lp"], genre="Pop")
    by_pattern = audio.batch([tmp_path / "lp" / "*.mp3"], genre="Rock")

    assert by_folder.output_files == files
    assert by_pattern.output_files == files


def test_batch_reports_a_bad_file_and_goes_on(tmp_path):
    good = _mp3(tmp_path / "good.mp3")
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"not audio at all")

    result = audio.batch([good, bad], genre="Pop")

    assert result.ok and result.output_files == [good]
    assert [failure["file"] for failure in result.details["failed"]] == ["bad.mp3"]
    assert result.message == "Updated 1 of 2 files."


def test_batch_without_tags_or_files_is_an_error(tmp_path):
    files = _album(tmp_path / "lp", 1)

    with pytest.raises(ValidationError, match="No tags given"):
        audio.batch(files)
    with pytest.raises(ValidationError, match="No audio files"):
        audio.batch([tmp_path / "lp" / "*.flac"], genre="Pop")
    with pytest.raises(ResourceNotFoundError):
        audio.batch([tmp_path / "gone.mp3"], genre="Pop")


# --- organize ----------------------------------------------------------------------


def test_organize_dry_run_moves_nothing(tmp_path):
    files = _album(tmp_path / "in", 2)
    audio.batch(files, artist="Band", album="LP")

    result = audio.organize(
        [tmp_path / "in"], tmp_path / "out", "artist-album", dry_run=True
    )

    assert result.details["dry_run"] and result.undo_group is None
    assert len(result.details["moves"]) == 2
    assert all(path.exists() for path in files)
    assert not (tmp_path / "out").exists()


def test_organize_moves_by_tags_and_can_be_undone(tmp_path):
    files = _album(tmp_path / "in", 2)
    audio.batch(files, artist="Band", album="LP")
    audio.set_tags(files[0], title="Opener")

    result = audio.organize([tmp_path / "in"], tmp_path / "out", "artist-album")

    moved = sorted(path.name for path in (tmp_path / "out" / "Band" / "LP").iterdir())
    assert moved == ["2.mp3", "Opener.mp3"]
    assert result.undo_group is not None


def test_organize_refuses_an_unknown_pattern(song):
    with pytest.raises(ValidationError, match="Unknown pattern"):
        audio.organize([song], pattern="decade")


# --- compress ----------------------------------------------------------------------


def test_compress_names_the_output_and_reports_sizes(song):
    media = MagicMock()
    media.compress_audio.side_effect = lambda source, output, **_: output.write_bytes(
        b"x"
    )

    result = audio.compress(song, quality="s", mono=True, engine=media)

    output = song.parent / "song_compressed.mp3"
    media.compress_audio.assert_called_once_with(
        song, output, bitrate="64k", channels=1
    )
    assert result.details["output_size"] == 1
    assert result.details["input_size"] == song.stat().st_size


# --- describe (the Audio page) -----------------------------------------------------


def test_describe_a_song(song):
    audio.set_tags(song, title="My Song", artist="Ana")

    facts = audio.describe(song)

    assert facts.tags == {"title": "My Song", "artist": "Ana"}
    assert facts.duration == pytest.approx(0.52, abs=0.01)
    assert facts.bitrate == 128000
    assert facts.cover_art is False


def test_describe_a_folder_counts_untagged_tracks(tmp_path):
    files = _album(tmp_path / "lp", 3)
    audio.set_tags(files[0], title="One", artist="Ana")

    facts = audio.describe(tmp_path / "lp")

    assert facts.is_folder and facts.track_count == 3
    assert facts.formats == {"MP3": 3}
    assert facts.untagged == 2
    assert "2 without title or artist" in facts.note
    assert facts.total_duration == pytest.approx(3 * 0.52, abs=0.05)


def test_describe_a_folder_names_its_artists_and_albums(tmp_path):
    files = _album(tmp_path / "lp", 3)
    audio.set_tags(files[0], artist="Ana", album="Blue")
    audio.set_tags(files[1], artist="Ana", album="Blue")
    audio.set_tags(files[2], artist="Bo", album="Red")

    facts = audio.describe(tmp_path / "lp")

    assert facts.artists == {"Ana": 2, "Bo": 1}
    assert facts.albums == {"Blue": 2, "Red": 1}


def test_undo_removes_the_folders_organize_made(tmp_path):
    """Undo put the files back but left empty Artist/Album folders."""
    from max_cli.core.operations import files

    files_in = _album(tmp_path / "in", 2)
    audio.batch(files_in, artist="Band", album="LP")
    (tmp_path / "out").mkdir()  # yours before organize: undo keeps it

    audio.organize([tmp_path / "in"], tmp_path / "out", "artist-album")
    files.undo()

    assert all(path.exists() for path in files_in)
    assert (tmp_path / "out").is_dir()
    assert list((tmp_path / "out").iterdir()) == []
