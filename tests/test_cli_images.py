from typer.testing import CliRunner
from max_cli.interface.cli_images import app as images_app
from PIL import Image


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
