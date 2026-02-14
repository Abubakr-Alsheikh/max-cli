import pytest
from unittest.mock import patch, MagicMock
from max_cli.core.network_engine import NetworkEngine


class TestNetworkEngine:
    """Tests for network/download operations."""

    @patch("shutil.which")
    def test_init_with_js(self, mock_which):
        """Test initialization with JS runtime."""
        mock_which.side_effect = lambda x: x == "node"

        engine = NetworkEngine()
        assert engine.has_js is True

    @patch("shutil.which")
    def test_init_without_js(self, mock_which):
        """Test initialization without JS runtime."""
        mock_which.return_value = None

        engine = NetworkEngine()
        assert engine.has_js is False

    @patch("yt_dlp.YoutubeDL")
    @patch("shutil.which")
    def test_get_info(self, mock_which, mock_ytdl):
        """Test getting info from URL."""
        mock_which.return_value = None

        mock_instance = MagicMock()
        mock_instance.extract_info.return_value = {
            "title": "Test Video",
            "duration": 120,
            "entries": [],
        }
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        engine = NetworkEngine()
        result = engine.get_info("https://example.com/video")

        assert "title" in result

    @patch("yt_dlp.YoutubeDL")
    @patch("shutil.which")
    def test_download_media_video(self, mock_which, mock_ytdl, tmp_path):
        """Test downloading video."""
        mock_which.return_value = None

        mock_instance = MagicMock()
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        engine = NetworkEngine()
        output_path = tmp_path / "downloads"
        output_path.mkdir()

        engine.download_media(
            "https://example.com/video",
            output_path,
            quality="h",
            audio_only=False,
        )

        mock_instance.download.assert_called_once()

    @patch("yt_dlp.YoutubeDL")
    @patch("shutil.which")
    def test_download_media_audio(self, mock_which, mock_ytdl, tmp_path):
        """Test downloading audio only."""
        mock_which.return_value = None

        mock_instance = MagicMock()
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        engine = NetworkEngine()
        output_path = tmp_path / "downloads"
        output_path.mkdir()

        engine.download_media(
            "https://example.com/video",
            output_path,
            quality="h",
            audio_only=True,
        )

        mock_instance.download.assert_called_once()

    @patch("yt_dlp.YoutubeDL")
    @patch("shutil.which")
    def test_download_media_with_error(self, mock_which, mock_ytdl, tmp_path):
        """Test download error handling."""
        import yt_dlp

        mock_which.return_value = None

        mock_instance = MagicMock()
        mock_instance.download.side_effect = yt_dlp.utils.DownloadError(
            "Download failed"
        )
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        engine = NetworkEngine()
        output_path = tmp_path / "downloads"
        output_path.mkdir()

        with pytest.raises(RuntimeError, match="Download failed"):
            engine.download_media(
                "https://example.com/video",
                output_path,
                quality="h",
            )

    @patch("yt_dlp.YoutubeDL")
    @patch("shutil.which")
    def test_download_with_playlist(self, mock_which, mock_ytdl, tmp_path):
        """Test downloading with playlist options."""
        mock_which.return_value = None

        mock_instance = MagicMock()
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        engine = NetworkEngine()
        output_path = tmp_path / "downloads"
        output_path.mkdir()

        engine.download_media(
            "https://example.com/playlist",
            output_path,
            quality="m",
            playlist_items="1-10",
            no_playlist=False,
        )

        mock_instance.download.assert_called_once()
