"""Installing FFmpeg: package managers, download sources, checksums, fallbacks.

No network and no installer runs: `urlopen` and `subprocess.run` are mocked,
and `_read_text` serves the checksum files and Martin Riedl's page.
"""

import hashlib
import io
import subprocess
import tarfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from max_cli.common import ffmpeg_resolver
from max_cli.common.exceptions import ResourceNotFoundError
from max_cli.common.ffmpeg_resolver import (
    Download,
    FFmpegResolver,
    FFmpegSource,
    ffmpeg_sources,
)


def _resolver(tmp_path: Path, system: str = "Windows") -> FFmpegResolver:
    with patch("platform.system", return_value=system):
        resolver = FFmpegResolver()
    resolver.bin_dir = tmp_path
    resolver.local_path = tmp_path / resolver.binary_name
    return resolver


def _serve(mock_urlopen: MagicMock, payload: bytes) -> None:
    response = MagicMock()
    response.read.side_effect = [payload, b""]
    response.getheader.return_value = str(len(payload))
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = response


def _zip(entries: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class TestSources:
    def test_windows_tries_gyan_then_btbn(self):
        sources = ffmpeg_sources("Windows", "AMD64")

        assert [source.name for source in sources] == ["gyan.dev", "BtbN (GitHub)"]
        gyan = sources[0].downloads[0]
        assert gyan.checksum_url == gyan.url + ".sha256"

    @pytest.mark.parametrize(
        "machine, build", [("x86_64", "linux64"), ("aarch64", "linuxarm64")]
    )
    def test_linux_picks_the_build_for_the_machine(self, machine, build):
        btbn, static = ffmpeg_sources("Linux", machine)

        assert build in btbn.downloads[0].url
        assert btbn.downloads[0].checksum_name in btbn.downloads[0].url
        assert static.downloads[0].checksum_url == ""

    def test_macos_reads_the_newest_release_from_martin_riedls_page(self):
        page = """
        <a href="/download/macos/arm64/1700000000_8.0.1/ffmpeg.zip">
        <a href="/download/macos/arm64/1789931890_9.0.2/ffmpeg.zip">
        <a href="/download/macos/arm64/1791650033_N-127260-g7bc3576910/ffmpeg.zip">
        <a href="/download/macos/amd64/1795000000_9.1/ffmpeg.zip">
        """
        with patch.object(ffmpeg_resolver, "_read_text", return_value=page):
            (source,) = ffmpeg_sources("Darwin", "arm64")

        assert source.name == "Martin Riedl (9.0.2)"
        ffmpeg, ffprobe = source.downloads
        assert ffmpeg.url.endswith("/macos/arm64/1789931890_9.0.2/ffmpeg.zip")
        assert ffprobe.url.endswith("/ffprobe.zip")
        assert ffmpeg.checksum_url == ffmpeg.url + ".sha256"

    def test_macos_without_the_page_has_no_source(self):
        from urllib.error import URLError

        with patch.object(ffmpeg_resolver, "_read_text", side_effect=URLError("x")):
            assert ffmpeg_sources("Darwin", "arm64") == []


class TestChecksums:
    def test_a_list_of_checksums_gives_the_named_files_line(self):
        listing = "aaa  ffmpeg-master-latest-win64-gpl.zip\nbbb  other.zip\n"
        download = Download("u", "list", "other.zip")

        with patch.object(ffmpeg_resolver, "_read_text", return_value=listing):
            assert ffmpeg_resolver._expected_checksum(download) == "bbb"

    def test_a_single_checksum_file(self):
        with patch.object(ffmpeg_resolver, "_read_text", return_value="ABC123\n"):
            assert ffmpeg_resolver._expected_checksum(Download("u", "u.sha256")) == (
                "abc123"
            )

    def test_no_checksum_published(self):
        assert ffmpeg_resolver._expected_checksum(Download("u")) is None

    @patch("urllib.request.urlopen")
    def test_a_mismatch_keeps_nothing(self, mock_urlopen, tmp_path):
        _serve(mock_urlopen, _zip({"build/bin/ffmpeg.exe": b"exe"}))
        resolver = _resolver(tmp_path)

        with pytest.raises(ValueError, match="checksum"):
            resolver._download_binary(
                "https://example.com/f.zip", "ffmpeg.exe", sha256="0" * 64
            )

        assert list(tmp_path.iterdir()) == []

    @patch("urllib.request.urlopen")
    def test_a_match_unpacks_ffmpeg_and_ffprobe(self, mock_urlopen, tmp_path):
        payload = _zip(
            {
                "build/bin/ffmpeg.exe": b"exe",
                "build/bin/ffprobe.exe": b"probe",
                "build/bin/ffplay.exe": b"play",
                "build/doc/readme.txt": b"doc",
            }
        )
        _serve(mock_urlopen, payload)
        resolver = _resolver(tmp_path)

        resolver._download_binary(
            "https://example.com/f.zip",
            "ffmpeg.exe",
            sha256=hashlib.sha256(payload).hexdigest(),
        )

        assert sorted(path.name for path in tmp_path.iterdir()) == [
            "ffmpeg.exe",
            "ffprobe.exe",
        ]

    @patch("urllib.request.urlopen")
    def test_a_tar_gives_both_programs_and_no_folders(self, mock_urlopen, tmp_path):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:xz") as archive:
            for name in ("ffmpeg-master/bin/ffmpeg", "ffmpeg-master/bin/ffprobe"):
                info = tarfile.TarInfo(name)
                info.size = 3
                archive.addfile(info, io.BytesIO(b"bin"))
        _serve(mock_urlopen, buffer.getvalue())
        resolver = _resolver(tmp_path, system="Linux")

        resolver._download_binary("https://example.com/f.tar.xz", "ffmpeg")

        assert sorted(path.name for path in tmp_path.iterdir()) == [
            "ffmpeg",
            "ffprobe",
        ]


class TestInstall:
    @pytest.fixture(autouse=True)
    def interactive(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MAX_CLI_NON_INTERACTIVE", raising=False)
        monkeypatch.setattr(
            ffmpeg_resolver, "RESOLUTION_CACHE_FILE", tmp_path / ".resolved"
        )

    def test_the_package_manager_comes_first(self, tmp_path, monkeypatch):
        resolver = _resolver(tmp_path)
        installed = tmp_path / "winget" / "ffmpeg.exe"
        monkeypatch.setattr(
            resolver, "_package_manager", lambda: ["winget", "install", "x"]
        )
        monkeypatch.setattr(resolver, "find_installed", lambda: installed)
        questions = []

        with (
            patch(
                "subprocess.run", return_value=subprocess.CompletedProcess([], 0)
            ) as run,
            patch.object(ffmpeg_resolver, "ffmpeg_sources") as sources,
        ):
            path = resolver._download_and_install(
                lambda question: questions.append(question) or True
            )

        assert path == installed
        assert run.call_args.args[0] == ["winget", "install", "x"]
        assert "with winget" in questions[0]
        sources.assert_not_called()

    def test_a_failed_package_manager_falls_back_to_a_download(
        self, tmp_path, monkeypatch
    ):
        resolver = _resolver(tmp_path)
        monkeypatch.setattr(resolver, "_package_manager", lambda: ["winget"])
        monkeypatch.setattr(resolver, "_validate_binary", lambda path: True)
        source = FFmpegSource("test", (Download("https://example.com/f.exe"),))
        monkeypatch.setattr(ffmpeg_resolver, "ffmpeg_sources", lambda system: [source])

        def fake_download(url, binary_name, **kwargs):
            (tmp_path / binary_name).write_bytes(b"exe")

        monkeypatch.setattr(resolver, "_download_binary", fake_download)
        with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 1)):
            path = resolver._download_and_install(lambda question: True)

        assert path == tmp_path / "ffmpeg.exe"

    def test_the_next_source_takes_over(self, tmp_path, monkeypatch):
        from urllib.error import HTTPError

        resolver = _resolver(tmp_path)
        monkeypatch.setattr(resolver, "_package_manager", lambda: None)
        monkeypatch.setattr(resolver, "_validate_binary", lambda path: True)
        sources = [
            FFmpegSource("gone", (Download("https://gone.example/f.zip"),)),
            FFmpegSource("works", (Download("https://works.example/f.zip"),)),
        ]
        monkeypatch.setattr(ffmpeg_resolver, "ffmpeg_sources", lambda system: sources)
        tried = []

        def fake_download(url, binary_name, **kwargs):
            tried.append(url)
            if "gone" in url:
                raise HTTPError(url, 404, "Not Found", None, None)
            (tmp_path / binary_name).write_bytes(b"exe")

        monkeypatch.setattr(resolver, "_download_binary", fake_download)

        assert resolver._download_and_install(lambda question: True).exists()
        assert tried == ["https://gone.example/f.zip", "https://works.example/f.zip"]

    def test_when_everything_fails_it_names_each_source_and_the_fix(
        self, tmp_path, monkeypatch
    ):
        from urllib.error import HTTPError

        resolver = _resolver(tmp_path)
        monkeypatch.setattr(resolver, "_package_manager", lambda: None)
        monkeypatch.setattr(
            ffmpeg_resolver,
            "ffmpeg_sources",
            lambda system: [FFmpegSource("gyan.dev", (Download("u"),))],
        )

        def not_found(url, binary_name, **kwargs):
            raise HTTPError(url, 404, "Not Found", None, None)

        monkeypatch.setattr(resolver, "_download_binary", not_found)

        with pytest.raises(ResourceNotFoundError) as caught:
            resolver._download_and_install(lambda question: True)

        message = str(caught.value)
        assert "gyan.dev: HTTP Error 404" in message
        assert "winget install Gyan.FFmpeg" in message
        assert "Traceback" not in message


class TestFinding:
    def test_a_fresh_winget_install_is_found_before_path_knows(
        self, tmp_path, monkeypatch
    ):
        resolver = _resolver(tmp_path / "bin")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        link = tmp_path / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
        link.parent.mkdir(parents=True)
        link.write_bytes(b"exe")
        monkeypatch.setattr(resolver, "_validate_binary", lambda path: True)

        with patch("shutil.which", return_value=None):
            assert resolver.find_installed() == link

    def test_homebrew_places_on_macos(self, tmp_path):
        resolver = _resolver(tmp_path, system="Darwin")

        assert Path("/opt/homebrew/bin/ffmpeg") in resolver.known_locations()

    def test_package_manager_only_when_installed(self, tmp_path):
        resolver = _resolver(tmp_path)

        with patch("shutil.which", return_value=r"C:\winget.exe"):
            assert resolver._package_manager()[:2] == [r"C:\winget.exe", "install"]
        with patch("shutil.which", return_value=None):
            assert resolver._package_manager() is None
