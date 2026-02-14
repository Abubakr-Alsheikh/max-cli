import pytest
from unittest.mock import patch, MagicMock
from max_cli.core.media_engine import MediaEngine


class TestMediaEngine:
    """Tests for media manipulation operations."""

    @patch("shutil.which")
    def test_init_without_ffmpeg(self, mock_which):
        """Test initialization fails without FFmpeg."""
        mock_which.return_value = None

        with pytest.raises(RuntimeError, match="FFmpeg is not installed"):
            MediaEngine()

    @patch("shutil.which")
    def test_init_with_ffmpeg(self, mock_which):
        """Test initialization succeeds with FFmpeg."""
        mock_which.return_value = "/usr/bin/ffmpeg"

        engine = MediaEngine()
        assert engine.ffmpeg_path == "/usr/bin/ffmpeg"

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_compress_video(self, mock_which, mock_run, tmp_path):
        """Test video compression."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock()

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mp4"
        input_path.write_text("video content")

        engine = MediaEngine()
        engine.compress_video(input_path, output_path, crf=28, preset="medium")

        mock_run.assert_called_once()

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_convert_format(self, mock_which, mock_run, tmp_path):
        """Test format conversion."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock()

        input_path = tmp_path / "input.mkv"
        output_path = tmp_path / "output.mp4"
        input_path.write_text("video content")

        engine = MediaEngine()
        engine.convert_format(input_path, output_path)

        assert mock_run.call_count >= 1

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_extract_audio(self, mock_which, mock_run, tmp_path):
        """Test audio extraction."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock()

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mp3"
        input_path.write_text("video content")

        engine = MediaEngine()
        engine.extract_audio(input_path, output_path)

        mock_run.assert_called_once()

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_video_to_gif(self, mock_which, mock_run, tmp_path):
        """Test video to GIF conversion."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock()

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.gif"
        input_path.write_text("video content")

        engine = MediaEngine()
        engine.video_to_gif(input_path, output_path, fps=15, scale=480)

        mock_run.assert_called_once()

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_trim_video(self, mock_which, mock_run, tmp_path):
        """Test video trimming."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock()

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mp4"
        input_path.write_text("video content")

        engine = MediaEngine()
        engine.trim_video(input_path, output_path, start="00:00:10", duration="30")

        mock_run.assert_called_once()

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_get_thumbnail(self, mock_which, mock_run, tmp_path):
        """Test thumbnail extraction."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock()

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "thumb.jpg"
        input_path.write_text("video content")

        engine = MediaEngine()
        engine.get_thumbnail(input_path, output_path, time="00:00:01")

        mock_run.assert_called_once()

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_adjust_volume(self, mock_which, mock_run, tmp_path):
        """Test volume adjustment."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock()

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mp4"
        input_path.write_text("video content")

        engine = MediaEngine()
        engine.adjust_volume(input_path, output_path, db=10)

        mock_run.assert_called_once()

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_mute_video(self, mock_which, mock_run, tmp_path):
        """Test video muting."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock()

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mp4"
        input_path.write_text("video content")

        engine = MediaEngine()
        engine.mute_video(input_path, output_path)

        mock_run.assert_called_once()

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_ffmpeg_error_handling(self, mock_which, mock_run, tmp_path):
        """Test error handling when FFmpeg fails."""
        import subprocess

        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "ffmpeg", stderr=b"Error message"
        )

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mp4"
        input_path.write_text("video content")

        engine = MediaEngine()

        with pytest.raises(RuntimeError, match="FFmpeg Error"):
            engine.compress_video(input_path, output_path)
