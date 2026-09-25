"""CliRunner tests for `max tools` (src/max_cli/interface/cli_tools.py)."""

import re
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from max_cli.common.exceptions import MaxError
from max_cli.interface.cli_tools import app as tools_app

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})

ENGINE_PATH = "max_cli.interface.cli_tools._get_engine"

# The shared Rich console is built at import time, so it may still emit ANSI
# styles inside CliRunner. Strip them before substring checks.
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(result) -> str:
    return ANSI_ESCAPE.sub("", result.output)


def _engine() -> MagicMock:
    return MagicMock()


def test_group_help_lists_visible_commands() -> None:
    result = runner.invoke(tools_app, ["--help"])

    assert result.exit_code == 0
    for command in ("share", "paste", "copy"):
        assert command in _plain(result)


@pytest.mark.parametrize("command", ["share", "qr", "paste", "copy"])
def test_command_help(command: str) -> None:
    result = runner.invoke(tools_app, [command, "--help"])

    assert result.exit_code == 0, result.output
    assert "Usage" in _plain(result)


class TestShare:
    def test_prints_generated_qr(self) -> None:
        engine = _engine()
        engine.generate_qr.return_value = "QR-BLOCKS"
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(tools_app, ["share", "http://localhost:8000"])

        assert result.exit_code == 0, result.output
        engine.generate_qr.assert_called_once_with("http://localhost:8000")
        assert "Generating QR for:" in _plain(result)
        assert "QR-BLOCKS" in _plain(result)

    def test_hidden_qr_alias_uses_same_handler(self) -> None:
        engine = _engine()
        engine.generate_qr.return_value = "QR-BLOCKS"
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(tools_app, ["qr", "hello"])

        assert result.exit_code == 0, result.output
        engine.generate_qr.assert_called_once_with("hello")

    def test_engine_error_is_reported(self) -> None:
        engine = _engine()
        engine.generate_qr.side_effect = MaxError("segno missing")
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(tools_app, ["share", "hello"])

        assert result.exit_code == 0
        assert result.exception is None
        assert "QR generation failed: segno missing" in _plain(result)


class TestPaste:
    def test_saves_clipboard_image(self, tmp_path) -> None:
        engine = _engine()
        target = tmp_path / "shot.png"
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(tools_app, ["paste", str(target)])

        assert result.exit_code == 0, result.output
        engine.save_clipboard_image.assert_called_once_with(target)
        assert "Image saved to:" in _plain(result)

    def test_adds_png_suffix_when_missing(self, tmp_path) -> None:
        engine = _engine()
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(tools_app, ["paste", str(tmp_path / "shot")])

        assert result.exit_code == 0, result.output
        engine.save_clipboard_image.assert_called_once_with(tmp_path / "shot.png")

    def test_empty_clipboard_shows_warning(self, tmp_path) -> None:
        engine = _engine()
        engine.save_clipboard_image.side_effect = ValueError("Clipboard is empty.")
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(tools_app, ["paste", str(tmp_path / "a.png")])

        assert result.exit_code == 0
        assert "Clipboard is empty." in _plain(result)
        assert "Error" not in _plain(result)

    def test_engine_error_is_reported(self, tmp_path) -> None:
        engine = _engine()
        engine.save_clipboard_image.side_effect = MaxError("no display")
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(tools_app, ["paste", str(tmp_path / "a.png")])

        assert result.exit_code == 0
        assert result.exception is None
        assert "Failed to save image: no display" in _plain(result)


class TestCopy:
    def test_copies_file(self, tmp_path) -> None:
        engine = _engine()
        target = tmp_path / "notes.txt"
        target.write_text("hello", encoding="utf-8")
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(tools_app, ["copy", str(target)])

        assert result.exit_code == 0, result.output
        engine.copy_file_to_clipboard.assert_called_once_with(target)
        assert "Copied notes.txt to clipboard." in _plain(result)

    def test_engine_error_is_reported(self, tmp_path) -> None:
        engine = _engine()
        engine.copy_file_to_clipboard.side_effect = MaxError("File not found")
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(tools_app, ["copy", str(tmp_path / "gone.txt")])

        assert result.exit_code == 0
        assert result.exception is None
        assert "Error:" in _plain(result)
        assert "File not found" in _plain(result)


@patch(ENGINE_PATH)
def test_paste_asks_before_overwriting(mock_get_engine, tmp_path):
    """paste used to overwrite an existing file without asking."""
    existing = tmp_path / "shot.png"
    existing.write_bytes(b"keep me")

    result = runner.invoke(tools_app, ["paste", str(existing)], input="n\n")

    assert result.exit_code == 0, result.output
    mock_get_engine.return_value.save_clipboard_image.assert_not_called()
    assert existing.read_bytes() == b"keep me"


@patch(ENGINE_PATH)
def test_paste_force_overwrites(mock_get_engine, tmp_path):
    existing = tmp_path / "shot.png"
    existing.write_bytes(b"old")

    result = runner.invoke(tools_app, ["paste", str(existing), "--force"])

    assert result.exit_code == 0, result.output
    mock_get_engine.return_value.save_clipboard_image.assert_called_once_with(existing)
