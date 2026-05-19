import pytest
from unittest.mock import patch, MagicMock

from max_cli.common.events import (
    EventEmitter,
    DownloadProgressEvent,
    DownloadCompleteEvent,
    EventType,
    get_emitter,
    reset_emitter,
)
from max_cli.core.engines.network_engine import NetworkEngine
from max_cli.interface.event_subscriber import EventSubscriber


class TestDownloadProgressEvent:
    def test_defaults(self):
        event = DownloadProgressEvent()
        assert event.type == EventType.DOWNLOAD_PROGRESS
        assert event.url == ""
        assert event.downloaded_bytes == 0
        assert event.total_bytes == 0
        assert event.speed == 0.0
        assert event.eta == 0
        assert event.percentage == 0.0

    def test_with_values(self):
        event = DownloadProgressEvent(
            url="https://example.com",
            filename="video.mp4",
            downloaded_bytes=5000000,
            total_bytes=10000000,
            speed=1234567.0,
            eta=12,
            percentage=50.0,
        )
        assert event.url == "https://example.com"
        assert event.filename == "video.mp4"
        assert event.downloaded_bytes == 5000000
        assert event.total_bytes == 10000000
        assert event.speed == 1234567.0
        assert event.eta == 12
        assert event.percentage == 50.0


class TestDownloadCompleteEvent:
    def test_defaults(self):
        event = DownloadCompleteEvent()
        assert event.type == EventType.DOWNLOAD_COMPLETE
        assert event.url == ""
        assert event.filename == ""
        assert event.total_bytes == 0

    def test_with_values(self):
        event = DownloadCompleteEvent(
            url="https://example.com",
            filename="video.mp4",
            total_bytes=10000000,
        )
        assert event.url == "https://example.com"
        assert event.filename == "video.mp4"
        assert event.total_bytes == 10000000


class TestNetworkEngineDownloadProgress:
    def setup_method(self):
        reset_emitter()

    def teardown_method(self):
        reset_emitter()

    @patch("yt_dlp.YoutubeDL")
    @patch("shutil.which")
    def test_download_emits_progress_event(self, mock_which, mock_ytdl, tmp_path):
        mock_which.return_value = None
        engine = NetworkEngine()
        captured_events = []

        def capture_hook(d: dict):
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                downloaded = d.get("downloaded_bytes", 0)
                pct = (downloaded / total * 100) if total > 0 else 0.0
                captured_events.append(
                    DownloadProgressEvent(
                        url="https://example.com/video",
                        filename=d.get("filename", ""),
                        downloaded_bytes=downloaded,
                        total_bytes=total,
                        speed=d.get("speed", 0),
                        eta=d.get("eta", 0),
                        percentage=pct,
                    )
                )

        mock_instance = MagicMock()
        mock_instance.download.side_effect = lambda urls: capture_hook(
            {
                "status": "downloading",
                "total_bytes": 10000000,
                "downloaded_bytes": 5000000,
                "speed": 1234567.0,
                "eta": 5,
                "filename": "/path/video.mp4",
            }
        )
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        output_path = tmp_path / "downloads"
        output_path.mkdir()

        engine.download_media(
            "https://example.com/video",
            output_path,
            quality="h",
            audio_only=False,
        )

        assert len(captured_events) == 1
        event = captured_events[0]
        assert event.total_bytes == 10000000
        assert event.downloaded_bytes == 5000000
        assert event.percentage == 50.0
        assert event.speed == 1234567.0
        assert event.eta == 5

    @patch("yt_dlp.YoutubeDL")
    @patch("shutil.which")
    def test_download_emits_complete_event(self, mock_which, mock_ytdl, tmp_path):
        mock_which.return_value = None
        engine = NetworkEngine()
        captured_events = []

        def capture_hook(d: dict):
            status = d.get("status")
            if status == "finished":
                captured_events.append(
                    DownloadCompleteEvent(
                        url="https://example.com/video",
                        filename=d.get("filename", ""),
                        total_bytes=d.get("total_bytes", 0),
                    )
                )

        mock_instance = MagicMock()
        mock_instance.download.side_effect = lambda urls: capture_hook(
            {
                "status": "finished",
                "total_bytes": 10000000,
                "filename": "/path/video.mp4",
            }
        )
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        output_path = tmp_path / "downloads"
        output_path.mkdir()

        engine.download_media(
            "https://example.com/video",
            output_path,
            quality="h",
            audio_only=False,
        )

        assert len(captured_events) == 1
        event = captured_events[0]
        assert event.total_bytes == 10000000
        assert event.filename == "/path/video.mp4"

    @patch("yt_dlp.YoutubeDL")
    @patch("shutil.which")
    def test_progress_uses_total_bytes_estimate_when_total_bytes_missing(
        self, mock_which, mock_ytdl, tmp_path
    ):
        mock_which.return_value = None
        engine = NetworkEngine()
        captured_events = []

        def capture_hook(d: dict):
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                downloaded = d.get("downloaded_bytes", 0)
                pct = (downloaded / total * 100) if total > 0 else 0.0
                captured_events.append(
                    DownloadProgressEvent(
                        url="https://example.com/video",
                        downloaded_bytes=downloaded,
                        total_bytes=total,
                        percentage=pct,
                    )
                )

        mock_instance = MagicMock()
        mock_instance.download.side_effect = lambda urls: capture_hook(
            {
                "status": "downloading",
                "total_bytes_estimate": 8000000,
                "downloaded_bytes": 2000000,
                "speed": 500000.0,
                "eta": 12,
            }
        )
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        output_path = tmp_path / "downloads"
        output_path.mkdir()

        engine.download_media(
            "https://example.com/video",
            output_path,
            quality="h",
            audio_only=False,
        )

        assert len(captured_events) == 1
        event = captured_events[0]
        assert event.total_bytes == 8000000
        assert event.percentage == pytest.approx(25.0)

    @patch("yt_dlp.YoutubeDL")
    @patch("shutil.which")
    def test_progress_zero_when_no_total(self, mock_which, mock_ytdl, tmp_path):
        mock_which.return_value = None
        engine = NetworkEngine()
        captured_events = []

        def capture_hook(d: dict):
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                downloaded = d.get("downloaded_bytes", 0)
                pct = (downloaded / total * 100) if total > 0 else 0.0
                captured_events.append(
                    DownloadProgressEvent(
                        url="https://example.com/video",
                        downloaded_bytes=downloaded,
                        total_bytes=total,
                        percentage=pct,
                    )
                )

        mock_instance = MagicMock()
        mock_instance.download.side_effect = lambda urls: capture_hook(
            {
                "status": "downloading",
                "downloaded_bytes": 1000000,
            }
        )
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        output_path = tmp_path / "downloads"
        output_path.mkdir()

        engine.download_media(
            "https://example.com/video",
            output_path,
            quality="h",
            audio_only=False,
        )

        assert len(captured_events) == 1
        assert captured_events[0].percentage == 0.0
        assert captured_events[0].total_bytes == 0

    @patch("yt_dlp.YoutubeDL")
    @patch("shutil.which")
    def test_progress_hook_backward_compatibility(
        self, mock_which, mock_ytdl, tmp_path
    ):
        mock_which.return_value = None
        engine = NetworkEngine()
        hook_calls = []

        def custom_hook(d: dict):
            hook_calls.append(d)

        mock_instance = MagicMock()
        mock_instance.download.side_effect = lambda urls: custom_hook(
            {
                "status": "downloading",
                "total_bytes": 10000000,
                "downloaded_bytes": 5000000,
            }
        )
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        output_path = tmp_path / "downloads"
        output_path.mkdir()

        engine.download_media(
            "https://example.com/video",
            output_path,
            quality="h",
            audio_only=False,
            progress_hook=custom_hook,
        )

        assert len(hook_calls) == 1
        assert hook_calls[0]["status"] == "downloading"
        assert hook_calls[0]["total_bytes"] == 10000000

    @patch("yt_dlp.YoutubeDL")
    @patch("shutil.which")
    def test_emits_to_global_emitter(self, mock_which, mock_ytdl, tmp_path):
        mock_which.return_value = None
        engine = NetworkEngine()
        reset_emitter()
        emitter = get_emitter()
        received = []
        emitter.subscribe(lambda e: received.append(e))

        mock_instance = MagicMock()
        mock_instance.download.side_effect = lambda urls: None
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        output_path = tmp_path / "downloads"
        output_path.mkdir()

        engine.download_media(
            "https://example.com/video",
            output_path,
            quality="h",
            audio_only=False,
        )

        emitter.unsubscribe(lambda e: received.append(e))


class TestEventSubscriberDownloadHandlers:
    def setup_method(self):
        self.emitter = EventEmitter()
        self.subscriber = EventSubscriber(self.emitter)

    def teardown_method(self):
        self.subscriber.unsubscribe()
        self.emitter.clear()

    def test_download_progress_creates_task(self):
        self.subscriber.subscribe()
        self.subscriber.create_progress_context(1, "Grabbing Video...")
        self.emitter.emit(
            DownloadProgressEvent(
                url="https://example.com",
                filename="/path/test_video.mp4",
                downloaded_bytes=5000000,
                total_bytes=10000000,
                speed=1234567.0,
                eta=5,
                percentage=50.0,
            )
        )
        assert self.subscriber._download_task is not None
        self.subscriber.unsubscribe()

    def test_download_progress_updates_task(self):
        self.subscriber.subscribe()
        self.subscriber.create_progress_context(1, "Grabbing Video...")
        self.emitter.emit(
            DownloadProgressEvent(
                url="https://example.com",
                filename="video.mp4",
                downloaded_bytes=2500000,
                total_bytes=10000000,
                speed=500000.0,
                eta=15,
                percentage=25.0,
            )
        )
        assert self.subscriber._download_task is not None
        task = self.subscriber._progress.tasks[self.subscriber._download_task]
        assert task.completed == 25.0
        self.subscriber.unsubscribe()

    def test_download_complete_marks_done(self):
        self.subscriber.subscribe()
        self.subscriber.create_progress_context(1, "Grabbing Video...")
        self.emitter.emit(
            DownloadProgressEvent(
                url="https://example.com",
                filename="video.mp4",
                downloaded_bytes=5000000,
                total_bytes=10000000,
                percentage=50.0,
            )
        )
        task_before = self.subscriber._download_task
        assert task_before is not None

        self.emitter.emit(
            DownloadCompleteEvent(
                url="https://example.com",
                filename="video.mp4",
                total_bytes=10000000,
            )
        )

        task = self.subscriber._progress.tasks[task_before]
        assert task.completed == 100
        assert self.subscriber._download_task is None
        self.subscriber.unsubscribe()

    def test_download_progress_without_progress_context(self):
        self.subscriber.subscribe()
        self.emitter.emit(
            DownloadProgressEvent(
                url="https://example.com",
                filename="video.mp4",
                downloaded_bytes=5000000,
                total_bytes=10000000,
                percentage=50.0,
            )
        )
        assert self.subscriber._download_task is None
        self.subscriber.unsubscribe()

    def test_download_progress_handles_filename_with_path(self):
        self.subscriber.subscribe()
        self.subscriber.create_progress_context(1, "Grabbing Video...")
        self.emitter.emit(
            DownloadProgressEvent(
                url="https://example.com",
                filename="/home/user/downloads/My Video Title.mp4",
                downloaded_bytes=5000000,
                total_bytes=10000000,
                percentage=50.0,
            )
        )
        assert self.subscriber._download_task is not None
        task = self.subscriber._progress.tasks[self.subscriber._download_task]
        assert "My Video Title.mp4" in task.description
        self.subscriber.unsubscribe()
