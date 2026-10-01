"""images.describe: what an image or a folder of images holds, for the Images page."""

import pytest
from PIL import ExifTags, Image

from max_cli.common.exceptions import ProcessingError, ResourceNotFoundError
from max_cli.core.operations import images

ROTATED_A_QUARTER = 6


def _photo(path, *, size=(400, 300), orientation=None, gps=False):
    exif = Image.Exif()
    exif[ExifTags.Base.Model] = "Pixel 7"
    exif.get_ifd(ExifTags.IFD.Exif)[ExifTags.Base.DateTimeOriginal] = (
        "2024:05:01 10:22:33"
    )
    if orientation:
        exif[ExifTags.Base.Orientation] = orientation
    if gps:
        exif.get_ifd(ExifTags.IFD.GPSInfo)[ExifTags.GPS.GPSLatitudeRef] = "N"
    Image.new("RGB", size, color="red").save(path, "JPEG", exif=exif)
    return path


def test_a_photo_with_exif(tmp_path):
    path = _photo(tmp_path / "photo.jpg")

    facts = images.describe(path)

    assert (facts.width, facts.height) == (400, 300)
    assert (facts.format, facts.mode) == ("JPEG", "RGB")
    assert (facts.taken, facts.camera) == ("2024-05-01", "Pixel 7")
    assert facts.size_bytes == path.stat().st_size
    assert not facts.is_folder and not facts.has_gps and facts.note == ""


def test_the_size_follows_the_exif_rotation(tmp_path):
    facts = images.describe(
        _photo(tmp_path / "turned.jpg", orientation=ROTATED_A_QUARTER)
    )

    assert (facts.width, facts.height) == (300, 400)


def test_a_gps_location_gets_a_note(tmp_path):
    facts = images.describe(_photo(tmp_path / "trip.jpg", gps=True))

    assert facts.has_gps
    assert facts.note == images.GPS_NOTE


def test_a_plain_png_and_an_animated_gif(tmp_path, dummy_image_png):
    gif = tmp_path / "spin.gif"
    frames = [Image.new("RGB", (20, 20), color) for color in ("red", "lime", "blue")]
    frames[0].save(gif, save_all=True, append_images=frames[1:])

    png = images.describe(dummy_image_png)
    animated = images.describe(gif)

    assert (png.format, png.taken, png.camera, png.frames) == ("PNG", "", "", 1)
    assert (animated.format, animated.frames) == ("GIF", 3)


def test_a_folder_counts_its_images(tmp_path):
    folder = tmp_path / "photos"
    folder.mkdir()
    for name in ("a.jpg", "b.jpg", "c.png"):
        Image.new("RGB", (10, 10)).save(folder / name)
    (folder / "notes.txt").write_text("not an image", encoding="utf-8")
    (folder / "inner").mkdir()
    Image.new("RGB", (10, 10)).save(folder / "inner" / "d.jpg")

    facts = images.describe(folder)

    assert facts.is_folder and facts.image_count == 3
    assert facts.formats == {"JPG": 2, "PNG": 1}
    assert facts.size_bytes == sum(
        (folder / name).stat().st_size for name in ("a.jpg", "b.jpg", "c.png")
    )
    assert facts.output_dir == tmp_path.resolve() / "photos_optimized"
    assert facts.note == ""


def test_an_empty_folder_says_where_max_looks(tmp_path):
    facts = images.describe(tmp_path)

    assert facts.image_count == 0
    assert facts.note == images.EMPTY_FOLDER_NOTE


def test_a_file_that_isnt_an_image_is_an_error(tmp_path):
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not an image at all")

    with pytest.raises(ProcessingError, match="Couldn't read this image"):
        images.describe(broken)


def test_a_missing_file_is_an_error(tmp_path):
    with pytest.raises(ResourceNotFoundError):
        images.describe(tmp_path / "gone.jpg")
