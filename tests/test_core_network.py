import pytest
from unittest.mock import patch, MagicMock
from max_cli.core.engines.network_engine import NetworkEngine


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

    @patch("yt_dlp.YoutubeDL")
    @patch("shutil.which")
    def test_download_media_player_client(self, mock_which, mock_ytdl, tmp_path):
        """Test that player_client is passed as extractor_args."""
        mock_which.return_value = None

        mock_instance = MagicMock()
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        engine = NetworkEngine()
        output_path = tmp_path / "downloads"
        output_path.mkdir()

        engine.download_media(
            "https://www.youtube.com/watch?v=abc",
            output_path,
            quality="h",
            player_client="tv",
        )

        _, kwargs = mock_ytdl.call_args
        opts = kwargs.get("opts") or mock_ytdl.call_args.args[0]
        extractor_args = opts.get("extractor_args", {})
        assert extractor_args["youtube"]["player_client"] == ["tv"]

    @patch("yt_dlp.YoutubeDL")
    @patch("shutil.which")
    def test_download_media_auto_pot_provider(
        self, mock_which, mock_ytdl, tmp_path
    ):
        """Test that a PO token provider triggers android client + fetch_pot."""
        mock_which.return_value = None

        mock_instance = MagicMock()
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        engine = NetworkEngine()
        with patch.object(
            engine, "pot_provider_available", return_value=True
        ):
            output_path = tmp_path / "downloads"
            output_path.mkdir()

            engine.download_media(
                "https://www.youtube.com/watch?v=abc",
                output_path,
                quality="h",
            )

            _, kwargs = mock_ytdl.call_args
            opts = kwargs.get("opts") or mock_ytdl.call_args.args[0]
            extractor_args = opts.get("extractor_args", {})
            assert extractor_args["youtube"]["player_client"] == ["android"]
            assert extractor_args["youtube"]["fetch_pot"] == "always"

    @patch("yt_dlp.YoutubeDL")
    @patch("shutil.which")
    def test_download_media_pot_provider_non_youtube(
        self, mock_which, mock_ytdl, tmp_path
    ):
        """Test that non-YouTube URLs do not get android player_client."""
        mock_which.return_value = None

        mock_instance = MagicMock()
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        engine = NetworkEngine()
        with patch.object(
            engine, "pot_provider_available", return_value=True
        ):
            output_path = tmp_path / "downloads"
            output_path.mkdir()

            engine.download_media(
                "https://vimeo.com/12345",
                output_path,
                quality="h",
            )

            _, kwargs = mock_ytdl.call_args
            opts = kwargs.get("opts") or mock_ytdl.call_args.args[0]
            assert "extractor_args" not in opts

    @patch("yt_dlp.YoutubeDL")
    def test_pot_provider_available(self, mock_ytdl):
        """Test PO token provider detection from the yt-dlp registry."""
        engine = NetworkEngine()

        with patch(
            "yt_dlp.extractor.youtube.pot._registry._pot_providers",
            new=MagicMock(value={"BgUtilHTTP": object()}),
        ):
            assert engine.pot_provider_available() is True

        with patch(
            "yt_dlp.extractor.youtube.pot._registry._pot_providers",
            new=MagicMock(value={}),
        ):
            assert engine.pot_provider_available() is False

    @patch("subprocess.run")
    def test_install_pot_provider_success(self, mock_run):
        """Test pip install of the POT provider plugin."""
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        engine = NetworkEngine()
        result = engine.install_pot_provider()
        assert result["ok"] is True
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_setup_pot_server_clones_and_installs(self, mock_run, tmp_path):
        """Test server setup skips clone when repo already exists."""
        mock_run.return_value = MagicMock(returncode=0, stdout="done", stderr="")
        engine = NetworkEngine()
        server_dir = tmp_path / "bgutil" / "server"
        server_dir.mkdir(parents=True)
        with (
            patch(
                "max_cli.core.engines.network_engine.POT_SERVER_DIR",
                tmp_path / "bgutil",
            ),
            patch("shutil.which", return_value="deno"),
            patch.object(engine, "_ensure_canvas_binary", return_value=False),
        ):
            result = engine.setup_pot_server()
        assert result["ok"] is True
        assert mock_run.call_count == 1


class TestCanvasMirrorExtraction:
    """The canvas mirror tarball must not write outside the package (hardening 1.12)."""

    @staticmethod
    def _canvas_pkg(tmp_path):
        pkg = (
            tmp_path
            / "server"
            / "node_modules"
            / ".deno"
            / "canvas@3.2.1"
            / "node_modules"
            / "canvas"
        )
        pkg.mkdir(parents=True)
        return pkg

    @staticmethod
    def _serve_tar(entries):
        import io
        import tarfile

        def fake_urlretrieve(url, destination):
            with tarfile.open(destination, "w:gz") as archive:
                for name, payload in entries.items():
                    info = tarfile.TarInfo(name=name)
                    info.size = len(payload)
                    archive.addfile(info, io.BytesIO(payload))

        return fake_urlretrieve

    def test_valid_tarball_installs_binary(self, tmp_path):
        pkg = self._canvas_pkg(tmp_path)
        tarball = {"build/Release/canvas.node": b"native"}

        with patch("urllib.request.urlretrieve", self._serve_tar(tarball)):
            fixed = NetworkEngine()._ensure_canvas_binary(tmp_path / "server")

        assert fixed is True
        assert (pkg / "build" / "Release" / "canvas.node").read_bytes() == b"native"

    def test_traversing_tarball_is_rejected(self, tmp_path):
        self._canvas_pkg(tmp_path)
        escape = tmp_path / "escaped.txt"
        tarball = {"../../../../../../escaped.txt": b"evil"}

        with patch("urllib.request.urlretrieve", self._serve_tar(tarball)):
            fixed = NetworkEngine()._ensure_canvas_binary(tmp_path / "server")

        assert fixed is False
        assert not escape.exists()
