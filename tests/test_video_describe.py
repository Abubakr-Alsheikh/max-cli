"""video.describe: what a video or audio file holds, for the dashboard's Video page."""

from unittest.mock import MagicMock, patch

import pytest

from max_cli.common.exceptions import ResourceNotFoundError
from max_cli.core.operations import video

PROBE = {
    "format": {"duration": "3725.4", "bit_rate": "8200000"},
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "avg_frame_rate": "30000/1001",
        },
        {"codec_type": "audio", "codec_name": "aac", "channels": 2},
    ],
}


def test_facts_come_from_ffprobe(dummy_video):
    engine = MagicMock()
    engine.probe_media.return_value = PROBE

    facts = video.describe(dummy_video, engine=engine)

    assert facts.duration == pytest.approx(3725.4)
    assert (facts.width, facts.height, facts.fps) == (1920, 1080, 29.97)
    assert (facts.video_codec, facts.audio_codec, facts.audio_channels) == (
        "h264",
        "aac",
        2,
    )
    assert facts.bitrate == 8_200_000
    assert facts.size_bytes == dummy_video.stat().st_size
    assert facts.note == ""


def test_a_music_files_cover_picture_is_not_video(dummy_audio):
    probe = {
        "format": {"duration": "200"},
        "streams": [
            {"codec_type": "audio", "codec_name": "mp3", "channels": 1},
            {
                "codec_type": "video",
                "codec_name": "mjpeg",
                "width": 500,
                "height": 500,
                "disposition": {"attached_pic": 1},
            },
        ],
    }

    facts = video.facts_from_probe(dummy_audio, 10, probe)

    assert facts.video_codec == "" and facts.width is None
    assert (facts.audio_codec, facts.audio_channels) == ("mp3", 1)


def test_without_ffmpeg_only_the_size_is_known(dummy_video):
    with patch(
        "max_cli.core.engines.ffmpeg_base.FFmpegEngine.__init__",
        side_effect=RuntimeError("FFmpeg is not installed"),
    ):
        facts = video.describe(dummy_video)

    assert facts.size_bytes > 0 and facts.duration is None
    assert facts.note == video.NO_FFMPEG_NOTE


def test_an_unreadable_file_says_why(dummy_video):
    engine = MagicMock()
    engine.probe_media.side_effect = RuntimeError("Invalid data found")

    facts = video.describe(dummy_video, engine=engine)

    assert facts.note == "Invalid data found"


def test_a_missing_file_is_an_error(tmp_path):
    with pytest.raises(ResourceNotFoundError):
        video.describe(tmp_path / "gone.mp4", engine=MagicMock())


def test_probe_media_reads_ffprobe_json(tmp_path):
    from max_cli.core.engines.ffmpeg_base import FFmpegEngine

    with patch.object(
        FFmpegEngine, "_resolve_ffmpeg", return_value=tmp_path / "ffmpeg"
    ):
        engine = FFmpegEngine()
    done = MagicMock(returncode=0, stdout='{"format": {"duration": "5"}}', stderr="")
    with patch("subprocess.run", return_value=done) as run:
        probe = engine.probe_media(tmp_path / "clip.mp4")

    assert probe == {"format": {"duration": "5"}}
    assert "-show_streams" in run.call_args.args[0]


def test_probe_media_failure_is_a_runtime_error(tmp_path):
    from max_cli.core.engines.ffmpeg_base import FFmpegEngine

    with patch.object(
        FFmpegEngine, "_resolve_ffmpeg", return_value=tmp_path / "ffmpeg"
    ):
        engine = FFmpegEngine()
    failed = MagicMock(returncode=1, stdout="", stderr="clip.mp4: No such file")
    with patch("subprocess.run", return_value=failed):
        with pytest.raises(RuntimeError, match="No such file"):
            engine.probe_media(tmp_path / "clip.mp4")
