import random
from pathlib import Path

import pytest
from PIL import Image

from max_cli.core.engines.image_processor import ImageEngine

NOISE_SEED = 1234
EXIF_ARTIST_TAG = 0x013B


@pytest.fixture
def engine() -> ImageEngine:
    return ImageEngine()


@pytest.fixture
def noisy_jpeg(tmp_path) -> Path:
    """Seeded random-pixel image: JPEG quality visibly changes its file size."""
    rng = random.Random(NOISE_SEED)
    width, height = 120, 80
    pixels = bytes(rng.randrange(256) for _ in range(width * height * 3))
    image_path = tmp_path / "noise.jpg"
    Image.frombytes("RGB", (width, height), pixels).save(image_path, quality=95)
    return image_path


@pytest.fixture
def wide_png(tmp_path) -> Path:
    image_path = tmp_path / "wide.png"
    Image.new("RGB", (200, 100), color="green").save(image_path)
    return image_path


# --- compress ----------------------------------------------------------------


def test_compress_image(engine, dummy_image):
    output_path = dummy_image.parent / "output.jpg"

    stats = engine.process_single_image(dummy_image, output_path, quality=50)

    assert output_path.exists()
    assert stats["file_name"] == "test.jpg"
    assert stats["out_path"] == output_path
    with Image.open(output_path) as result:
        assert result.format == "JPEG"
        assert result.size == (100, 100)


def test_compress_lower_quality_gives_smaller_file(engine, noisy_jpeg, tmp_path):
    high = engine.process_single_image(noisy_jpeg, tmp_path / "high.jpg", quality=95)
    low = engine.process_single_image(noisy_jpeg, tmp_path / "low.jpg", quality=20)

    high_size = high["out_path"].stat().st_size
    low_size = low["out_path"].stat().st_size
    assert low_size < high_size
    assert low["reduction_pct"] > high["reduction_pct"]
    assert low["reduction_pct"] > 0


def test_compress_reports_human_sizes(engine, noisy_jpeg, tmp_path):
    stats = engine.process_single_image(noisy_jpeg, tmp_path / "out.jpg", quality=40)

    expected_original = engine.get_size_str(noisy_jpeg.stat().st_size)
    expected_final = engine.get_size_str(stats["out_path"].stat().st_size)
    assert stats["original_size"] == expected_original
    assert stats["final_size"] == expected_final


def test_compress_missing_input_raises(engine, tmp_path):
    with pytest.raises(FileNotFoundError):
        engine.process_single_image(tmp_path / "missing.jpg", tmp_path / "out.jpg")


def test_get_size_str_switches_units(engine):
    assert engine.get_size_str(2048) == "2.00 KB"
    assert engine.get_size_str(3 * 1024 * 1024) == "3.00 MB"


# --- resize ------------------------------------------------------------------


def test_resize_image(engine, dummy_image):
    output_path = dummy_image.parent / "resized.jpg"

    engine.process_single_image(dummy_image, output_path, scale=50)

    with Image.open(output_path) as result:
        assert result.size == (50, 50)


@pytest.mark.parametrize(
    "resize_args, expected_size",
    [
        ({"width": 100}, (100, 50)),
        ({"height": 50}, (100, 50)),
        ({"width": 30, "height": 70}, (30, 70)),
        ({"scale": 25}, (50, 25)),
        ({"max_dim": 80}, (80, 40)),
        ({"max_dim": 500}, (200, 100)),
    ],
    ids=["width", "height", "both", "scale", "max-dim", "max-dim-no-upscale"],
)
def test_resize_modes(engine, wide_png, tmp_path, resize_args, expected_size):
    output_path = tmp_path / "out.png"

    engine.process_single_image(wide_png, output_path, **resize_args)

    with Image.open(output_path) as result:
        assert result.size == expected_size


# --- convert -----------------------------------------------------------------


def test_convert_by_output_suffix(engine, dummy_image, tmp_path):
    stats = engine.process_single_image(dummy_image, tmp_path / "converted.png")

    assert stats["out_path"] == tmp_path / "converted.png"
    with Image.open(stats["out_path"]) as result:
        assert result.format == "PNG"


@pytest.mark.parametrize(
    "force_format, expected_suffix, expected_format",
    [
        ("webp", ".webp", "WEBP"),
        ("JPEG", ".jpg", "JPEG"),
        ("png", ".png", "PNG"),
    ],
)
def test_convert_force_format_overrides_suffix(
    engine, dummy_image_png, tmp_path, force_format, expected_suffix, expected_format
):
    stats = engine.process_single_image(
        dummy_image_png, tmp_path / "out.bmp", force_format=force_format
    )

    assert stats["out_path"] == tmp_path / f"out{expected_suffix}"
    with Image.open(stats["out_path"]) as result:
        assert result.format == expected_format
        assert result.size == (100, 100)


def test_convert_unknown_target_keeps_source_format(engine, dummy_image_png, tmp_path):
    stats = engine.process_single_image(dummy_image_png, tmp_path / "out.xyz")

    assert stats["out_path"] == tmp_path / "out.png"
    with Image.open(stats["out_path"]) as result:
        assert result.format == "PNG"


def test_convert_rgba_png_to_jpeg_drops_alpha(engine, tmp_path):
    rgba_path = tmp_path / "alpha.png"
    Image.new("RGBA", (40, 40), color=(255, 0, 0, 128)).save(rgba_path)

    stats = engine.process_single_image(rgba_path, tmp_path / "flat.jpg")

    with Image.open(stats["out_path"]) as result:
        assert result.format == "JPEG"
        assert result.mode == "RGB"


def test_quantize_png_produces_palette_image(engine, noisy_jpeg, tmp_path):
    plain = engine.process_single_image(noisy_jpeg, tmp_path / "plain.png")
    quantized = engine.process_single_image(
        noisy_jpeg, tmp_path / "quantized.png", quantize_png=True
    )

    with Image.open(quantized["out_path"]) as result:
        assert result.mode == "P"
    assert quantized["out_path"].stat().st_size < plain["out_path"].stat().st_size


def test_strip_exif_drops_metadata(engine, tmp_path):
    source_path = tmp_path / "tagged.jpg"
    exif = Image.Exif()
    exif[EXIF_ARTIST_TAG] = "Someone"
    Image.new("RGB", (30, 30), color="red").save(source_path, exif=exif.tobytes())
    with Image.open(source_path) as tagged:
        assert tagged.getexif().get(EXIF_ARTIST_TAG) == "Someone"

    stats = engine.process_single_image(
        source_path, tmp_path / "clean.jpg", strip_exif=True
    )

    with Image.open(stats["out_path"]) as result:
        assert EXIF_ARTIST_TAG not in result.getexif()
        assert result.size == (30, 30)


def test_strip_metadata_rewrites_pixels_only(engine, tmp_path):
    source_path = tmp_path / "tagged.png"
    Image.new("RGB", (10, 10), color="blue").save(source_path)
    output_path = tmp_path / "clean.png"

    engine.strip_metadata(source_path, output_path)

    with Image.open(output_path) as result:
        assert result.size == (10, 10)
        assert result.getpixel((0, 0)) == (0, 0, 255)
