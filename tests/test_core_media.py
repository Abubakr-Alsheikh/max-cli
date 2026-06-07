import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from max_cli.core.engines.media_engine import MediaEngine


class TestMediaEngine:
    """Tests for media manipulation operations."""

    @patch("max_cli.common.ffmpeg_resolver.FFmpegResolver")
    @patch("shutil.which")
    def test_init_without_ffmpeg(self, mock_which, mock_resolver_class):
        """Test initialization fails without FFmpeg."""
        mock_which.return_value = None
        mock_resolver = MagicMock()
        mock_resolver.local_path.exists.return_value = False
        mock_resolver_class.return_value = mock_resolver

        with pytest.raises(RuntimeError, match="FFmpeg is not installed"):
            MediaEngine(auto_resolve=False)

    @patch("shutil.which")
    def test_init_with_ffmpeg(self, mock_which):
        """Test initialization succeeds with FFmpeg."""
        mock_which.return_value = "/usr/bin/ffmpeg"

        engine = MediaEngine()
        assert engine.ffmpeg_path == Path("/usr/bin/ffmpeg")

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


class TestMediaEngineResolvedPath:
    def test_uses_resolved_path(self):
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            engine = MediaEngine()
            assert engine.ffmpeg_path == Path("/usr/bin/ffmpeg")

    def test_compress_video_uses_resolved_path(self, tmp_path):
        with (
            patch("shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock()
            input_path = tmp_path / "input.mp4"
            output_path = tmp_path / "output.mp4"
            input_path.write_text("video content")

            engine = MediaEngine()
            engine.compress_video(input_path, output_path, crf=28, preset="medium")

            call_args = mock_run.call_args[0][0]
            assert call_args[0] == str(Path("/usr/bin/ffmpeg"))
            assert call_args[0] != "ffmpeg"

    def test_auto_resolve_on_init(self):
        mock_path = Path("/custom/ffmpeg")
        with (
            patch("shutil.which", return_value=None),
            patch(
                "max_cli.common.ffmpeg_resolver.resolve_ffmpeg", return_value=mock_path
            ),
        ):
            engine = MediaEngine()
            assert engine.ffmpeg_path == mock_path


class TestMediaEngineDenoise:
    """Tests for audio denoising operations."""

    def _make_mock_process(self, returncode=0, stderr_lines=None):
        process = MagicMock()
        process.stdout = iter([])
        process.stderr = iter(stderr_lines or [])
        process.returncode = returncode
        process.wait.return_value = returncode
        return process

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_denoise_auto_default(
        self, mock_which, mock_run, mock_popen, tmp_path
    ):
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock()
        mock_popen.return_value = self._make_mock_process()

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mp4"
        input_path.write_text("video content")

        engine = MediaEngine()
        engine.denoise_audio(input_path, output_path)

        call_args = mock_popen.call_args[0][0]
        assert call_args[0] == str(Path("/usr/bin/ffmpeg"))
        af_idx = call_args.index("-af")
        assert "anlmdn" in call_args[af_idx + 1]
        assert "0.0005:0.016:0.016" in call_args[af_idx + 1]
        cv_idx = call_args.index("-c:v")
        assert call_args[cv_idx + 1] == "copy"

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_denoise_auto_strength_mild(
        self, mock_which, mock_run, mock_popen, tmp_path
    ):
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock()
        mock_popen.return_value = self._make_mock_process()

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mp4"
        input_path.write_text("video content")

        engine = MediaEngine()
        engine.denoise_audio(input_path, output_path, strength="mild")

        call_args = mock_popen.call_args[0][0]
        af_idx = call_args.index("-af")
        assert "0.0001:0.016:0.016" in call_args[af_idx + 1]

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_denoise_auto_strength_aggressive(
        self, mock_which, mock_run, mock_popen, tmp_path
    ):
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock()
        mock_popen.return_value = self._make_mock_process()

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mp4"
        input_path.write_text("video content")

        engine = MediaEngine()
        engine.denoise_audio(input_path, output_path, strength="aggressive")

        call_args = mock_popen.call_args[0][0]
        af_idx = call_args.index("-af")
        assert "0.003:0.016:0.016" in call_args[af_idx + 1]

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_denoise_hiss_mode(
        self, mock_which, mock_run, mock_popen, tmp_path
    ):
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock()
        mock_popen.return_value = self._make_mock_process()

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mp4"
        input_path.write_text("video content")

        engine = MediaEngine()
        engine.denoise_audio(input_path, output_path, mode="hiss")

        call_args = mock_popen.call_args[0][0]
        af_idx = call_args.index("-af")
        assert "afftdn" in call_args[af_idx + 1]

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_denoise_hum_mode(
        self, mock_which, mock_run, mock_popen, tmp_path
    ):
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock()
        mock_popen.return_value = self._make_mock_process()

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mp4"
        input_path.write_text("video content")

        engine = MediaEngine()
        engine.denoise_audio(input_path, output_path, mode="hum")

        call_args = mock_popen.call_args[0][0]
        af_idx = call_args.index("-af")
        assert "highpass" in call_args[af_idx + 1]
        cv_idx = call_args.index("-c:v")
        assert call_args[cv_idx + 1] == "copy"

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_denoise_hum_custom_cutoff(
        self, mock_which, mock_run, mock_popen, tmp_path
    ):
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock()
        mock_popen.return_value = self._make_mock_process()

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mp4"
        input_path.write_text("video content")

        engine = MediaEngine()
        engine.denoise_audio(
            input_path, output_path, mode="hum", hum_cutoff=120
        )

        call_args = mock_popen.call_args[0][0]
        af_idx = call_args.index("-af")
        assert "highpass=f=120" in call_args[af_idx + 1]

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_denoise_ffmpeg_error(
        self, mock_which, mock_run, mock_popen, tmp_path
    ):
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock()
        mock_popen.return_value = self._make_mock_process(
            returncode=1, stderr_lines=["Error message"]
        )

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mp4"
        input_path.write_text("video content")

        engine = MediaEngine()

        with pytest.raises(RuntimeError, match="FFmpeg Error"):
            engine.denoise_audio(input_path, output_path)

    def test_denoise_invalid_mode(self, tmp_path):
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            engine = MediaEngine()
            input_path = tmp_path / "input.mp4"
            output_path = tmp_path / "output.mp4"
            input_path.write_text("video content")

            with pytest.raises(ValueError):
                engine.denoise_audio(input_path, output_path, mode="invalid")

    def test_denoise_invalid_strength(self, tmp_path):
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            engine = MediaEngine()
            input_path = tmp_path / "input.mp4"
            output_path = tmp_path / "output.mp4"
            input_path.write_text("video content")

            with pytest.raises(ValueError):
                engine.denoise_audio(input_path, output_path, strength="invalid")

    def test_denoise_input_not_found(self, tmp_path):
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            engine = MediaEngine()
            input_path = tmp_path / "nonexistent.mp4"
            output_path = tmp_path / "output.mp4"

            with pytest.raises(FileNotFoundError):
                engine.denoise_audio(input_path, output_path)

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_denoise_uses_resolved_path(
        self, mock_which, mock_run, mock_popen, tmp_path
    ):
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock()
        mock_popen.return_value = self._make_mock_process()

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mp4"
        input_path.write_text("video content")

        engine = MediaEngine()
        engine.denoise_audio(input_path, output_path)

        call_args = mock_popen.call_args[0][0]
        assert call_args[0] == str(Path("/usr/bin/ffmpeg"))
        assert call_args[0] != "ffmpeg"
