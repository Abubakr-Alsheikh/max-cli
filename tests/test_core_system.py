from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from max_cli.core.engines.system_engine import SystemEngine


def test_generate_qr_returns_text_without_printing(capsys):
    qr_text = SystemEngine().generate_qr("https://example.com")

    assert qr_text.strip()
    assert len(qr_text.splitlines()) > 5
    assert capsys.readouterr().out == ""


# --- copy_file_to_clipboard --------------------------------------------------


def test_copy_file_to_clipboard_copies_utf8_text(tmp_path):
    text_file = tmp_path / "note.txt"
    text_file.write_text("héllo wörld ✓", encoding="utf-8")

    with patch("pyperclip.copy") as mock_copy:
        SystemEngine().copy_file_to_clipboard(text_file)

    mock_copy.assert_called_once_with("héllo wörld ✓")


def test_copy_file_to_clipboard_missing_file(tmp_path):
    with patch("pyperclip.copy") as mock_copy:
        with pytest.raises(FileNotFoundError):
            SystemEngine().copy_file_to_clipboard(tmp_path / "missing.txt")

    mock_copy.assert_not_called()


def test_copy_file_to_clipboard_rejects_binary(tmp_path):
    binary_file = tmp_path / "blob.bin"
    binary_file.write_bytes(b"\xff\xfe\x00\x80\x81")

    with patch("pyperclip.copy") as mock_copy:
        with pytest.raises(ValueError, match="binary"):
            SystemEngine().copy_file_to_clipboard(binary_file)

    mock_copy.assert_not_called()


def test_copy_file_to_clipboard_wraps_clipboard_errors(tmp_path):
    import pyperclip

    text_file = tmp_path / "note.txt"
    text_file.write_text("hi", encoding="utf-8")

    with patch("pyperclip.copy", side_effect=pyperclip.PyperclipException("no")):
        with pytest.raises(RuntimeError, match="Clipboard error: no"):
            SystemEngine().copy_file_to_clipboard(text_file)


# --- save_clipboard_image ----------------------------------------------------


def test_save_clipboard_image_empty_clipboard(tmp_path):
    output_path = tmp_path / "clip.png"

    with patch("PIL.ImageGrab.grabclipboard", return_value=None):
        with pytest.raises(ValueError, match="empty"):
            SystemEngine().save_clipboard_image(output_path)

    assert not output_path.exists()


def test_save_clipboard_image_non_image_content(tmp_path):
    output_path = tmp_path / "clip.png"
    copied_files = [str(tmp_path / "a.txt")]

    with patch("PIL.ImageGrab.grabclipboard", return_value=copied_files):
        with pytest.raises(ValueError, match="does not contain image data"):
            SystemEngine().save_clipboard_image(output_path)

    assert not output_path.exists()


def test_save_clipboard_image_writes_image(tmp_path):
    output_path = tmp_path / "clip.png"
    clipboard_image = Image.new("RGB", (12, 8), color="green")

    with patch("PIL.ImageGrab.grabclipboard", return_value=clipboard_image):
        SystemEngine().save_clipboard_image(output_path)

    with Image.open(output_path) as saved:
        assert saved.format == "PNG"
        assert saved.size == (12, 8)


def test_save_clipboard_image_delegates_to_save(tmp_path):
    output_path = tmp_path / "clip.png"
    clipboard_image = MagicMock()

    with patch("PIL.ImageGrab.grabclipboard", return_value=clipboard_image):
        SystemEngine().save_clipboard_image(output_path)

    clipboard_image.save.assert_called_once_with(output_path)
