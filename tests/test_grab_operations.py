"""`core/operations/grab.py` and the engine features it needs (grab-page-redesign.md, G1)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yt_dlp

from max_cli.common.exceptions import OperationCancelled, ValidationError
from max_cli.config import settings
from max_cli.core.engines.download_history import DownloadHistory
from max_cli.core.engines.network_engine import NetworkEngine
from max_cli.core.operations import grab

VIDEO_URL = "https://www.youtube.com/watch?v=abc123"

VIDEO_INFO = {
    "title": "Trailer",
    "uploader": "Studio",
    "duration": 151,
    "formats": [
        {
            "format_id": "140",
            "vcodec": "none",
            "acodec": "mp4a",
            "abr": 128,
            "filesize": 2_000_000,
        },
        {
            "format_id": "139",
            "vcodec": "none",
            "acodec": "mp4a",
            "abr": 48,
            "filesize": 800_000,
        },
        {
            "format_id": "137",
            "vcodec": "avc1",
            "acodec": "none",
            "height": 1080,
            "tbr": 4000,
            "filesize": 80_000_000,
        },
        {
            "format_id": "248",
            "vcodec": "vp9",
            "acodec": "none",
            "height": 1080,
            "tbr": 2500,
            "filesize": 50_000_000,
        },
        {
            "format_id": "136",
            "vcodec": "avc1",
            "acodec": "none",
            "height": 720,
            "tbr": 2000,
            "filesize_approx": 40_000_000,
        },
        {
            "format_id": "18",
            "vcodec": "avc1",
            "acodec": "mp4a",
            "height": 360,
            "tbr": 500,
        },
    ],
}

PLAYLIST_INFO = {
    "_type": "playlist",
    "title": "My Mix",
    "uploader": "Someone",
    "entries": [
        {"title": "Song one", "url": "https://youtu.be/1", "duration": 192},
        {"title": "Song two", "url": "https://youtu.be/2", "duration": 245},
    ],
}


@pytest.fixture(autouse=True)
def empty_probe_cache():
    grab._probe_cache.clear()
    yield
    grab._probe_cache.clear()


class TestProbe:
    def test_video_lists_heights_with_sizes(self):
        engine = MagicMock()
        engine.probe_info.return_value = VIDEO_INFO

        media = grab.probe(VIDEO_URL, engine=engine)

        assert (media.title, media.uploader, media.duration) == (
            "Trailer",
            "Studio",
            151,
        )
        assert not media.is_playlist
        assert [q.height for q in media.qualities] == [1080, 720, 360]
        # The best 1080p stream (highest bitrate) plus the best audio track.
        assert media.qualities[0].size_bytes == 82_000_000
        assert media.qualities[1].size_bytes == 42_000_000
        # Format 18 already has audio and no size.
        assert media.qualities[2].size_bytes is None
        assert media.audio_size_bytes == 2_000_000
        assert [q.quality_code for q in media.qualities] == ["h", "m", "ss"]
        assert media.qualities[0].label == "1080p"

    def test_playlist_lists_items_numbered_from_one(self):
        engine = MagicMock()
        engine.probe_info.return_value = PLAYLIST_INFO

        media = grab.probe("https://youtube.com/playlist?list=PL1", engine=engine)

        assert media.is_playlist
        assert [(e.index, e.title, e.duration) for e in media.entries] == [
            (1, "Song one", 192),
            (2, "Song two", 245),
        ]

    def test_results_are_cached(self):
        engine = MagicMock()
        engine.probe_info.return_value = VIDEO_INFO

        grab.probe(VIDEO_URL, engine=engine)
        grab.probe(f"  {VIDEO_URL} ", engine=engine)

        engine.probe_info.assert_called_once_with(VIDEO_URL)

    def test_blank_link(self):
        with pytest.raises(ValidationError, match="Paste a link"):
            grab.probe("   ", engine=MagicMock())


class TestDownload:
    def test_defaults_come_from_settings_and_history_is_recorded(self, tmp_path):
        engine = MagicMock()
        saved = tmp_path / "Trailer.mp4"
        saved.write_bytes(b"x" * 10)
        engine.download_media.return_value = {"files": [str(saved)]}
        engine.probe_info.return_value = VIDEO_INFO
        grab.probe(VIDEO_URL, engine=engine)

        result = grab.download(VIDEO_URL, output=tmp_path, engine=engine)

        kwargs = engine.download_media.call_args.kwargs
        assert kwargs["quality"] == settings.GRAB_QUALITY
        assert kwargs["audio_only"] is (settings.GRAB_DEFAULT_TYPE == "audio")
        assert kwargs["output_path"] == tmp_path
        assert kwargs["player_client"] is None
        assert result.output_files == [saved]
        assert result.message == "Downloaded: Trailer"
        [entry] = DownloadHistory().get_recent()
        assert entry["title"] == "Trailer"

    def test_audio_and_playlist_items(self, tmp_path):
        engine = MagicMock()
        engine.download_media.return_value = {"files": []}

        grab.download(
            "https://youtube.com/watch?v=x&list=PL1",
            output=tmp_path,
            media_type="audio",
            playlist_items="1-3",
            record_history=False,
            engine=engine,
        )

        kwargs = engine.download_media.call_args.kwargs
        assert kwargs["audio_only"] is True
        assert kwargs["playlist_items"] == "1-3"
        # Picking items keeps the playlist part of the link.
        assert "list=PL1" in kwargs["url"]

    def test_single_video_link_loses_its_playlist_part(self, tmp_path):
        engine = MagicMock()
        engine.download_media.return_value = {"files": []}

        grab.download(
            "https://youtube.com/watch?v=x&list=PL1",
            output=tmp_path,
            strip_playlist=True,
            record_history=False,
            engine=engine,
        )

        assert "list=" not in engine.download_media.call_args.kwargs["url"]

    def test_unknown_media_type(self, tmp_path):
        with pytest.raises(ValidationError, match="media_type"):
            grab.download(
                VIDEO_URL, output=tmp_path, media_type="gif", engine=MagicMock()
            )

    def test_cancel_is_passed_to_the_engine(self, tmp_path):
        engine = MagicMock()
        engine.download_media.side_effect = OperationCancelled("Download cancelled")

        with pytest.raises(OperationCancelled):
            grab.download(
                VIDEO_URL, output=tmp_path, should_cancel=lambda: True, engine=engine
            )
        assert engine.download_media.call_args.kwargs["should_cancel"]() is True
        assert DownloadHistory().get_recent() == []


def _fake_ydl(opts_seen: list, run):
    """A YoutubeDL stand-in whose download() calls `run(opts)`."""
    ydl = MagicMock()
    ydl.__enter__.return_value = ydl

    def _factory(opts):
        opts_seen.append(opts)
        ydl.download.side_effect = lambda urls: run(opts)
        return ydl

    return _factory


class TestEngine:
    def test_cancel_stops_the_download_and_removes_partial_files(self, tmp_path):
        target = tmp_path / "Song.webm"
        partial = tmp_path / "Song.webm.part"
        partial.write_bytes(b"half")
        keep = tmp_path / "Song.webm.keep"
        keep.write_bytes(b"not ours")

        def run(opts):
            for hook in opts["progress_hooks"]:
                hook(
                    {
                        "status": "downloading",
                        "filename": str(target),
                        "downloaded_bytes": 5,
                    }
                )

        opts_seen: list = []
        with patch("yt_dlp.YoutubeDL", side_effect=_fake_ydl(opts_seen, run)):
            with pytest.raises(OperationCancelled):
                NetworkEngine().download_media(
                    VIDEO_URL, tmp_path, should_cancel=lambda: True
                )

        assert not partial.exists()
        assert keep.exists()

    def test_reports_final_paths_after_post_processing(self, tmp_path):
        original = tmp_path / "Song.webm"
        final = tmp_path / "Song.mp3"
        final.write_bytes(b"mp3")

        def run(opts):
            info = {"id": "abc"}
            for hook in opts["progress_hooks"]:
                hook(
                    {"status": "finished", "filename": str(original), "info_dict": info}
                )
            for hook in opts["postprocessor_hooks"]:
                hook(
                    {
                        "status": "finished",
                        "info_dict": {"id": "abc", "filepath": str(final)},
                    }
                )

        opts_seen: list = []
        with patch("yt_dlp.YoutubeDL", side_effect=_fake_ydl(opts_seen, run)):
            result = NetworkEngine().download_media(
                VIDEO_URL, tmp_path, audio_only=True
            )

        assert result["files"] == [str(final)]

    def test_download_error_still_becomes_runtime_error(self, tmp_path):
        def run(opts):
            raise yt_dlp.utils.DownloadError("ERROR: HTTP Error 403")

        with patch("yt_dlp.YoutubeDL", side_effect=_fake_ydl([], run)):
            with pytest.raises(RuntimeError, match="HTTP Error 403"):
                NetworkEngine().download_media(VIDEO_URL, tmp_path)


def test_catalog_download_resolves_setting_defaults(tmp_path, monkeypatch):
    from max_cli.core.catalog import get_action
    from max_cli.core.catalog.runner import coerce_args

    monkeypatch.setattr(settings, "GRAB_QUALITY", "m")
    args = coerce_args(get_action("grab.download"), {"url": VIDEO_URL})

    assert args["quality"] == "m"
    assert args["output"] == settings.GRAB_DEFAULT_PATH
    assert isinstance(args["output"], Path)
