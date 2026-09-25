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
    def test_passes_fields_to_engine(self, dummy_audio: Path) -> None:
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
        assert kwargs["title"] == "New Title"
        assert kwargs["artist"] == "New Artist"
        assert kwargs["album"] is None
        assert "Metadata saved" in _plain(result)

    def test_no_fields_does_not_call_engine(self, dummy_audio: Path) -> None:
        engine = MagicMock()
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(audio_app, ["set", str(dummy_audio)])

        assert result.exit_code == 0
        engine.set_metadata.assert_not_called()
        assert "No metadata fields specified" in _plain(result)

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
            result = runner.invoke(
                audio_app, ["clear", str(dummy_audio), "--no-duration"]
            )

        assert result.exit_code == 0, result.output
        engine.clear_metadata.assert_called_once_with(
            dummy_audio, None, keep_duration=False
        )
        assert "Cleared metadata" in _plain(result)

    def test_engine_error_is_reported(self, dummy_audio: Path) -> None:
        engine = MagicMock()
        engine.clear_metadata.side_effect = MaxError("locked")
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(audio_app, ["clear", str(dummy_audio)])

        assert result.exit_code == 0
        assert result.exception is None
        assert "Failed to clear metadata: locked" in _plain(result)


class TestBatch:
    def test_auto_increments_track_numbers(self, tmp_path: Path) -> None:
        files = [tmp_path / f"{index}.mp3" for index in range(3)]
        engine = MagicMock()
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(
                audio_app,
                ["batch", *map(str, files), "-b", "Album Z", "--start", "5"],
            )

        assert result.exit_code == 0, result.output
        tracks = [
            call.kwargs["tracknumber"] for call in engine.set_metadata.call_args_list
        ]
        assert tracks == ["5", "6", "7"]
        assert all(
            call.kwargs["album"] == "Album Z"
            for call in engine.set_metadata.call_args_list
        )
        assert "Updated 3 files successfully." in _plain(result)

    def test_engine_error_on_one_file_keeps_going(self, tmp_path: Path) -> None:
        files = [tmp_path / "good.mp3", tmp_path / "bad.mp3"]
        engine = MagicMock()
        engine.set_metadata.side_effect = [None, MaxError("corrupt tag")]
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(audio_app, ["batch", *map(str, files), "-g", "Rock"])

        assert result.exit_code == 0
        assert result.exception is None
        output = _plain(result)
        assert "Failed on bad.mp3: corrupt tag" in output
        assert "Updated 1 files successfully." in output


class TestOrganize:
    def test_moves_files_and_saves_transaction(self, tmp_path: Path) -> None:
        files = [tmp_path / "a.mp3", tmp_path / "b.mp3"]
        engine = MagicMock()
        engine.organize.return_value = {
            "moved": ["a.mp3 -> Artist/a.mp3", "b.mp3 -> Artist/b.mp3"],
            "total_moved": 2,
            "errors": [],
            "total_errors": 0,
        }
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
        assert kwargs["filter_value"] is None
        transaction_log_cls.return_value.save.assert_called_once_with()
        output = _plain(result)
        assert "Moved 2 files" in output
        assert "Done! Moved: 2, Errors: 0" in output

    def test_invalid_pattern_is_rejected(self, tmp_path: Path) -> None:
        engine = MagicMock()
        with patch(ENGINE_PATH, return_value=engine), patch(TRANSACTION_LOG_PATH):
            result = runner.invoke(
                audio_app, ["organize", str(tmp_path / "a.mp3"), "-p", "decade"]
            )

        assert result.exit_code == 0
        engine.organize.assert_not_called()
        assert "Invalid pattern" in _plain(result)

    def test_engine_error_propagates_to_main_handler(self, tmp_path: Path) -> None:
        # organize has no local try/except; max_cli.main.main() reports MaxError.
        engine = MagicMock()
        engine.organize.side_effect = MaxError("target not writable")
        with (
            patch(ENGINE_PATH, return_value=engine),
            patch(TRANSACTION_LOG_PATH) as transaction_log_cls,
        ):
            result = runner.invoke(audio_app, ["organize", str(tmp_path / "a.mp3")])

        assert result.exit_code == 1
        assert isinstance(result.exception, MaxError)
        transaction_log_cls.return_value.save.assert_not_called()
