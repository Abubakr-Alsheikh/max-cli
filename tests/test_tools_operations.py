"""`core/operations/tools.py`: share, paste and copy without the CLI."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from max_cli.common.exceptions import (
    ProcessingError,
    ResourceNotFoundError,
    ValidationError,
)
from max_cli.core.operations import tools


def test_share_returns_the_code_as_text():
    result = tools.share("https://example.com")

    assert result.ok
    assert result.details["data"] == "https://example.com"
    assert len(result.details["qr"].splitlines()) > 5


def test_share_refuses_empty_text():
    with pytest.raises(ValidationError):
        tools.share("   ")


def test_paste_adds_png_and_reports_the_file(tmp_path):
    engine = MagicMock()

    result = tools.paste(tmp_path / "shot", engine=engine)

    engine.save_clipboard_image.assert_called_once_with(tmp_path / "shot.png")
    assert result.ok
    assert result.output_files == [tmp_path / "shot.png"]


def test_paste_keeps_an_existing_file_unless_asked(tmp_path):
    existing = tmp_path / "shot.png"
    existing.write_bytes(b"keep")
    engine = MagicMock()

    with pytest.raises(ValidationError, match="already exists"):
        tools.paste(existing, engine=engine)
    engine.save_clipboard_image.assert_not_called()

    tools.paste(existing, overwrite=True, engine=engine)
    engine.save_clipboard_image.assert_called_once_with(existing)


def test_paste_with_no_image_on_the_clipboard_is_not_ok(tmp_path):
    engine = MagicMock()
    engine.save_clipboard_image.side_effect = ValueError("Clipboard is empty.")

    result = tools.paste(tmp_path / "a.png", engine=engine)

    assert not result.ok
    assert result.message == "Clipboard is empty."
    assert result.output_files == []


@pytest.mark.parametrize(
    "raised, expected",
    [
        (FileNotFoundError("gone"), ResourceNotFoundError),
        (ValueError("binary"), ValidationError),
        (RuntimeError("no clipboard"), ProcessingError),
    ],
)
def test_copy_turns_engine_errors_into_max_errors(raised, expected):
    engine = MagicMock()
    engine.copy_file_to_clipboard.side_effect = raised

    with pytest.raises(expected):
        tools.copy(Path("notes.txt"), engine=engine)


def test_copy_names_the_file():
    result = tools.copy(Path("notes.txt"), engine=MagicMock())

    assert result.message == "Copied notes.txt to the clipboard."
