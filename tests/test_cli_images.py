from pathlib import Path

from PIL import Image
from typer.testing import CliRunner

from max_cli.interface.cli_images import app as images_app

runner = CliRunner()


class TestCLIIimages:
    """Tests for CLI image commands."""

    def test_compress_images_help(self):
        """Test compress command help."""
        result = runner.invoke(images_app, ["compress", "--help"])
        assert result.exit_code == 0
        assert "Quality (1-100)" in result.stdout

    def test_resize_images_help(self):
        """Test resize command help."""
        result = runner.invoke(images_app, ["resize", "--help"])
        assert result.exit_code == 0
        assert "Width in px" in result.stdout

    def test_convert_images_help(self):
        """Test convert command help."""
        result = runner.invoke(images_app, ["convert", "--help"])
        assert result.exit_code == 0
        assert "Target format" in result.stdout

    def test_strip_help(self):
        """Test strip command help."""
        result = runner.invoke(images_app, ["strip", "--help"])
        assert result.exit_code == 0
        assert "Remove GPS" in result.stdout

    def test_compress_images_missing_target(self):
        """Test compress with missing target."""
        result = runner.invoke(
            images_app, ["compress", "/nonexistent/path/to/file.jpg"]
        )
        assert result.exit_code != 0 or "Error" in result.stdout


class TestCLIImagesParsing:
    """Tests for CLI argument parsing."""

    def test_compress_with_scale(self, tmp_path):
        """Test compress with scale option."""
        img_path = tmp_path / "test.jpg"
        img = Image.new("RGB", (100, 100), color="red")
        img.save(img_path)

        result = runner.invoke(images_app, ["compress", str(img_path), "-s", "50"])
        assert result.exit_code == 0 or "Error" in result.stdout

    def test_compress_with_max_dim(self, tmp_path):
        """Test compress with max dimension option."""
        img_path = tmp_path / "test.jpg"
        img = Image.new("RGB", (100, 100), color="red")
        img.save(img_path)

        result = runner.invoke(images_app, ["compress", str(img_path), "-m", "50"])
        assert result.exit_code == 0 or "Error" in result.stdout

    def test_resize_requires_dimension(self):
        """Test resize requires at least one dimension option."""
        result = runner.invoke(images_app, ["resize", "."])
        assert "Specify" in result.stdout or result.exit_code != 0


class TestCLIImagesUsesTheOperation:
    """The CLI prints what core/operations/images.py returns."""

    def test_compress_prints_a_summary_and_the_output_path(self, dummy_image):
        result = runner.invoke(images_app, ["compress", str(dummy_image), "-j", "1"])

        assert result.exit_code == 0, result.output
        assert "Optimizing Summary" in result.output
        assert (dummy_image.parent / "test_opt.jpg").exists()

    def test_missing_target_exits_1(self, tmp_path):
        result = runner.invoke(images_app, ["compress", str(tmp_path / "gone.jpg")])

        assert result.exit_code == 1
        assert "Not found" in result.output

    def test_resize_without_a_size_exits_1(self, dummy_image):
        result = runner.invoke(images_app, ["resize", str(dummy_image)])

        assert result.exit_code == 1
        assert "Specify" in result.output

    def test_unknown_convert_format_exits_1(self, dummy_image):
        result = runner.invoke(images_app, ["convert", str(dummy_image), "--to", "gif"])

        assert result.exit_code == 1
        assert "Unknown format" in result.output
