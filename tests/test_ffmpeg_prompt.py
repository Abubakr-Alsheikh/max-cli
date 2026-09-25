from unittest.mock import MagicMock, patch

from max_cli.interface import ffmpeg_prompt


def _console(is_terminal: bool) -> MagicMock:
    return MagicMock(is_terminal=is_terminal)


def test_confirm_declines_without_a_terminal():
    with patch.object(ffmpeg_prompt, "console", _console(False)):
        with patch("rich.prompt.Confirm.ask") as ask:
            assert ffmpeg_prompt.confirm_ffmpeg_download("Download?") is False
    ask.assert_not_called()


def test_confirm_asks_in_a_terminal():
    with patch.object(ffmpeg_prompt, "console", _console(True)):
        with patch("rich.prompt.Confirm.ask", return_value=True) as ask:
            assert ffmpeg_prompt.confirm_ffmpeg_download("Download?") is True
    ask.assert_called_once()


def test_progress_line_shows_percentage():
    fake_console = _console(True)
    with patch.object(ffmpeg_prompt, "console", fake_console):
        ffmpeg_prompt.show_ffmpeg_progress(512 * 1024, 1024 * 1024)
    assert "(50%)" in fake_console.print.call_args_list[0].args[0]
