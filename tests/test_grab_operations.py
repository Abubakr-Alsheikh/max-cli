"""`core/operations/grab.py` and the engine features it needs (grab-page-redesign.md, G1)."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yt_dlp

from max_cli.common.exceptions import OperationCancelled, ValidationError
from max_cli.config import settings
from max_cli.core.engines.download_history import DownloadHistory
from max_cli.core.engines.download_tags import DownloadTags
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

    def test_tags_and_folders_reach_the_engine(self, tmp_path):
        engine = MagicMock()
        engine.download_media.return_value = {"files": []}

        grab.download(
            VIDEO_URL,
            output=tmp_path,
            artist=" Me ",
            album="Mine",
            genre="",
            year="2024",
            track_numbers=False,
            sort_into="artist/album",
            record_history=False,
            engine=engine,
        )

        tags = engine.download_media.call_args.kwargs["tags"]
        assert tags == DownloadTags(
            artist="Me",
            album="Mine",
            year="2024",
            track_numbers=False,
            sort_into="artist/album",
        )

    def test_unknown_folder_sorting(self, tmp_path):
        with pytest.raises(ValidationError, match="sort_into"):
            grab.download(
                VIDEO_URL, output=tmp_path, sort_into="genre", engine=MagicMock()
            )

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


class TestTokenHelperTimeout:
    TIMEOUT = subprocess.TimeoutExpired(["deno", "run", "--allow-read=C:/cache"], 15)

    def test_probe_retries_once_then_succeeds(self):
        ydl = MagicMock()
        ydl.__enter__.return_value = ydl
        ydl.extract_info.side_effect = [self.TIMEOUT, VIDEO_INFO]
        with patch("yt_dlp.YoutubeDL", return_value=ydl):
            info = NetworkEngine().probe_info(VIDEO_URL)

        assert info["title"] == "Trailer"
        assert ydl.extract_info.call_count == 2

    def test_probe_gives_a_readable_error_after_two_timeouts(self):
        ydl = MagicMock()
        ydl.__enter__.return_value = ydl
        ydl.extract_info.side_effect = [self.TIMEOUT, self.TIMEOUT]
        with patch("yt_dlp.YoutubeDL", return_value=ydl):
            with pytest.raises(RuntimeError, match="token helper") as error:
                NetworkEngine().probe_info(VIDEO_URL)

        assert "--allow-read" not in str(error.value)

    def test_download_timeout_is_readable(self, tmp_path):
        def run(opts):
            raise self.TIMEOUT

        with patch("yt_dlp.YoutubeDL", side_effect=_fake_ydl([], run)):
            with pytest.raises(RuntimeError, match="token helper"):
                NetworkEngine().download_media(VIDEO_URL, tmp_path)


RICH_INFO = {
    **VIDEO_INFO,
    "webpage_url_domain": "www.youtube.com",
    "upload_date": "20240501",
    "view_count": 1_234_567,
    "like_count": 34_500,
    "subtitles": {"en": [], "ar": [], "live_chat": []},
    "automatic_captions": {"en": []},
    "chapters": [{"title": "Intro"}, {"title": "Main"}],
    "live_status": "not_live",
    "formats": [
        *VIDEO_INFO["formats"],
        {
            "format_id": "299",
            "vcodec": "avc1",
            "acodec": "none",
            "height": 1080,
            "fps": 60,
            "tbr": 6000,
            "filesize": 120_000_000,
        },
    ],
}


class TestProbeDetails:
    def test_video_details_for_the_preview(self):
        engine = MagicMock()
        engine.probe_info.return_value = RICH_INFO

        media = grab.probe(VIDEO_URL, engine=engine)

        assert media.site == "youtube.com"
        assert media.upload_date == "2024-05-01"
        assert (media.view_count, media.like_count) == (1_234_567, 34_500)
        # yt-dlp lists the live chat replay as a subtitle track.
        assert media.subtitle_languages == ["ar", "en"]
        assert media.has_auto_captions
        assert media.chapter_count == 2
        assert not media.is_live
        assert (media.audio_codec, media.audio_bitrate) == ("mp4a", 128)
        # The 60 fps stream has the highest bitrate at 1080p.
        assert media.qualities[0].label == "1080p60"

    def test_missing_details_stay_empty(self):
        engine = MagicMock()
        engine.probe_info.return_value = {"title": "Bare", "formats": []}

        media = grab.probe("https://example.com/v", engine=engine)

        assert media.site == "example.com"
        assert (media.upload_date, media.view_count, media.chapter_count) == (
            "",
            None,
            0,
        )
        assert media.subtitle_languages == []

    def test_playlist_length_adds_up_its_items(self):
        engine = MagicMock()
        engine.probe_info.return_value = PLAYLIST_INFO

        media = grab.probe("https://youtube.com/playlist?list=PL1", engine=engine)

        assert media.total_duration == 192 + 245


class TestYoutubeFix:
    def _engine(self, available):
        engine = MagicMock()
        engine.pot_provider_available.side_effect = available
        engine.install_pot_provider.return_value = {"ok": True, "output": ""}
        engine.setup_pot_server.return_value = {"ok": True, "output": ""}
        return engine

    def test_status(self):
        engine = self._engine([True])
        with patch("shutil.which", return_value=None):
            status = grab.youtube_fix_status(engine=engine)

        assert status == grab.YoutubeFixStatus(installed=True, deno_found=False)

    def test_needs_deno(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(ValidationError, match="Deno"):
                grab.install_youtube_fix(engine=self._engine([False]))

    def test_already_installed_does_nothing(self):
        engine = self._engine([True])
        with patch("shutil.which", return_value="deno"):
            result = grab.install_youtube_fix(engine=engine)

        assert result.ok and "already" in result.message
        engine.install_pot_provider.assert_not_called()

    def test_installs_plugin_then_server(self):
        engine = self._engine([False, True])
        with patch("shutil.which", return_value="deno"):
            result = grab.install_youtube_fix(engine=engine)

        assert result.ok
        engine.install_pot_provider.assert_called_once()
        engine.setup_pot_server.assert_called_once()

    def test_a_failed_step_says_which(self):
        from max_cli.common.exceptions import ProcessingError

        engine = self._engine([False])
        engine.install_pot_provider.return_value = {"ok": False, "output": "no pip"}
        with patch("shutil.which", return_value="deno"):
            with pytest.raises(ProcessingError, match="yt-dlp plugin failed:\nno pip"):
                grab.install_youtube_fix(engine=engine)
        engine.setup_pot_server.assert_not_called()

    def test_provider_not_seen_after_install(self):
        from max_cli.common.exceptions import ProcessingError

        engine = self._engine([False, False])
        with patch("shutil.which", return_value="deno"):
            with pytest.raises(ProcessingError, match="Restart max"):
                grab.install_youtube_fix(engine=engine)


class TestTagsInTheEngine:
    def test_download_media_names_files_by_the_folders_and_adds_the_tag_steps(
        self, tmp_path
    ):
        with patch("yt_dlp.YoutubeDL") as youtube_dl:
            ydl = youtube_dl.return_value.__enter__.return_value
            NetworkEngine().download_media(
                VIDEO_URL,
                tmp_path,
                audio_only=True,
                tags=DownloadTags(sort_into="album"),
            )

        options = youtube_dl.call_args.args[0]
        assert options["outtmpl"] == str(
            tmp_path / "%(max_folder_1|.)s/%(max_folder_2|.)s/%(title)s.%(ext)s"
        )
        steps = [call.kwargs["when"] for call in ydl.add_post_processor.call_args_list]
        assert steps == ["pre_process", "post_process"]

    def test_a_queued_download_keeps_its_tags(self, tmp_path):
        from max_cli.core.engines.network_engine import (
            _download_executor,
            make_download_task,
        )

        tags = DownloadTags(artist="Me", sort_into="artist/album")
        task = make_download_task(VIDEO_URL, output_path=tmp_path, tags=tags)

        with patch.object(NetworkEngine, "download_media") as download_media:
            with patch("max_cli.core.engines.network_engine._log_download"):
                _download_executor(task)

        assert task.payload["artist"] == "Me"
        assert download_media.call_args.kwargs["tags"] == tags
