"""CliRunner tests for `max audio` (src/max_cli/interface/cli_audio.py)."""

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from max_cli.common.exceptions import MaxError
from max_cli.interface.cli_audio import app as audio_app

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})

ENGINE_PATH = "max_cli.interface.cli_audio._get_engine"
MEDIA_ENGINE_PATH = "max_cli.interface.cli_audio._get_media_engine"
TRANSACTION_LOG_PATH = "max_cli.common.transaction_log.TransactionLog"

# The shared Rich console is built at import time, so it may still emit ANSI
# styles inside CliRunner. Strip them before substring checks.
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

VISIBLE_COMMANDS = ["compress", "denoise", "get", "set", "clear", "batch", "organize"]
HIDDEN_ALIASES = ["c", "dn", "g", "s", "cl", "b", "org"]


def _plain(result) -> str:
    return ANSI_ESCAPE.sub("", result.output)


def _write_small_output(source: Path, output: Path, **_kwargs) -> None:
    """Stand-in for an FFmpeg encode: produce a smaller file at `output`."""
    output.write_bytes(b"x" * 4)


def test_group_help_lists_visible_commands() -> None:
    result = runner.invoke(audio_app, ["--help"])

    assert result.exit_code == 0
    for command in VISIBLE_COMMANDS:
        assert command in result.stdout


@pytest.mark.parametrize("command", VISIBLE_COMMANDS + HIDDEN_ALIASES)
def test_command_help(command: str) -> None:
    result = runner.invoke(audio_app, [command, "--help"])

    assert result.exit_code == 0, result.output
    assert "Usage" in result.stdout


class TestCompress:
    def test_encodes_to_sibling_mp3(self, dummy_audio: Path) -> None:
        media = MagicMock()
        media.compress_audio.side_effect = _write_small_output
        with patch(MEDIA_ENGINE_PATH, return_value=media):
            result = runner.invoke(audio_app, ["compress", str(dummy_audio)])

        assert result.exit_code == 0, result.output
        expected_output = dummy_audio.parent / "test_compressed.mp3"
        media.compress_audio.assert_called_once_with(
            dummy_audio, expected_output, bitrate="128k", channels=None
        )
        assert expected_output.exists()
        assert "Audio compressed" in _plain(result)

    def test_small_mono_quality(self, dummy_audio: Path, tmp_path: Path) -> None:
        media = MagicMock()
        media.compress_audio.side_effect = _write_small_output
        output = tmp_path / "small.mp3"
        with patch(MEDIA_ENGINE_PATH, return_value=media):
            result = runner.invoke(
                audio_app,
                ["compress", str(dummy_audio), "-q", "s", "--mono", "-o", str(output)],
            )

        assert result.exit_code == 0, result.output
        media.compress_audio.assert_called_once_with(
            dummy_audio, output, bitrate="64k", channels=1
        )
        assert "64k, mono" in _plain(result)

    def test_missing_file_exits_1(self, tmp_path: Path) -> None:
        with patch(MEDIA_ENGINE_PATH, return_value=MagicMock()):
            result = runner.invoke(audio_app, ["compress", str(tmp_path / "no.mp3")])

        assert result.exit_code == 1
        assert "File not found" in _plain(result)

    def test_engine_error_is_reported(self, dummy_audio: Path) -> None:
        media = MagicMock()
        media.compress_audio.side_effect = MaxError("ffmpeg exploded")
        with patch(MEDIA_ENGINE_PATH, return_value=media):
            result = runner.invoke(audio_app, ["compress", str(dummy_audio)])

        assert result.exit_code == 0
        assert result.exception is None
        assert "Compression failed: ffmpeg exploded" in _plain(result)


class TestDenoise:
    def test_writes_denoised_file(self, dummy_audio: Path) -> None:
        media = MagicMock()
        media.denoise_audio.side_effect = _write_small_output
        with patch(MEDIA_ENGINE_PATH, return_value=media):
            result = runner.invoke(
                audio_app, ["denoise", str(dummy_audio), "--strength", "aggressive"]
            )

        assert result.exit_code == 0, result.output
        expected_output = dummy_audio.parent / "test_denoised.mp3"
        media.denoise_audio.assert_called_once_with(
            dummy_audio, expected_output, mode="auto", strength="aggressive"
        )
        assert "Denoised audio saved: test_denoised.mp3" in _plain(result)

    def test_non_auto_mode_resets_strength(self, dummy_audio: Path) -> None:
        media = MagicMock()
        media.denoise_audio.side_effect = _write_small_output
        with patch(MEDIA_ENGINE_PATH, return_value=media):
            result = runner.invoke(
                audio_app,
                ["denoise", str(dummy_audio), "-m", "hiss", "-s", "aggressive"],
            )

        assert result.exit_code == 0, result.output
        assert media.denoise_audio.call_args.kwargs == {
            "mode": "hiss",
            "strength": "medium",
        }

    def test_engine_error_is_reported(self, dummy_audio: Path) -> None:
        media = MagicMock()
        media.denoise_audio.side_effect = MaxError("filter unavailable")
        with patch(MEDIA_ENGINE_PATH, return_value=media):
            result = runner.invoke(audio_app, ["denoise", str(dummy_audio)])

        assert result.exit_code == 0
        assert result.exception is None
        assert "Denoising failed: filter unavailable" in _plain(result)


class TestGet:
    def test_prints_metadata_table(self, dummy_audio: Path) -> None:
        engine = MagicMock()
        engine.get_metadata.return_value = {"title": "Song A", "artist": "Band B"}
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(audio_app, ["get", str(dummy_audio)])

        assert result.exit_code == 0, result.output
        engine.get_metadata.assert_called_once_with(dummy_audio)
        output = _plain(result)
        assert "Metadata: test.mp3" in output
        assert "Song A" in output
        assert "Band B" in output

    def test_engine_error_is_reported(self, dummy_audio: Path) -> None:
        engine = MagicMock()
        engine.get_metadata.side_effect = MaxError("unsupported format")
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(audio_app, ["get", str(dummy_audio)])

        assert result.exit_code == 0
        assert result.exception is None
        assert "Failed to read metadata: unsupported format" in _plain(result)


class TestSet:
    def test_passes_only_the_given_tags(self, dummy_audio: Path) -> None:
        engine = MagicMock()
        engine.set_metadata.return_value = dummy_audio
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(
                audio_app,
                ["set", str(dummy_audio), "-t", "New Title", "-a", "New Artist"],
            )

        assert result.exit_code == 0, result.output
        args, kwargs = engine.set_metadata.call_args
        assert args == (dummy_audio, None)
        assert kwargs == {"title": "New Title", "artist": "New Artist"}
        assert "Metadata saved" in _plain(result)

    def test_no_tags_is_an_error(self, dummy_audio: Path) -> None:
        engine = MagicMock()
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(audio_app, ["set", str(dummy_audio)])

        assert result.exit_code == 1
        engine.set_metadata.assert_not_called()
        assert "No tags given" in _plain(result)

    def test_engine_error_is_reported(self, dummy_audio: Path) -> None:
        engine = MagicMock()
        engine.set_metadata.side_effect = MaxError("read-only file")
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(audio_app, ["set", str(dummy_audio), "-t", "X"])

        assert result.exit_code == 0
        assert result.exception is None
        assert "Failed to set metadata: read-only file" in _plain(result)


class TestClear:
    def test_clears_metadata(self, dummy_audio: Path) -> None:
        engine = MagicMock()
        engine.clear_metadata.return_value = dummy_audio
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(audio_app, ["clear", str(dummy_audio)])

        assert result.exit_code == 0, result.output
        engine.clear_metadata.assert_called_once_with(dummy_audio, None)
        assert "Cleared metadata" in _plain(result)

    def test_the_old_no_duration_flag_still_runs(self, dummy_audio: Path) -> None:
        """--keep-duration/--no-duration never did anything; scripts may pass it."""
        engine = MagicMock()
        engine.clear_metadata.return_value = dummy_audio
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(
                audio_app, ["clear", str(dummy_audio), "--no-duration"]
            )
        help_text = runner.invoke(audio_app, ["clear", "--help"]).output

        assert result.exit_code == 0, result.output
        assert "--keep-duration" not in help_text

    def test_engine_error_is_reported(self, dummy_audio: Path) -> None:
        engine = MagicMock()
        engine.clear_metadata.side_effect = MaxError("locked")
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(audio_app, ["clear", str(dummy_audio)])

        assert result.exit_code == 0
        assert result.exception is None
        assert "Failed to clear metadata: locked" in _plain(result)


def _songs(folder: Path, count: int) -> list[Path]:
    files = [folder / f"{index}.mp3" for index in range(count)]
    for path in files:
        path.write_bytes(b"")
    return files


class TestBatch:
    def test_start_numbers_the_tracks(self, tmp_path: Path) -> None:
        files = _songs(tmp_path, 3)
        engine = MagicMock()
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(
                audio_app,
                ["batch", *map(str, files), "-b", "Album Z", "--start", "5"],
            )

        assert result.exit_code == 0, result.output
        calls = engine.set_metadata.call_args_list
        assert [call.kwargs["tracknumber"] for call in calls] == ["5", "6", "7"]
        assert all(call.kwargs["album"] == "Album Z" for call in calls)
        assert "Updated 3 files successfully." in _plain(result)

    def test_track_without_start_writes_that_number(self, tmp_path: Path) -> None:
        """--track 5 without --start wrote "0" into every file."""
        files = _songs(tmp_path, 2)
        engine = MagicMock()
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(audio_app, ["batch", *map(str, files), "-n", "5"])

        assert result.exit_code == 0, result.output
        calls = engine.set_metadata.call_args_list
        assert [call.kwargs["tracknumber"] for call in calls] == ["5", "5"]

    def test_a_folder_gives_its_audio_files(self, tmp_path: Path) -> None:
        _songs(tmp_path, 2)
        (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
        engine = MagicMock()
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(audio_app, ["batch", str(tmp_path), "-g", "Pop"])

        assert result.exit_code == 0, result.output
        assert engine.set_metadata.call_count == 2

    def test_one_failing_file_keeps_going(self, tmp_path: Path) -> None:
        good, bad = tmp_path / "good.mp3", tmp_path / "bad.mp3"
        for path in (good, bad):
            path.write_bytes(b"")
        engine = MagicMock()
        engine.set_metadata.side_effect = [None, ValueError("corrupt tag")]
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(
                audio_app, ["batch", str(good), str(bad), "-g", "Rock"]
            )

        assert result.exception is None
        output = _plain(result)
        assert "Failed on bad.mp3: corrupt tag" in output
        assert "Updated 1 of 2 files." in output


def _moved(count: int) -> dict:
    moves = [f"{index}.mp3 -> Artist/{index}.mp3" for index in range(count)]
    return {
        "moved": moves,
        "skipped": [],
        "errors": [],
        "total_moved": count,
        "total_errors": 0,
    }


class TestOrganize:
    def test_moves_files_and_saves_transaction(self, tmp_path: Path) -> None:
        files = _songs(tmp_path, 2)
        engine = MagicMock()
        engine.organize.return_value = _moved(2)
        with (
            patch(ENGINE_PATH, return_value=engine),
            patch(TRANSACTION_LOG_PATH) as transaction_log_cls,
        ):
            result = runner.invoke(
                audio_app, ["organize", *map(str, files), "-p", "artist"]
            )

        assert result.exit_code == 0, result.output
        args, kwargs = engine.organize.call_args
        assert args == (files, tmp_path, "artist")
        assert kwargs["filter_value"] is None and kwargs["dry_run"] is False
        transaction_log_cls.return_value.save.assert_called_once_with()
        output = _plain(result)
        assert "Moved 2 files" in output
        assert "Done! Moved: 2, Errors: 0" in output

    def test_dry_run_moves_nothing_and_records_nothing(self, tmp_path: Path) -> None:
        files = _songs(tmp_path, 1)
        engine = MagicMock()
        engine.organize.return_value = _moved(1)
        with (
            patch(ENGINE_PATH, return_value=engine),
            patch(TRANSACTION_LOG_PATH) as transaction_log_cls,
        ):
            result = runner.invoke(audio_app, ["organize", str(files[0]), "--dry-run"])

        assert result.exit_code == 0, result.output
        assert engine.organize.call_args.kwargs["dry_run"] is True
        transaction_log_cls.assert_not_called()
        output = _plain(result)
        assert "Would move 1 files" in output
        assert "Dry run: nothing moved" in output

    def test_invalid_pattern_is_rejected(self, tmp_path: Path) -> None:
        engine = MagicMock()
        files = _songs(tmp_path, 1)
        with patch(ENGINE_PATH, return_value=engine), patch(TRANSACTION_LOG_PATH):
            result = runner.invoke(
                audio_app, ["organize", str(files[0]), "-p", "decade"]
            )

        assert result.exit_code == 1
        engine.organize.assert_not_called()
        assert "Unknown pattern" in _plain(result)

    def test_engine_error_is_reported(self, tmp_path: Path) -> None:
        engine = MagicMock()
        engine.organize.side_effect = MaxError("target not writable")
        files = _songs(tmp_path, 1)
        with (
            patch(ENGINE_PATH, return_value=engine),
            patch(TRANSACTION_LOG_PATH) as transaction_log_cls,
        ):
            result = runner.invoke(audio_app, ["organize", str(files[0])])

        assert result.exception is None
        assert "Organizing failed: target not writable" in _plain(result)
        transaction_log_cls.return_value.save.assert_not_called()
