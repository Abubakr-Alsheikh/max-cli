import pytest
from pathlib import Path
from PIL import Image
from max_cli.core.image_processor import ImageEngine


@pytest.fixture
def dummy_image(tmp_path):
    """Creates a temporary 100x100 red image for testing."""
    img_path = tmp_path / "test.jpg"
    img = Image.new("RGB", (100, 100), color="red")
    img.save(img_path)
    return img_path


def test_compress_image(dummy_image):
    """Test that compression reduces file size (or at least runs)."""
    engine = ImageEngine()
    output_path = dummy_image.parent / "output.jpg"

    # Run compression
    stats = engine.process_single_image(dummy_image, output_path, quality=50)

    assert output_path.exists()
    assert stats["file_name"] == "test.jpg"
    # Basic check: verify it's still a valid image
    with Image.open(output_path) as result:
        assert result.size == (100, 100)


def test_resize_image(dummy_image):
    """Test that scaling works."""
    engine = ImageEngine()
    output_path = dummy_image.parent / "resized.jpg"

    engine.process_single_image(
        dummy_image, output_path, scale=50  # Should become 50x50
    )

    with Image.open(output_path) as result:
        assert result.size == (50, 50)
