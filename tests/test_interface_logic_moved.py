"""Logic moved from the CLI layer into engines (hardening Phase 3)."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from max_cli.core.engines.ai_engine import (
    IMAGE_DOWNLOAD_TIMEOUT_SECONDS,
    download_image,
    find_searchable_files,
)
from max_cli.core.engines.network_engine import strip_playlist_params
from max_cli.core.engines.pdf_engine import PDFEngine


class TestStripPlaylistParams:
    def test_keeps_video_and_timestamp(self):
        url = "https://www.youtube.com/watch?v=abc&list=PL1&index=3&t=42"
        assert strip_playlist_params(url) == "https://www.youtube.com/watch?v=abc&t=42"

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/playlist?list=PL1",
            "https://www.youtube.com/watch?v=abc",
            "https://vimeo.com/123",
        ],
    )
    def test_leaves_other_urls_alone(self, url):
        assert strip_playlist_params(url) == url


class TestFindSearchableFiles:
    def test_matches_extensions_recursively(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "a.TXT").write_text("a", encoding="utf-8")
        (tmp_path / "sub" / "b.md").write_text("b", encoding="utf-8")
        (tmp_path / "c.png").write_bytes(b"")

        found = find_searchable_files(tmp_path, ["txt", " md"])

        assert sorted(p.name for p in found) == ["a.TXT", "b.md"]


class TestDownloadImage:
    def test_uses_timeout_and_writes_file(self, tmp_path):
        response = MagicMock()
        response.__enter__.return_value = response
        response.iter_content.return_value = [b"abc", b"def"]
        with patch("requests.get", return_value=response) as get:
            saved = download_image("https://img/x.png", tmp_path / "x.png")

        assert get.call_args.kwargs["timeout"] == IMAGE_DOWNLOAD_TIMEOUT_SECONDS
        assert saved.read_bytes() == b"abcdef"

    def test_failure_leaves_no_partial_file(self, tmp_path):
        response = MagicMock()
        response.__enter__.return_value = response
        response.raise_for_status.side_effect = requests.HTTPError("404")
        with patch("requests.get", return_value=response):
            with pytest.raises(requests.HTTPError):
                download_image("https://img/x.png", tmp_path / "x.png")

        assert list(tmp_path.iterdir()) == []


class TestBundlePdfs:
    def test_merge_only_bundle(self, dummy_pdf, dummy_pdf_multi, tmp_path):
        output = tmp_path / "out" / "bundle.pdf"

        stats = PDFEngine().bundle_pdfs(
            [dummy_pdf, dummy_pdf_multi], output, compress=False
        )

        assert stats["page_count"] == 4
        assert stats["output_size"] == output.stat().st_size
        assert [p.name for p in output.parent.iterdir()] == ["bundle.pdf"]

    def test_failed_bundle_removes_temp_file(self, dummy_pdf, tmp_path):
        engine = PDFEngine()
        output = tmp_path / "bundle.pdf"
        with patch.object(engine, "compress_pdf", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                engine.bundle_pdfs([dummy_pdf], output, compress=True)

        assert [p.name for p in tmp_path.iterdir()] == ["test.pdf"]
