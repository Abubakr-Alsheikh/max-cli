"""CliRunner tests for `max video` (src/max_cli/interface/cli_media.py).

Every test mocks `_get_engine`, so FFmpeg never runs.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from typer.testing import CliRunner

from max_cli.common import logger
from max_cli.common.exceptions import MaxError
from max_cli.core.engines.task_manager import get_task_manager
from max_cli.core.engines.task_queue import TaskType
from max_cli.core.presets import (
    CONCAT_METHODS,
    DEFAULT_VIDEO_PRESET,
    crf_for_level,
)
from max_cli.interface import cli_media
from max_cli.interface.cli_media import app as media_app

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})

ENGINE_PATH = "max_cli.interface.cli_media._get_engine"
ENCODED_BYTES = b"x"


@pytest.fixture(autouse=True)
def plain_console(monkeypatch):
    """Swap the shared Rich console for a wide, colorless one.

    The logger console is built at import time, so the runner's NO_COLOR and
    COLUMNS never reach it; without this it emits ANSI codes and wraps paths.
    """
    plain = Console(
        theme=logger.custom_theme,
        width=300,
        height=1000,
        color_system=None,
        force_terminal=False,
        legacy_windows=False,
    )
    monkeypatch.setattr(logger, "console", plain)
    monkeypatch.setattr(cli_media, "console", plain)


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    with patch(ENGINE_PATH, return_value=engine):
        yield engine


def _write_output(*args, **kwargs):
    """Engine side effect: create the output file (second positional arg)."""
    Path(args[1]).write_bytes(ENCODED_BYTES)


@pytest.mark.parametrize(
    "command",
    [
        None,
        "compress",
        "convert",
        "to-audio",
        "gif",
        "cut",
        "snap",
        "louder",
        "mute",
        "concat",
        "brightness",
        "color",
        "stabilize",
        "normalize",
        "denoise",
        "audio-convert",
        "record",
        "stream",
        "preview",
    ],
)
def test_help(command):
    args = [command, "--help"] if command else ["--help"]
    result = runner.invoke(media_app, args)
    assert result.exit_code == 0, result.output
    assert "Usage" in result.output


class TestCompress:
    def test_encodes_with_level_crf(self, mock_engine, dummy_video):
        mock_engine.compress_video.side_effect = _write_output

        result = runner.invoke(media_app, ["compress", str(dummy_video)])

        assert result.exit_code == 0, result.output
        output_path = dummy_video.parent / "test_compressed.mp4"
        mock_engine.compress_video.assert_called_once_with(
            dummy_video,
            output_path,
            crf=crf_for_level("balanced"),
            preset=DEFAULT_VIDEO_PRESET,
        )
        assert "Video saved:" in result.output
        assert "test_compressed.mp4" in result.output

    def test_queue_adds_task_without_encoding(self, mock_engine, dummy_video):
        result = runner.invoke(
            media_app, ["compress", str(dummy_video), "--queue", "--level", "max"]
        )

        assert result.exit_code == 0, result.output
        assert "Queued: test.mp4" in result.output
        mock_engine.compress_video.assert_not_called()
        [task] = get_task_manager().get_all()
        assert task.type == TaskType.ACTION
        assert task.payload == {
            "action": "video.compress",
            "args": {"target": str(dummy_video), "output": None, "level": "max"},
        }

    def test_engine_error_is_reported(self, mock_engine, dummy_video):
        mock_engine.compress_video.side_effect = MaxError("encoder crashed")

        result = runner.invoke(media_app, ["compress", str(dummy_video)])

        assert result.exception is None
        assert result.exit_code == 0
        assert "Error: Compression failed: encoder crashed" in result.output
        assert "Traceback" not in result.output


def test_missing_ffmpeg_exits_1(dummy_video):
    with patch(
        "max_cli.core.engines.media_engine.MediaEngine",
        side_effect=RuntimeError("FFmpeg not available"),
    ):
        result = runner.invoke(media_app, ["compress", str(dummy_video)])

    assert result.exit_code == 1
    assert "FFmpeg not available" in result.output


class TestToAudio:
    def test_default_bitrate_and_output(self, mock_engine, dummy_video):
        mock_engine.extract_audio.side_effect = _write_output

        result = runner.invoke(media_app, ["to-audio", str(dummy_video)])

        assert result.exit_code == 0, result.output
        mock_engine.extract_audio.assert_called_once_with(
            dummy_video, dummy_video.parent / "test.mp3", bitrate="192k"
        )
        assert "Audio extraction complete: test.mp3" in result.output

    def test_output_suffix_follows_format(self, mock_engine, dummy_video, tmp_path):
        mock_engine.extract_audio.side_effect = _write_output

        result = runner.invoke(
            media_app,
            [
                "to-audio",
                str(dummy_video),
                "-f",
                "wav",
                "-q",
                "xtreme",
                "-o",
                str(tmp_path / "song.mp3"),
            ],
        )

        assert result.exit_code == 0, result.output
        mock_engine.extract_audio.assert_called_once_with(
            dummy_video, tmp_path / "song.wav", bitrate="320k"
        )

    def test_missing_file_exits_1(self, mock_engine, tmp_path):
        result = runner.invoke(media_app, ["to-audio", str(tmp_path / "nope.mp4")])
        assert result.exit_code == 1
        assert "File not found" in result.output
        mock_engine.extract_audio.assert_not_called()


class TestCutAndConcat:
    def test_cut_passes_times(self, mock_engine, dummy_video):
        result = runner.invoke(
            media_app, ["cut", str(dummy_video), "-s", "10", "-d", "5"]
        )

        assert result.exit_code == 0, result.output
        mock_engine.trim_video.assert_called_once_with(
            dummy_video, dummy_video.parent / "test_cut.mp4", "10", None, "5"
        )
        assert "Clip saved:" in result.output

    def test_cut_audio_keeps_audio_extension(self, mock_engine, dummy_audio):
        result = runner.invoke(media_app, ["cut", str(dummy_audio), "-s", "1"])

        assert result.exit_code == 0, result.output
        output_path = mock_engine.trim_video.call_args.args[1]
        assert output_path == dummy_audio.parent / "test_cut.mp3"

    def test_concat_from_list_file(self, mock_engine, tmp_path):
        list_file = tmp_path / "clips.txt"
        list_file.write_text("file 'a.mp4'\nb.mp4\n", encoding="utf-8")

        result = runner.invoke(media_app, ["concat", str(list_file)])

        assert result.exit_code == 0, result.output
        mock_engine.concatenate_videos.assert_called_once_with(
            [Path("a.mp4"), Path("b.mp4")],
            tmp_path / "concatenated.mp4",
            method=CONCAT_METHODS["fast"],
        )
        assert "Concatenated 2 videos" in result.output

    def test_concat_rejects_bad_target(self, mock_engine, dummy_video):
        result = runner.invoke(media_app, ["concat", str(dummy_video)])

        assert result.exit_code == 1
        assert "Provide either a .txt file" in result.output
        mock_engine.concatenate_videos.assert_not_called()


class TestDenoise:
    def test_denoises_file(self, mock_engine, dummy_audio):
        mock_engine.denoise_audio.side_effect = _write_output

        result = runner.invoke(
            media_app, ["denoise", str(dummy_audio), "--strength", "aggressive"]
        )

        assert result.exit_code == 0, result.output
        mock_engine.denoise_audio.assert_called_once_with(
            dummy_audio,
            dummy_audio.parent / "test_denoised.mp3",
            mode="auto",
            strength="aggressive",
        )
        assert "Denoised audio saved: test_denoised.mp3" in result.output

    def test_queue_adds_task(self, mock_engine, dummy_audio):
        result = runner.invoke(
            media_app, ["denoise", str(dummy_audio), "--mode", "hum", "--queue"]
        )

        assert result.exit_code == 0, result.output
        mock_engine.denoise_audio.assert_not_called()
        [task] = get_task_manager().get_all()
        assert task.type == TaskType.ACTION
        assert task.payload["action"] == "video.denoise"
        assert task.payload["args"]["mode"] == "hum"


@pytest.mark.parametrize(
    "args, engine_method, message",
    [
        (["convert", "{video}", "-f", "mkv"], "convert_format", "Conversion failed"),
        (["gif", "{video}"], "video_to_gif", "GIF creation failed"),
        (["snap", "{video}"], "get_thumbnail", "Snapshot failed"),
        (["louder", "{video}"], "adjust_volume", "Volume adjustment failed"),
        (["mute", "{video}"], "mute_video", "Mute failed"),
        (["brightness", "{video}"], "adjust_brightness", "Adjustment failed"),
        (["color", "{video}"], "apply_color_preset", "Color grading failed"),
        (["stabilize", "{video}"], "stabilize_video", "Stabilization failed"),
        (["normalize", "{video}"], "normalize_audio", "Normalization failed"),
        (["denoise", "{video}"], "denoise_audio", "Denoising failed"),
        (["audio-convert", "{video}"], "convert_audio", "Conversion failed"),
        (["to-audio", "{video}"], "extract_audio", "Conversion failed"),
        (["cut", "{video}", "-s", "1"], "trim_video", "Cut failed"),
    ],
)
def test_engine_max_error_is_reported(
    mock_engine, dummy_video, args, engine_method, message
):
    getattr(mock_engine, engine_method).side_effect = MaxError("ffmpeg exploded")
    cli_args = [str(dummy_video) if arg == "{video}" else arg for arg in args]

    result = runner.invoke(media_app, cli_args)

    assert result.exception is None
    assert result.exit_code == 0
    assert f"Error: {message}: ffmpeg exploded" in result.output


@pytest.mark.parametrize("command", ["stream", "preview"])
def test_live_commands_require_existing_file(mock_engine, tmp_path, command):
    args = [command, str(tmp_path / "nope.mp4")]
    if command == "stream":
        args += ["--url", "rtmp://localhost/app"]

    result = runner.invoke(media_app, args)

    assert result.exit_code == 1
    assert "File not found" in result.output
    mock_engine.stream_to_rtmp.assert_not_called()
    mock_engine.live_preview.assert_not_called()


@patch(ENGINE_PATH)
def test_concat_rejects_unknown_method(mock_get_engine, tmp_path):
    """Unknown --method values used to fall back to "safe" without a word."""
    (tmp_path / "a.mp4").write_bytes(b"")
    result = runner.invoke(
        media_app, ["concat", str(tmp_path / "*.mp4"), "--method", "quick"]
    )

    assert result.exit_code == 1
    assert "Unknown method 'quick'" in result.output
    mock_get_engine.return_value.concatenate_videos.assert_not_called()
