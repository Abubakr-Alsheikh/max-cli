"""Downloading part of a video (`grab download --start 1:00 --end 5:00`).

yt-dlp never touches the network here: YoutubeDL is mocked, and the
operation and CLI tests use a fake engine.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest
from typer.testing import CliRunner

from max_cli.common.exceptions import ValidationError
from max_cli.core.engines import network_engine
from max_cli.core.engines.download_section import DownloadSection, clock, parse_time
from max_cli.core.engines.download_tags import output_template
from max_cli.core.engines.network_engine import NetworkEngine, make_download_task
from max_cli.core.operations import grab
from max_cli.interface.cli_network import app as network_app

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})
URL = "https://youtu.be/abc"


class TestTimes:
    @pytest.mark.parametrize(
        "text, seconds",
        [
            ("90", 90.0),
            ("1:30", 90.0),
            ("01:02:03", 3723.0),
            ("1:30.5", 90.5),
            ("75:00", 4500.0),
            (" 5 ", 5.0),
            ("", None),
            (None, None),
        ],
    )
    def test_reads_seconds_and_clock_times(self, text, seconds):
        assert parse_time(text) == seconds

    @pytest.mark.parametrize("text", ["1:75", "a", "1:2:3:4", "1.5:30", "-5", "1:"])
    def test_refuses_what_isnt_a_time(self, text):
        with pytest.raises(ValueError, match="isn't a time"):
            parse_time(text)

    def test_clock(self):
        assert clock(90) == "1:30"
        assert clock(3723) == "1:02:03"
        assert clock(5) == "0:05"


class TestSection:
    def test_no_times_is_the_whole_video(self):
        assert DownloadSection.parse("", None) is None

    def test_start_alone_runs_to_the_end(self):
        section = DownloadSection.parse("2:00", None)

        assert section == DownloadSection(120.0, None, False)
        assert section.label() == "2:00-end"

    def test_end_alone_starts_at_the_beginning(self):
        section = DownloadSection.parse(None, "0:30", exact=True)

        assert section == DownloadSection(0.0, 30.0, True)
        assert section.file_label() == "0.00-0.30"

    def test_end_before_start_is_refused(self):
        with pytest.raises(ValueError, match="end must come after"):
            DownloadSection.parse("5:00", "1:00")

    def test_ydl_options_name_the_range(self):
        options = DownloadSection(60.0, 300.0, True).ydl_options()

        ranges = list(options["download_ranges"]({"duration": 600}, None))
        assert ranges == [{"start_time": 60.0, "end_time": 300.0}]
        assert options["force_keyframes_at_cuts"] is True

    def test_open_end_reaches_the_end(self):
        options = DownloadSection(5.0).ydl_options()

        (only,) = options["download_ranges"]({"duration": 19}, None)
        assert only["end_time"] == float("inf")


def test_the_file_name_carries_the_times():
    assert output_template("none", " (1.00-5.00)") == "%(title)s (1.00-5.00).%(ext)s"
    assert output_template("album", " (x)").endswith("/%(title)s (x).%(ext)s")


@patch("max_cli.core.engines.network_engine._ffmpeg_for_parts")
@patch("yt_dlp.YoutubeDL")
@patch("shutil.which", return_value=None)
def test_engine_hands_yt_dlp_the_range_and_ffmpeg(
    mock_which, mock_ytdl, mock_ffmpeg, tmp_path
):
    mock_ffmpeg.return_value = Path("/opt/ffmpeg")

    NetworkEngine().download_media(
        URL, tmp_path, section=DownloadSection(60.0, 300.0, False)
    )

    options = mock_ytdl.call_args.args[0]
    assert options["outtmpl"].endswith("%(title)s (1.00-5.00).%(ext)s")
    assert options["force_keyframes_at_cuts"] is False
    assert callable(options["download_ranges"])
    assert options["ffmpeg_location"] == str(Path("/opt/ffmpeg"))


@patch("yt_dlp.YoutubeDL")
@patch("shutil.which", return_value=None)
def test_whole_downloads_are_unchanged(mock_which, mock_ytdl, tmp_path):
    NetworkEngine().download_media(URL, tmp_path)

    options = mock_ytdl.call_args.args[0]
    assert "download_ranges" not in options
    assert "ffmpeg_location" not in options
    assert options["outtmpl"].endswith("%(title)s.%(ext)s")


def test_a_queued_download_keeps_its_section():
    section = DownloadSection(90.5, 300.0, True)

    task = make_download_task(URL, quality="h", section=section)

    assert task.payload["section_start"] == 90.5
    assert network_engine._payload_section(task.payload) == section
    assert network_engine._payload_section({"url": URL}) is None


def _fake_engine(saved: Path) -> MagicMock:
    engine = MagicMock()
    engine.download_media.return_value = {"files": [str(saved)]}
    return engine


class TestOperation:
    def test_start_and_end_reach_the_engine(self, tmp_path):
        saved = tmp_path / "Talk (1.00-5.00).mp4"
        saved.write_bytes(b"v")
        engine = _fake_engine(saved)

        result = grab.download(
            URL,
            output=tmp_path,
            start="1:00",
            end="5:00",
            exact_cuts=True,
            engine=engine,
            record_history=False,
        )

        section = engine.download_media.call_args.kwargs["section"]
        assert section == DownloadSection(60.0, 300.0, True)
        assert result.message == "Downloaded: Talk (1:00-5:00)"
        assert result.details["section"] == "1:00-5:00"

    def test_no_times_download_the_whole_video(self, tmp_path):
        saved = tmp_path / "Talk.mp4"
        saved.write_bytes(b"v")
        engine = _fake_engine(saved)

        grab.download(URL, output=tmp_path, engine=engine, record_history=False)

        assert engine.download_media.call_args.kwargs["section"] is None

    def test_bad_times_stop_before_downloading(self, tmp_path):
        engine = _fake_engine(tmp_path / "x.mp4")

        with pytest.raises(ValidationError, match="isn't a time"):
            grab.download(URL, output=tmp_path, start="soon", engine=engine)

        engine.download_media.assert_not_called()


class TestCli:
    def test_start_and_end_flags(self, tmp_path):
        saved = tmp_path / "Talk (1.00-5.00).mp4"
        saved.write_bytes(b"v")
        engine = _fake_engine(saved)
        engine.has_js = True

        with patch("max_cli.interface.cli_network._get_engine", return_value=engine):
            result = runner.invoke(
                network_app,
                ["do", URL, "--start", "1:00", "--end", "5:00.5", "-o", str(tmp_path)]
                + ["--no-progress"],
            )

        assert result.exit_code == 0, result.output
        section = engine.download_media.call_args.kwargs["section"]
        assert section == DownloadSection(60.0, 300.5, False)
        assert "Only 1:00-5:00" in click.unstyle(result.output)

    def test_bad_time_exits_1(self, tmp_path):
        result = runner.invoke(
            network_app, ["do", URL, "--start", "later", "-o", str(tmp_path)]
        )

        assert result.exit_code == 1
        assert "isn't a time" in click.unstyle(result.output)

    def test_queue_stores_the_section(self, tmp_path):
        from max_cli.core.engines.task_manager import get_task_manager

        result = runner.invoke(
            network_app,
            ["do", URL, "-Q", "--no-process", "--end", "0:30", "-o", str(tmp_path)],
        )

        assert result.exit_code == 0, result.output
        [task] = get_task_manager().get_all()
        assert task.payload["section_end"] == 30.0
