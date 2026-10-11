"""`max video cut-silence`: finding pauses, choosing what stays, and the encode.

FFmpeg never runs: subprocess.run is mocked, and the operation tests use a
fake engine.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from max_cli.common.exceptions import ValidationError
from max_cli.core.engines.media_engine import MediaEngine
from max_cli.core.engines.video_engine import parse_silences
from max_cli.core.operations import video
from max_cli.interface.cli_media import app as media_app

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})

SILENCEDETECT_LOG = """\
Input #0, mp3, from 'talk.mp3':
[silencedetect @ 0000] silence_start: 3.00
[silencedetect @ 0000] silence_end: 5.00 | silence_duration: 2.00
size=N/A time=00:00:08.00 bitrate=N/A speed= 600x
[silencedetect @ 0000] silence_start: 8.00
[silencedetect @ 0000] silence_end: 10.00 | silence_duration: 2.00
[silencedetect @ 0000] silence_start: 12.5
"""


def test_parse_silences_pairs_starts_and_ends():
    assert parse_silences(SILENCEDETECT_LOG) == [
        (3.0, 5.0),
        (8.0, 10.0),
        (12.5, None),  # silent to the end
    ]


def test_parse_silences_clamps_a_negative_start():
    log = "silence_start: -0.01\nsilence_end: 1.5 | silence_duration: 1.5\n"

    assert parse_silences(log) == [(0.0, 1.5)]


class TestSegmentsToKeep:
    def test_padding_stays_at_both_ends_of_a_cut(self):
        keep = video.segments_to_keep([(3.0, 5.0), (8.0, 10.0)], 13.0, 0.25)

        assert keep == [(0.0, 3.25), (4.75, 8.25), (9.75, 13.0)]

    def test_leading_and_trailing_silence_go_completely(self):
        keep = video.segments_to_keep([(0.0, 2.0), (9.0, None)], 12.0, 0.25)

        assert keep == [(1.75, 9.25)]

    def test_a_pause_shorter_than_two_paddings_stays(self):
        keep = video.segments_to_keep([(3.0, 3.4)], 10.0, 0.25)

        assert keep == [(0.0, 10.0)]

    def test_all_silence_keeps_nothing(self):
        assert video.segments_to_keep([(0.0, None)], 10.0, 0.1) == []


def _fake_media(
    silences: list, duration: float = 13.0, has_video: bool = True
) -> MagicMock:
    media = MagicMock()
    streams = [{"codec_type": "audio", "codec_name": "aac"}]
    if has_video:
        streams.append({"codec_type": "video", "codec_name": "h264"})
    media.probe_media.return_value = {
        "format": {"duration": str(duration)},
        "streams": streams,
    }
    media.find_silences.return_value = silences
    return media


class TestOperation:
    def test_cuts_and_reports_what_it_removed(self, tmp_path):
        source = tmp_path / "talk.mp4"
        source.write_bytes(b"v")
        media = _fake_media([(3.0, 5.0), (8.0, 10.0)])

        result = video.cut_silence(source, padding=0.25, engine=media)

        assert result.ok
        assert result.output_files == [tmp_path / "talk_nosilence.mp4"]
        assert result.details == {
            "pauses": 2,
            "original_seconds": 13.0,
            "removed_seconds": 3.0,
        }
        media.find_silences.assert_called_once_with(source, -30.0, 0.6)
        source_arg, output_arg, keep = media.keep_segments.call_args.args
        assert keep == [(0.0, 3.25), (4.75, 8.25), (9.75, 13.0)]
        assert media.keep_segments.call_args.kwargs == {"has_video": True}

    def test_audio_file_keeps_its_type_and_has_no_picture(self, tmp_path):
        source = tmp_path / "note.m4a"
        source.write_bytes(b"a")
        media = _fake_media([(1.0, 4.0)], has_video=False)

        result = video.cut_silence(source, engine=media)

        assert result.output_files == [tmp_path / "note_nosilence.m4a"]
        assert media.keep_segments.call_args.kwargs == {"has_video": False}

    def test_no_pauses_writes_nothing(self, tmp_path):
        source = tmp_path / "talk.mp4"
        source.write_bytes(b"v")
        media = _fake_media([])

        result = video.cut_silence(source, engine=media)

        assert result.ok
        assert result.output_files == []
        assert "nothing to cut" in result.message
        media.keep_segments.assert_not_called()

    def test_all_silence_suggests_a_lower_threshold(self, tmp_path):
        source = tmp_path / "quiet.mp3"
        source.write_bytes(b"a")

        with pytest.raises(ValidationError, match="all silence.*-40"):
            video.cut_silence(source, engine=_fake_media([(0.0, None)]))

    def test_a_file_without_sound_is_refused(self, tmp_path):
        source = tmp_path / "silent.mp4"
        source.write_bytes(b"v")
        media = _fake_media([])
        media.probe_media.return_value = {
            "format": {"duration": "5"},
            "streams": [{"codec_type": "video", "codec_name": "h264"}],
        }

        with pytest.raises(ValidationError, match="no sound"):
            video.cut_silence(source, engine=media)

    def test_bad_settings(self, tmp_path):
        source = tmp_path / "talk.mp4"
        source.write_bytes(b"v")

        with pytest.raises(ValidationError):
            video.cut_silence(source, min_silence=0, engine=_fake_media([]))


def _completed(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], 0, stdout=stdout, stderr=stderr)


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
class TestEngine:
    @patch("subprocess.run")
    def test_find_silences_runs_silencedetect(self, mock_run, mock_which, tmp_path):
        mock_run.return_value = _completed(stderr=SILENCEDETECT_LOG)

        silences = MediaEngine().find_silences(tmp_path / "a.mp3", -35.0, 0.8)

        command = mock_run.call_args.args[0]
        assert command[command.index("-af") + 1] == "silencedetect=noise=-35.0dB:d=0.8"
        assert silences[0] == (3.0, 5.0)

    @pytest.mark.parametrize(
        "version_line, option",
        [
            ("ffmpeg version 7.0.2-essentials_build", "-/filter_complex"),
            ("ffmpeg version n8.0 Copyright", "-/filter_complex"),
            ("ffmpeg version 6.1.1-3ubuntu5", "-filter_complex_script"),
            ("ffmpeg version N-117000-g1234", "-/filter_complex"),
        ],
    )
    def test_filter_goes_through_a_file(
        self, mock_which, version_line, option, tmp_path
    ):
        scripts: list[str] = []

        def run(command, **kwargs):
            if "-version" in command:
                return _completed(stdout=version_line)
            scripts.append(Path(command[command.index(option) + 1]).read_text())
            return _completed()

        with patch("subprocess.run", side_effect=run) as mock_run:
            MediaEngine().keep_segments(
                tmp_path / "in.mp4",
                tmp_path / "out.mp4",
                [(0.0, 3.25), (4.75, 8.0)],
                has_video=True,
            )

        command = mock_run.call_args.args[0]
        assert command[-1] == str(tmp_path / "out.mp4")
        assert ["-map", "[v]", "-map", "[a]"] == command[-7:-3]
        (script,) = scripts
        between = "between(t,0.000,3.250)+between(t,4.750,8.000)"
        assert f"select='{between}',setpts=N/FRAME_RATE/TB[v]" in script
        assert f"aselect='{between}',asetpts=N/SR/TB[a]" in script

    def test_audio_only_maps_only_sound(self, mock_which, tmp_path):
        def run(command, **kwargs):
            if "-version" in command:
                return _completed(stdout="ffmpeg version 7.1")
            return _completed()

        with patch("subprocess.run", side_effect=run) as mock_run:
            MediaEngine().keep_segments(
                tmp_path / "a.mp3", tmp_path / "b.mp3", [(1.0, 2.0)], has_video=False
            )

        command = mock_run.call_args.args[0]
        assert "[v]" not in command
        assert command[-5:-3] == ["-map", "[a]"]


def test_cli_passes_the_settings(tmp_path):
    source = tmp_path / "talk.mp4"
    source.write_bytes(b"v")
    media = _fake_media([(3.0, 5.0)])
    media.keep_segments.side_effect = lambda src, out, *a, **k: out.write_bytes(b"x")

    with patch("max_cli.interface.cli_media._get_engine", return_value=media):
        result = runner.invoke(
            media_app, ["cut-silence", str(source), "-t", "-40", "-m", "1"]
        )

    assert result.exit_code == 0, result.output
    media.find_silences.assert_called_once_with(source, -40.0, 1.0)
    assert (tmp_path / "talk_nosilence.mp4").exists()
