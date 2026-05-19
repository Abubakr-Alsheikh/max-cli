import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from max_cli.common.exceptions import ResourceNotFoundError
from max_cli.common.ffmpeg_resolver import (
    FFmpegResolver,
    MAX_CLI_BIN_DIR,
    RESOLUTION_CACHE_FILE,
    resolve_ffmpeg,
)


class TestFFmpegResolverTier1:
    @patch("shutil.which")
    def test_resolve_from_system_path(self, mock_which: MagicMock) -> None:
        mock_which.return_value = "/usr/bin/ffmpeg"
        with patch.object(FFmpegResolver, "get_cached_resolution", return_value=None):
            resolver = FFmpegResolver()
            result = resolver.resolve(auto_download=False)
            assert result == Path("/usr/bin/ffmpeg")

    @patch("shutil.which")
    def test_resolve_from_system_path_windows(self, mock_which: MagicMock) -> None:
        mock_which.return_value = "C:\\ffmpeg\\bin\\ffmpeg.exe"
        with patch.object(FFmpegResolver, "get_cached_resolution", return_value=None):
            with patch.object(
                FFmpegResolver, "_get_binary_name", return_value="ffmpeg.exe"
            ):
                resolver = FFmpegResolver()
                result = resolver.resolve(auto_download=False)
                assert result == Path("C:\\ffmpeg\\bin\\ffmpeg.exe")


class TestFFmpegResolverTier2:
    @patch("shutil.which", return_value=None)
    @patch.object(FFmpegResolver, "get_cached_resolution", return_value=None)
    def test_resolve_from_local_bin(
        self,
        mock_cached: MagicMock,
        mock_which: MagicMock,
        tmp_path: Path,
    ) -> None:
        fake_bin = tmp_path / "ffmpeg"
        fake_bin.touch()
        with patch.object(FFmpegResolver, "_validate_binary", return_value=True):
            with patch("max_cli.common.ffmpeg_resolver.MAX_CLI_BIN_DIR", tmp_path):
                resolver = FFmpegResolver()
                resolver.bin_dir = tmp_path
                resolver.local_path = fake_bin
                result = resolver.resolve(auto_download=False)
                assert result == fake_bin

    @patch("shutil.which", return_value=None)
    @patch.object(FFmpegResolver, "get_cached_resolution", return_value=None)
    def test_corrupted_local_bin_removed(
        self,
        mock_cached: MagicMock,
        mock_which: MagicMock,
        tmp_path: Path,
    ) -> None:
        fake_bin = tmp_path / "ffmpeg"
        fake_bin.touch()
        with patch.object(FFmpegResolver, "_validate_binary", return_value=False):
            with patch.object(FFmpegResolver, "_download_and_install") as mock_download:
                mock_download.return_value = Path("/fake/ffmpeg")
                with patch("max_cli.common.ffmpeg_resolver.MAX_CLI_BIN_DIR", tmp_path):
                    resolver = FFmpegResolver()
                    resolver.bin_dir = tmp_path
                    resolver.local_path = fake_bin
                    resolver.resolve(auto_download=True)
                    assert not fake_bin.exists()


class TestFFmpegResolverTier3:
    @patch("shutil.which", return_value=None)
    @patch.object(FFmpegResolver, "get_cached_resolution", return_value=None)
    def test_no_auto_download_raises(
        self,
        mock_cached: MagicMock,
        mock_which: MagicMock,
        tmp_path: Path,
    ) -> None:
        with patch("max_cli.common.ffmpeg_resolver.MAX_CLI_BIN_DIR", tmp_path):
            resolver = FFmpegResolver()
            resolver.bin_dir = tmp_path
            resolver.local_path = tmp_path / "ffmpeg"
            with pytest.raises(ResourceNotFoundError, match="FFmpeg not found"):
                resolver.resolve(auto_download=False)

    @patch("shutil.which", return_value=None)
    @patch.object(FFmpegResolver, "get_cached_resolution", return_value=None)
    @patch("max_cli.common.ffmpeg_resolver.console")
    @patch("rich.prompt.Confirm.ask", return_value=True)
    @patch.object(FFmpegResolver, "_download_binary")
    @patch.object(FFmpegResolver, "_validate_binary", return_value=True)
    @patch("max_cli.common.ffmpeg_resolver.log_success")
    def test_auto_download_flow(
        self,
        mock_log_success: MagicMock,
        mock_validate: MagicMock,
        mock_download: MagicMock,
        mock_confirm: MagicMock,
        mock_console: MagicMock,
        mock_cached: MagicMock,
        mock_which: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_console.is_terminal = True
        with patch("max_cli.common.ffmpeg_resolver.MAX_CLI_BIN_DIR", tmp_path):
            resolver = FFmpegResolver()
            resolver.bin_dir = tmp_path
            resolver.local_path = tmp_path / "ffmpeg"
            result = resolver.resolve(auto_download=True)
            mock_confirm.assert_called_once()
            mock_download.assert_called_once()
            assert result == resolver.local_path

    @patch("shutil.which", return_value=None)
    @patch.object(FFmpegResolver, "get_cached_resolution", return_value=None)
    @patch("max_cli.common.ffmpeg_resolver.console")
    @patch("rich.prompt.Confirm.ask", return_value=False)
    def test_user_declines_download(
        self,
        mock_confirm: MagicMock,
        mock_console: MagicMock,
        mock_cached: MagicMock,
        mock_which: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_console.is_terminal = True
        with patch("max_cli.common.ffmpeg_resolver.MAX_CLI_BIN_DIR", tmp_path):
            resolver = FFmpegResolver()
            resolver.bin_dir = tmp_path
            resolver.local_path = tmp_path / "ffmpeg"
            with pytest.raises(ResourceNotFoundError, match="download declined"):
                resolver.resolve(auto_download=True)

    @patch("shutil.which", return_value=None)
    @patch.object(FFmpegResolver, "get_cached_resolution", return_value=None)
    @patch("os.environ.get", return_value="1")
    def test_non_interactive_raises(
        self,
        mock_env: MagicMock,
        mock_cached: MagicMock,
        mock_which: MagicMock,
        tmp_path: Path,
    ) -> None:
        with patch("max_cli.common.ffmpeg_resolver.console") as mock_console:
            mock_console.is_terminal = True
            with patch("max_cli.common.ffmpeg_resolver.MAX_CLI_BIN_DIR", tmp_path):
                resolver = FFmpegResolver()
                resolver.bin_dir = tmp_path
                resolver.local_path = tmp_path / "ffmpeg"
                with pytest.raises(
                    ResourceNotFoundError, match="MAX_CLI_NON_INTERACTIVE"
                ):
                    resolver.resolve(auto_download=True)

    @patch("shutil.which", return_value=None)
    @patch.object(FFmpegResolver, "get_cached_resolution", return_value=None)
    @patch("max_cli.common.ffmpeg_resolver.console")
    def test_non_terminal_raises(
        self,
        mock_console: MagicMock,
        mock_cached: MagicMock,
        mock_which: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_console.is_terminal = False
        with patch("max_cli.common.ffmpeg_resolver.MAX_CLI_BIN_DIR", tmp_path):
            resolver = FFmpegResolver()
            resolver.bin_dir = tmp_path
            resolver.local_path = tmp_path / "ffmpeg"
            with pytest.raises(ResourceNotFoundError, match="MAX_CLI_NON_INTERACTIVE"):
                resolver.resolve(auto_download=True)

    @patch("shutil.which", return_value=None)
    @patch.object(FFmpegResolver, "get_cached_resolution", return_value=None)
    @patch("max_cli.common.ffmpeg_resolver.console")
    def test_unsupported_platform_raises(
        self,
        mock_console: MagicMock,
        mock_cached: MagicMock,
        mock_which: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_console.is_terminal = True
        with patch("platform.system", return_value="FreeBSD"):
            with patch("max_cli.common.ffmpeg_resolver.MAX_CLI_BIN_DIR", tmp_path):
                resolver = FFmpegResolver()
                resolver.bin_dir = tmp_path
                resolver.local_path = tmp_path / "ffmpeg"
                with pytest.raises(ResourceNotFoundError, match="Unsupported platform"):
                    resolver.resolve(auto_download=True)


class TestBinaryValidation:
    def test_validate_binary_success(self, tmp_path: Path) -> None:
        fake_binary = tmp_path / "ffmpeg"
        fake_binary.touch()
        resolver = FFmpegResolver()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=b"ffmpeg version 6.0 (C) 2024",
            )
            assert resolver._validate_binary(fake_binary) is True

    def test_validate_binary_failure(self, tmp_path: Path) -> None:
        fake_binary = tmp_path / "ffmpeg"
        fake_binary.touch()
        resolver = FFmpegResolver()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=b"")
            assert resolver._validate_binary(fake_binary) is False

    def test_validate_binary_timeout(self, tmp_path: Path) -> None:
        fake_binary = tmp_path / "ffmpeg"
        fake_binary.touch()
        resolver = FFmpegResolver()
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=10),
        ):
            assert resolver._validate_binary(fake_binary) is False

    def test_validate_binary_os_error(self, tmp_path: Path) -> None:
        fake_binary = tmp_path / "ffmpeg"
        fake_binary.touch()
        resolver = FFmpegResolver()
        with patch("subprocess.run", side_effect=OSError("Permission denied")):
            assert resolver._validate_binary(fake_binary) is False


class TestDownloadDirectBinary:
    @patch("urllib.request.urlopen")
    def test_download_direct_binary(
        self, mock_urlopen: MagicMock, tmp_path: Path
    ) -> None:
        mock_response = MagicMock()
        mock_response.read.side_effect = [b"fake_binary_data", b""]
        mock_response.getheader.return_value = None
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        resolver = FFmpegResolver()
        resolver.bin_dir = tmp_path
        resolver.local_path = tmp_path / "ffmpeg"

        resolver._download_binary(
            url="https://example.com/ffmpeg",
            binary_name="ffmpeg",
            extract_path=None,
        )

        assert resolver.local_path.exists()
        assert resolver.local_path.read_bytes() == b"fake_binary_data"


class TestDownloadZipExtraction:
    @patch("urllib.request.urlopen")
    def test_download_zip_extraction(
        self, mock_urlopen: MagicMock, tmp_path: Path
    ) -> None:
        import io
        import zipfile

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("ffmpeg-6.0/bin/ffmpeg.exe", b"fake_exe_data")
        zip_buffer.seek(0)
        zip_data = zip_buffer.read()

        mock_response = MagicMock()
        mock_response.read.side_effect = [zip_data, b""]
        mock_response.getheader.return_value = str(len(zip_data))
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        resolver = FFmpegResolver()
        resolver.bin_dir = tmp_path
        resolver.local_path = tmp_path / "ffmpeg.exe"

        resolver._download_binary(
            url="https://example.com/ffmpeg.zip",
            binary_name="ffmpeg.exe",
            extract_path="bin/ffmpeg.exe",
        )

        assert resolver.local_path.exists()
        assert resolver.local_path.read_bytes() == b"fake_exe_data"


class TestDownloadTarXzExtraction:
    @patch("urllib.request.urlopen")
    def test_download_tar_xz_extraction(
        self, mock_urlopen: MagicMock, tmp_path: Path
    ) -> None:
        import io
        import tarfile

        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode="w:xz") as tf:
            import tarfile as tf_mod

            data = b"fake_binary"
            member = tf_mod.TarInfo(name="ffmpeg-release-amd64-static/ffmpeg")
            member.size = len(data)
            tf.addfile(member, io.BytesIO(data))
        tar_buffer.seek(0)
        tar_data = tar_buffer.read()

        mock_response = MagicMock()
        mock_response.read.side_effect = [tar_data, b""]
        mock_response.getheader.return_value = str(len(tar_data))
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        resolver = FFmpegResolver()
        resolver.bin_dir = tmp_path
        resolver.local_path = tmp_path / "ffmpeg"

        resolver._download_binary(
            url="https://example.com/ffmpeg.tar.xz",
            binary_name="ffmpeg",
            extract_path=None,
        )

        assert resolver.local_path.exists()
        assert resolver.local_path.read_bytes() == b"fake_binary"


class TestCacheResolution:
    def test_cache_write_and_read(self, tmp_path: Path) -> None:
        cache_file = tmp_path / ".ffmpeg_resolved_path"
        with patch(
            "max_cli.common.ffmpeg_resolver.RESOLUTION_CACHE_FILE",
            cache_file,
        ):
            test_path = tmp_path / "ffmpeg"
            test_path.touch()
            resolver = FFmpegResolver()
            resolver._cache_resolution(test_path)

            assert cache_file.exists()
            assert cache_file.read_text() == str(test_path)

    def test_get_cached_resolution_valid(self, tmp_path: Path) -> None:
        cache_file = tmp_path / ".ffmpeg_resolved_path"
        test_path = tmp_path / "ffmpeg"
        test_path.touch()
        cache_file.write_text(str(test_path))

        with patch(
            "max_cli.common.ffmpeg_resolver.RESOLUTION_CACHE_FILE",
            cache_file,
        ):
            with patch.object(FFmpegResolver, "_validate_binary", return_value=True):
                cached = FFmpegResolver.get_cached_resolution()
                assert cached == test_path

    def test_get_cached_resolution_stale_cache(self, tmp_path: Path) -> None:
        cache_file = tmp_path / ".ffmpeg_resolved_path"
        test_path = tmp_path / "ffmpeg"
        test_path.touch()
        cache_file.write_text(str(test_path))

        with patch(
            "max_cli.common.ffmpeg_resolver.RESOLUTION_CACHE_FILE",
            cache_file,
        ):
            with patch.object(FFmpegResolver, "_validate_binary", return_value=False):
                cached = FFmpegResolver.get_cached_resolution()
                assert cached is None
                assert not cache_file.exists()

    def test_get_cached_resolution_no_cache_file(self) -> None:
        with patch.object(Path, "exists", return_value=False):
            cached = FFmpegResolver.get_cached_resolution()
            assert cached is None


class TestResolveFfmpegConvenience:
    @patch.object(FFmpegResolver, "get_cached_resolution")
    @patch.object(FFmpegResolver, "resolve")
    def test_resolve_ffmpeg_uses_cache(
        self,
        mock_resolve: MagicMock,
        mock_cached: MagicMock,
    ) -> None:
        mock_cached.return_value = Path("/cached/ffmpeg")
        result = resolve_ffmpeg(auto_download=True)
        assert result == Path("/cached/ffmpeg")
        mock_resolve.assert_not_called()

    @patch.object(FFmpegResolver, "get_cached_resolution", return_value=None)
    @patch.object(FFmpegResolver, "resolve")
    def test_resolve_ffmpeg_calls_resolver(
        self,
        mock_resolve: MagicMock,
        mock_cached: MagicMock,
    ) -> None:
        mock_resolve.return_value = Path("/resolved/ffmpeg")
        result = resolve_ffmpeg(auto_download=True)
        assert result == Path("/resolved/ffmpeg")
        mock_resolve.assert_called_once_with(auto_download=True)


class TestBinaryName:
    def test_binary_name_windows(self) -> None:
        with patch("platform.system", return_value="Windows"):
            resolver = FFmpegResolver()
            assert resolver.binary_name == "ffmpeg.exe"

    def test_binary_name_macos(self) -> None:
        with patch("platform.system", return_value="Darwin"):
            resolver = FFmpegResolver()
            assert resolver.binary_name == "ffmpeg"

    def test_binary_name_linux(self) -> None:
        with patch("platform.system", return_value="Linux"):
            resolver = FFmpegResolver()
            assert resolver.binary_name == "ffmpeg"


class TestConstants:
    def test_max_cli_bin_dir(self) -> None:
        assert MAX_CLI_BIN_DIR == Path.home() / ".max_cli" / "bin"

    def test_resolution_cache_file(self) -> None:
        assert (
            RESOLUTION_CACHE_FILE == Path.home() / ".max_cli" / ".ffmpeg_resolved_path"
        )
