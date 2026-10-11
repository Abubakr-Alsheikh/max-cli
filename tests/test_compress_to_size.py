"""Compressing to a size (`--size 25MB`): video, images and PDFs.

FFmpeg never runs: the video tests use a fake engine that writes files of a
chosen size. The image and PDF tests run Pillow and PyMuPDF for real.
"""

import io
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import pytest
from PIL import Image

from max_cli.common.exceptions import ValidationError
from max_cli.common.utils import format_decimal_size, parse_size
from max_cli.core.engines.image_processor import fit_in_bytes
from max_cli.core.engines.media_engine import MediaEngine
from max_cli.core.operations import images, pdf, video

FULL_HD = 1080
ONE_MINUTE = 60.0


class TestParseSize:
    @pytest.mark.parametrize(
        "text, size_bytes",
        [
            ("25MB", 25_000_000),
            ("25 mb", 25_000_000),
            ("800KB", 800_000),
            ("1.5G", 1_500_000_000),
            ("500000", 500_000),
            ("2m", 2_000_000),
        ],
    )
    def test_reads_decimal_units(self, text, size_bytes):
        assert parse_size(text) == size_bytes

    @pytest.mark.parametrize("text", ["", "big", "25XB", "-5MB", "0MB"])
    def test_refuses_what_isnt_a_size(self, text):
        with pytest.raises(ValueError):
            parse_size(text)

    def test_formats_in_the_same_units(self):
        assert format_decimal_size(25_000_000) == "25 MB"
        assert format_decimal_size(210_000) == "210 KB"
        assert format_decimal_size(12) == "12 B"


class TestPlanBitrates:
    def test_fills_the_budget_with_headroom(self):
        plan = video.plan_bitrates(25_000_000, ONE_MINUTE, True, FULL_HD)

        total_kbps = 25_000_000 * 8 * video.SIZE_HEADROOM / ONE_MINUTE / 1000
        assert plan.audio_kbps == 128
        assert plan.video_kbps == int(total_kbps - 128)
        assert plan.height is None  # over 1,500 kbps keeps full HD

    def test_tight_budget_spends_less_on_sound_and_pixels(self):
        plan = video.plan_bitrates(2_000_000, 20.0, True, FULL_HD)

        assert plan.audio_kbps == 96
        assert plan.height == 720

    def test_lowest_budget_scales_to_480(self):
        plan = video.plan_bitrates(1_500_000, ONE_MINUTE, True, FULL_HD)

        assert plan.height == 480

    def test_a_small_picture_is_not_scaled_up(self):
        plan = video.plan_bitrates(1_500_000, ONE_MINUTE, True, 360)

        assert plan.height is None

    def test_silent_video_gets_every_bit(self):
        plan = video.plan_bitrates(25_000_000, ONE_MINUTE, False, FULL_HD)

        assert plan.audio_kbps == 0

    def test_too_small_says_the_least_that_works(self):
        with pytest.raises(ValidationError, match="too small.*Give at least"):
            video.plan_bitrates(50_000, 20.0, True, FULL_HD)


def _fake_media(output_sizes: list[int], duration: float = ONE_MINUTE) -> MagicMock:
    """An engine whose encodes write files of the given sizes, in turn."""
    media = MagicMock()
    media.probe_media.return_value = {
        "format": {"duration": str(duration)},
        "streams": [
            {"codec_type": "video", "height": FULL_HD},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }
    sizes = iter(output_sizes)

    def encode(source, output, *args):
        Path(output).write_bytes(b"x" * next(sizes))

    media.compress_to_bitrate.side_effect = encode
    return media


class TestVideoToSize:
    def test_fits_in_one_encode(self, tmp_path):
        source = tmp_path / "talk.mp4"
        source.write_bytes(b"v" * 3_000_000)
        media = _fake_media([900_000])

        result = video.compress(source, size="1MB", engine=media)

        assert result.ok
        assert result.output_files == [tmp_path / "talk_compressed.mp4"]
        assert result.details["fits"] is True
        media.compress_to_bitrate.assert_called_once()
        media.compress_video.assert_not_called()

    def test_over_the_limit_encodes_again_lower(self, tmp_path):
        source = tmp_path / "talk.mp4"
        source.write_bytes(b"v" * 3_000_000)
        media = _fake_media([1_200_000, 950_000])

        result = video.compress(source, size="1MB", engine=media)

        first, second = media.compress_to_bitrate.call_args_list
        assert second.args[2] < first.args[2]
        assert result.details["fits"] is True

    def test_still_over_says_so(self, tmp_path):
        source = tmp_path / "talk.mp4"
        source.write_bytes(b"v" * 3_000_000)

        result = video.compress(
            source, size="1MB", engine=_fake_media([1_300_000, 1_100_000])
        )

        assert result.ok
        assert result.details["fits"] is False
        assert "over 1 MB" in result.message

    def test_already_small_does_nothing(self, tmp_path):
        source = tmp_path / "clip.mp4"
        source.write_bytes(b"v" * 1000)
        media = _fake_media([])

        result = video.compress(source, size="1MB", engine=media)

        assert result.ok
        assert result.output_files == []
        assert "already under 1 MB" in result.message
        media.compress_to_bitrate.assert_not_called()

    def test_bad_size_is_a_validation_error(self, tmp_path):
        source = tmp_path / "clip.mp4"
        source.write_bytes(b"v")

        with pytest.raises(ValidationError, match="isn't a size"):
            video.compress(source, size="huge", engine=_fake_media([]))


@patch("subprocess.run")
@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_engine_runs_two_passes_at_the_bitrate(mock_which, mock_run, tmp_path):
    mock_run.return_value = subprocess.CompletedProcess([], 0)

    MediaEngine().compress_to_bitrate(
        tmp_path / "in.mp4", tmp_path / "out.mp4", 700, 96, height=720
    )

    first, second = (call.args[0] for call in mock_run.call_args_list)
    assert first[first.index("-pass") + 1] == "1"
    assert "-an" in first and first[-1] == "-"
    assert second[second.index("-pass") + 1] == "2"
    for command in (first, second):
        assert command[command.index("-b:v") + 1] == "700k"
        assert command[command.index("-vf") + 1] == "scale=-2:720"
    assert second[second.index("-b:a") + 1] == "96k"
    assert second[-1] == str(tmp_path / "out.mp4")


def _noise(size: tuple[int, int], mode: str = "RGB") -> Image.Image:
    return Image.frombytes(mode, size, os.urandom(size[0] * size[1] * len(mode)))


class TestImagesToSize:
    def test_search_fits(self):
        data, fits = fit_in_bytes(_noise((400, 300)), "JPEG", 60_000, 95)

        assert fits
        assert len(data) <= 60_000

    def test_shrinks_the_picture_when_quality_alone_cant(self):
        data, fits = fit_in_bytes(_noise((1600, 1200)), "JPEG", 30_000, 85)

        assert fits
        assert Image.open(io.BytesIO(data)).width < 1600

    def test_png_becomes_jpeg_and_fits(self, tmp_path):
        source = tmp_path / "scan.png"
        _noise((800, 600)).save(source)

        result = images.compress(source, size="100KB", workers=1)

        assert result.ok, result.message
        (output,) = result.output_files
        assert output.name == "scan_opt.jpg"
        assert output.stat().st_size <= 100_000
        assert result.details["over_size"] == []

    def test_transparent_png_becomes_webp(self, tmp_path):
        source = tmp_path / "logo.png"
        _noise((300, 300), "RGBA").save(source)

        result = images.compress(source, size="50KB", workers=1)

        (output,) = result.output_files
        assert output.suffix == ".webp"
        with Image.open(output) as saved:
            assert saved.mode == "RGBA"

    def test_same_names_in_a_folder_dont_overwrite(self, tmp_path):
        folder = tmp_path / "photos"
        folder.mkdir()
        _noise((200, 200)).save(folder / "cat.png")
        _noise((200, 200)).save(folder / "cat.jpg")

        result = images.compress(folder, size="40KB", workers=1)

        names = sorted(path.name for path in result.output_files)
        assert names == ["cat_jpg.jpg", "cat_png.jpg"]

    def test_bad_size(self, tmp_path):
        source = tmp_path / "a.jpg"
        _noise((10, 10)).save(source)

        with pytest.raises(ValidationError):
            images.compress(source, size="a lot", workers=1)


def _scanned_pdf(path: Path, pages: int = 2) -> Path:
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        buffer = io.BytesIO()
        _noise((900, 1200)).save(buffer, "JPEG", quality=90)
        page.insert_image(page.rect, stream=buffer.getvalue())
    doc.save(path)
    doc.close()
    return path


class TestPdfToSize:
    def test_lossless_rewrite_is_enough_for_a_roomy_limit(self, tmp_path):
        source = _scanned_pdf(tmp_path / "scan.pdf")

        result = pdf.compress(source, size="50MB")

        (row,) = result.details["files"]
        assert row["how"] == "optimized"
        assert row["fits"] is True
        with fitz.open(result.output_files[0]) as doc:
            assert doc.page_count == 2

    def test_lowers_the_resolution_until_it_fits(self, tmp_path):
        source = _scanned_pdf(tmp_path / "scan.pdf")
        limit = source.stat().st_size // 4

        result = pdf.compress(source, size=str(limit))

        (row,) = result.details["files"]
        assert row["fits"] is True
        assert row["new_size"] <= limit
        assert "dpi" in row["how"]
        assert not list(tmp_path.glob(".*trial*"))

    def test_keeps_the_smallest_when_nothing_fits(self, tmp_path):
        source = _scanned_pdf(tmp_path / "scan.pdf")

        result = pdf.compress(source, size="1KB")

        assert result.ok
        assert result.details["over_size"] == ["scan.pdf"]
        assert "still over 1KB" in result.message
        assert result.output_files[0].stat().st_size < source.stat().st_size
