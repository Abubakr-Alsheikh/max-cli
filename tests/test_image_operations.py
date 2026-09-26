"""core/operations/images.py: batching, output naming and errors, for every caller."""

from pathlib import Path

import pytest
from PIL import Image

from max_cli.common.events import EventEmitter
from max_cli.common.exceptions import ResourceNotFoundError, ValidationError
from max_cli.core.operations import images


def _image(path: Path, size: tuple[int, int] = (100, 80), fmt: str = "JPEG") -> Path:
    Image.new("RGB", size, color="red").save(path, fmt)
    return path


@pytest.fixture
def photos(tmp_path) -> Path:
    folder = tmp_path / "photos"
    folder.mkdir()
    _image(folder / "a.jpg")
    _image(folder / "b.png", fmt="PNG")
    (folder / "notes.txt").write_text("not an image", encoding="utf-8")
    (folder / "nested").mkdir()
    _image(folder / "nested" / "c.jpg")
    return folder


class TestNaming:
    def test_one_file_saves_next_to_it_with_opt(self, tmp_path):
        photo = _image(tmp_path / "cat.jpg")

        result = images.compress(photo, workers=1)

        assert result.ok, result.message
        assert result.output_files == [tmp_path / "cat_opt.jpg"]
        assert result.details["output_dir"] == str(tmp_path)

    def test_folder_saves_its_own_images_into_an_optimized_folder(self, photos):
        result = images.compress(photos, workers=2)

        out_dir = photos.parent / "photos_optimized"
        assert result.ok, result.message
        assert sorted(result.output_files) == [out_dir / "a.jpg", out_dir / "b.png"]

    def test_folder_with_one_image_keeps_its_name(self, tmp_path):
        folder = tmp_path / "single"
        folder.mkdir()
        _image(folder / "only.jpg")

        result = images.compress(folder, workers=1)

        assert result.output_files == [tmp_path / "single_optimized" / "only.jpg"]

    def test_current_folder_gets_a_real_name(self, photos, monkeypatch):
        """`max images compress` with no path wrote into ./_optimized."""
        monkeypatch.chdir(photos)

        _images, out_dir = images.resolve_batch(Path("."))

        assert out_dir == photos.parent / "photos_optimized"


class TestErrors:
    def test_missing_path(self, tmp_path):
        with pytest.raises(ResourceNotFoundError):
            images.compress(tmp_path / "gone.jpg")

    def test_folder_without_images(self, tmp_path):
        result = images.strip(tmp_path)

        assert not result.ok
        assert "No images found" in result.message
        assert not (tmp_path.parent / f"{tmp_path.name}_optimized").exists()

    def test_resize_needs_a_size(self, tmp_path):
        with pytest.raises(ValidationError, match="--width"):
            images.resize(_image(tmp_path / "a.jpg"))

    @pytest.mark.parametrize("quality", [0, 101])
    def test_quality_range(self, tmp_path, quality):
        with pytest.raises(ValidationError, match="between 1 and 100"):
            images.compress(_image(tmp_path / "a.jpg"), quality=quality)

    @pytest.mark.parametrize("to", [None, "", "gif"])
    def test_convert_needs_a_known_format(self, tmp_path, to):
        with pytest.raises(ValidationError):
            images.convert(_image(tmp_path / "a.jpg"), to=to)

    def test_one_bad_image_does_not_stop_the_rest(self, photos):
        (photos / "broken.jpg").write_bytes(b"not really a jpeg")

        result = images.strip(photos, workers=2)

        assert result.ok
        assert len(result.output_files) == 2
        assert [failure["file"] for failure in result.details["failed"]] == [
            "broken.jpg"
        ]
        assert "1 of 3 images failed" in result.message


class TestWork:
    def test_convert_accepts_jpeg_as_jpg(self, tmp_path):
        result = images.convert(_image(tmp_path / "a.png", fmt="PNG"), to="JPEG")

        assert result.output_files == [tmp_path / "a_opt.jpg"]
        with Image.open(result.output_files[0]) as converted:
            assert converted.format == "JPEG"

    def test_resize_by_width_keeps_the_aspect_ratio(self, tmp_path):
        result = images.resize(_image(tmp_path / "a.jpg", size=(200, 100)), width=50)

        with Image.open(result.output_files[0]) as resized:
            assert resized.size == (50, 25)

    def test_progress_events_carry_the_total(self, photos):
        emitter = EventEmitter()
        seen = []
        emitter.subscribe(seen.append)

        images.strip(photos, workers=1, emitter=emitter)

        totals = [event.total for event in seen if event.type == "batch_progress"]
        assert totals and set(totals) == {2}


def test_dashboard_form_values_run_the_operation(tmp_path):
    """The Tools page sends strings; empty fields fall back to the defaults."""
    from max_cli.core.catalog import get_action
    from max_cli.core.catalog.runner import coerce_args, run_action

    photo = _image(tmp_path / "a.jpg")
    action = get_action("images.compress")
    args = coerce_args(action, {"target": str(photo), "quality": "70", "scale": ""})

    assert args["quality"] == 70 and args["scale"] is None
    result = run_action(action, args)
    assert result.ok and result.output_files == [tmp_path / "a_opt.jpg"]
