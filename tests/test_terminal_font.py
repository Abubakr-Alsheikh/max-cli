"""common/terminal_font.py and `max config setup-font`.

Every test works on files in tmp_path: never the real font folder, the
registry or Windows Terminal's settings.
"""

import io
import json
import tarfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from max_cli.common import terminal_font as fonts
from max_cli.common.exceptions import ProcessingError

runner = CliRunner()


def _terminal_settings(tmp_path: Path, defaults: dict) -> Path:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"theme": "dark", "profiles": {"defaults": defaults, "list": []}}),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    ("face", "nerd"),
    [
        ("CaskaydiaMono Nerd Font", True),
        ("Cascadia Code NF", True),
        ("JetBrainsMono NFM", True),
        ("Cascadia Mono", False),
        ("", False),
        ("Infinity", False),  # "nf" inside a word isn't a marker
    ],
)
def test_a_nerd_font_is_known_by_its_name(face, nerd):
    assert fonts.is_nerd_face(face) is nerd


def test_the_terminal_font_is_read_from_the_defaults(tmp_path):
    new_style = _terminal_settings(tmp_path, {"font": {"face": "Cascadia Code NF"}})
    assert fonts.terminal_font_face(new_style) == "Cascadia Code NF"

    old_style = _terminal_settings(tmp_path, {"fontFace": "Consolas"})
    assert fonts.terminal_font_face(old_style) == "Consolas"

    nothing = _terminal_settings(tmp_path, {})
    assert fonts.terminal_font_face(nothing) == ""


def test_setting_the_terminal_font_keeps_everything_else_and_a_backup(tmp_path):
    path = _terminal_settings(tmp_path, {"fontFace": "Consolas", "opacity": 90})
    before = path.read_text(encoding="utf-8")

    backup = fonts.set_terminal_font(path=path)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"
    assert data["profiles"]["defaults"] == {
        "opacity": 90,
        "font": {"face": fonts.NERD_FONT_FACE},
    }
    assert backup.read_text(encoding="utf-8") == before


def test_a_settings_file_with_comments_is_left_alone(tmp_path):
    path = tmp_path / "settings.json"
    text = '{\n  // my comment\n  "profiles": {}\n}\n'
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ProcessingError, match="Font face"):
        fonts.set_terminal_font(path=path)

    assert path.read_text(encoding="utf-8") == text
    assert fonts.terminal_font_face(path) == ""


def test_icons_turn_on_only_inside_windows_terminal_with_a_nerd_font(monkeypatch):
    monkeypatch.setattr(
        fonts, "terminal_font_face", lambda path=None: "Cascadia Code NF"
    )
    fonts.terminal_has_nerd_font.cache_clear()
    monkeypatch.delenv("WT_SESSION", raising=False)
    assert not fonts.terminal_has_nerd_font()

    fonts.terminal_has_nerd_font.cache_clear()
    monkeypatch.setenv("WT_SESSION", "1")
    assert fonts.terminal_has_nerd_font()
    fonts.terminal_has_nerd_font.cache_clear()


def _font_archive() -> bytes:
    """A tar.xz shaped like the Nerd Fonts release: the four styles and more."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:xz") as archive:
        for name in (*fonts.NERD_FONT_FILES, "CaskaydiaMonoNerdFontMono-Regular.ttf"):
            data = name.encode()
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return buffer.getvalue()


class _Response(io.BytesIO):
    def getheader(self, name):
        return str(len(self.getvalue())) if name == "Content-Length" else None


def test_the_download_unpacks_only_the_four_styles(tmp_path, monkeypatch):
    import urllib.request

    archive = _font_archive()
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda request, timeout=None: _Response(archive)
    )
    seen = []

    files = fonts.download_font(tmp_path, lambda done, total: seen.append(total))

    assert [path.name for path in files] == list(fonts.NERD_FONT_FILES)
    assert all(path.exists() for path in files)
    assert not (tmp_path / "CaskaydiaMonoNerdFontMono-Regular.ttf").exists()
    assert seen and seen[-1] == len(archive)


def test_installing_copies_the_files_for_this_user(tmp_path, monkeypatch):
    font_dir = tmp_path / "fonts"
    monkeypatch.setattr(fonts, "user_font_dir", lambda: font_dir)
    registered = []
    monkeypatch.setattr(fonts, "_register_on_windows", registered.extend)
    monkeypatch.setattr(fonts, "_refresh_font_cache", lambda: None)
    sources = []
    for name in fonts.NERD_FONT_FILES:
        source = tmp_path / name
        source.write_bytes(b"font")
        sources.append(source)

    fonts.install_font(sources)

    assert fonts.font_installed()


def test_setup_font_installs_and_sets_windows_terminal(tmp_path, monkeypatch):
    from max_cli.interface.cli_config import app

    settings_path = _terminal_settings(tmp_path, {})
    installed = []
    monkeypatch.setattr(fonts, "font_installed", lambda: False)
    monkeypatch.setattr(
        fonts, "setup_font", lambda on_progress=None: installed.append(1) or tmp_path
    )
    monkeypatch.setattr(fonts, "terminal_settings_path", lambda: settings_path)

    result = runner.invoke(app, ["setup-font", "--yes"])

    assert result.exit_code == 0, result.output
    assert installed == [1]
    assert fonts.terminal_font_face(settings_path) == fonts.NERD_FONT_FACE
    assert "Windows Terminal now uses the font" in result.output


def test_setup_font_leaves_a_nerd_font_terminal_alone(tmp_path, monkeypatch):
    from max_cli.interface.cli_config import app

    settings_path = _terminal_settings(tmp_path, {"font": {"face": "Cascadia Code NF"}})
    monkeypatch.setattr(fonts, "font_installed", lambda: True)
    monkeypatch.setattr(fonts, "terminal_settings_path", lambda: settings_path)

    result = runner.invoke(app, ["setup-font", "--yes"])

    assert result.exit_code == 0, result.output
    assert "already uses a Nerd Font" in result.output
    assert not (tmp_path / "settings.json.max-backup").exists()


def test_auto_icons_follow_the_terminal_font(monkeypatch):
    from max_cli.config import settings
    from max_cli.interface.tui.widgets.page_icons import NERD_ICONS, page_glyph

    monkeypatch.setattr(settings, "DASHBOARD_ICONS", "auto")
    monkeypatch.setattr(fonts, "terminal_has_nerd_font", lambda: True)
    assert page_glyph("video").plain == NERD_ICONS["video"]

    monkeypatch.setattr(fonts, "terminal_has_nerd_font", lambda: False)
    assert page_glyph("video") is None
