"""The Settings page (it replaced Config, System and Analytics)."""

import re
from pathlib import Path
from unittest.mock import patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button, Checkbox, Input, Select, Static

from max_cli.common.settings_file import read_settings_file, settings_file_path
from max_cli.config import Settings, settings
from max_cli.interface.tui.widgets import settings_panel
from max_cli.interface.tui.widgets.dialogs import ConfirmDialog
from max_cli.interface.tui.widgets.settings_panel import FIELDS, UNUSED, SettingsPanel
from max_cli.interface.tui.workers import _show_if_open

SIZE = (130, 80)
SRC = Path(__file__).resolve().parents[3] / "src" / "max_cli"
# Places that list settings rather than use them.
NOT_A_USE = ("config.py", "interface/config/", "settings_panel.py")


class SettingsApp(App):
    def compose(self) -> ComposeResult:
        yield SettingsPanel(id="settings-panel")


@pytest.fixture(autouse=True)
def restore_settings(monkeypatch):
    """The page applies saved values to the shared settings object."""
    before = settings.model_dump()
    monkeypatch.chdir(Path(__file__).parent)  # no .env from the repo root
    yield
    for name, value in before.items():
        setattr(settings, name, value)


async def _settle(app: App, pilot) -> None:
    await pilot.pause()
    await app.workers.wait_for_complete()
    for _ in range(3):
        await pilot.pause()


def _status(app: App) -> str:
    return str(app.query_one("#settings-status", Static).content)


def _used_settings() -> set[str]:
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        relative = path.relative_to(SRC).as_posix()
        if any(part in relative for part in NOT_A_USE):
            continue
        text = path.read_text(encoding="utf-8")
        found |= set(re.findall(r"settings\.([A-Z][A-Z0-9_]+)", text))
        found |= set(re.findall(r'Setting\("([A-Z][A-Z0-9_]+)"\)', text))
    return found & set(Settings.model_fields)


# --- which settings show ------------------------------------------------------


def test_every_setting_is_shown_or_known_to_be_unused():
    assert set(FIELDS) | UNUSED == set(Settings.model_fields)
    assert not set(FIELDS) & UNUSED


def test_the_page_shows_every_setting_the_code_reads():
    used = _used_settings()

    assert used <= set(FIELDS), f"read but not on the page: {used - set(FIELDS)}"
    assert not used & UNUSED, f"marked unused but read: {used & UNUSED}"


def test_format_size():
    from max_cli.common.utils import format_size

    assert format_size(512) == "512.00 B"
    assert format_size(1536) == "1.50 KB"
    assert format_size(1073741824) == "1.00 GB"


# --- editing ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_controls_start_from_the_current_settings(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-secret")
    monkeypatch.setattr(settings, "GRAB_QUALITY", "m")
    monkeypatch.setattr(settings, "GRAB_STRIP_PLAYLIST", False)
    app = SettingsApp()
    async with app.run_test(size=SIZE) as pilot:
        await _settle(app, pilot)
        key = app.query_one("#set-OPENAI_API_KEY", Input)
        quality = app.query_one("#set-GRAB_QUALITY", Select).value
        strip = app.query_one("#set-GRAB_STRIP_PLAYLIST", Checkbox).value
        save_disabled = app.query_one("#btn-save-settings", Button).disabled

    assert key.value == "sk-secret" and key.password
    assert quality == "m" and strip is False
    assert save_disabled


@pytest.mark.asyncio
async def test_show_reveals_the_api_key():
    app = SettingsApp()
    async with app.run_test(size=SIZE) as pilot:
        await _settle(app, pilot)
        app.query_one("#reveal-OPENAI_API_KEY", Button).press()
        await pilot.pause()
        shown = not app.query_one("#set-OPENAI_API_KEY", Input).password
        label = str(app.query_one("#reveal-OPENAI_API_KEY", Button).label)

    assert shown and label == "Hide"


@pytest.mark.asyncio
async def test_save_writes_only_what_changed_and_applies_it():
    app = SettingsApp()
    async with app.run_test(size=SIZE) as pilot:
        await _settle(app, pilot)
        app.query_one("#set-GRAB_QUALITY", Select).value = "x"
        app.query_one("#set-MAX_WORKERS", Input).value = "8"
        await pilot.pause()
        pending = _status(app)
        app.query_one("#btn-save-settings", Button).press()
        await _settle(app, pilot)
        after = _status(app)

    assert pending == "2 unsaved changes"
    assert read_settings_file() == {"GRAB_QUALITY": "x", "MAX_WORKERS": "8"}
    assert (settings.GRAB_QUALITY, settings.MAX_WORKERS) == ("x", 8)
    assert after == "Everything saved."


@pytest.mark.asyncio
async def test_a_bad_value_is_refused_and_nothing_is_written():
    app = SettingsApp()
    async with app.run_test(size=SIZE) as pilot:
        await _settle(app, pilot)
        app.query_one("#set-MAX_WORKERS", Input).value = "99"
        await pilot.pause()
        app.query_one("#btn-save-settings", Button).press()
        await _settle(app, pilot)
        status = _status(app)

    assert status.startswith("Images at once (1-16):")
    assert not settings_file_path().exists()
    assert settings.MAX_WORKERS != 99


@pytest.mark.asyncio
async def test_emptying_the_api_key_removes_it(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-old")
    settings_file_path().write_text("OPENAI_API_KEY=sk-old\n", encoding="utf-8")
    app = SettingsApp()
    async with app.run_test(size=SIZE) as pilot:
        await _settle(app, pilot)
        app.query_one("#set-OPENAI_API_KEY", Input).value = ""
        await pilot.pause()
        app.query_one("#btn-save-settings", Button).press()
        await _settle(app, pilot)

    assert read_settings_file() == {}
    assert settings.OPENAI_API_KEY is None


@pytest.mark.asyncio
async def test_discard_puts_the_saved_values_back():
    app = SettingsApp()
    async with app.run_test(size=SIZE) as pilot:
        await _settle(app, pilot)
        original = app.query_one("#set-AI_MODEL", Input).value
        app.query_one("#set-AI_MODEL", Input).value = "something-else"
        await pilot.pause()
        app.query_one("#btn-discard-settings", Button).press()
        await pilot.pause()
        value = app.query_one("#set-AI_MODEL", Input).value

    assert value == original
    assert not settings_file_path().exists()


# --- maintenance --------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer, reset", [("#confirm-yes", True), ("#confirm-no", False)]
)
async def test_reset_asks_then_removes_the_settings_file(answer, reset):
    settings_file_path().write_text("GRAB_QUALITY=s\n", encoding="utf-8")
    app = SettingsApp()
    async with app.run_test(size=SIZE) as pilot:
        await _settle(app, pilot)
        app.query_one("#btn-reset-settings", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmDialog)
        app.screen.query_one(answer, Button).press()
        await _settle(app, pilot)

    assert settings_file_path().exists() != reset


@pytest.mark.asyncio
async def test_clear_cache_asks_first():
    app = SettingsApp()
    with patch("max_cli.common.cache.Cache.clear", return_value=3) as clear:
        async with app.run_test(size=SIZE) as pilot:
            await _settle(app, pilot)
            app.query_one("#btn-clear-cache", Button).press()
            await pilot.pause()
            app.screen.query_one("#confirm-yes", Button).press()
            await _settle(app, pilot)

    clear.assert_called_once()


@pytest.mark.asyncio
async def test_maintenance_reports_ffmpeg_and_data(monkeypatch):
    from max_cli.common.exceptions import ResourceNotFoundError
    from max_cli.common.ffmpeg_resolver import FFmpegResolver

    def missing(self, **_):
        raise ResourceNotFoundError("no ffmpeg")

    monkeypatch.setattr(FFmpegResolver, "resolve", missing)
    app = SettingsApp()
    async with app.run_test(size=SIZE) as pilot:
        await _settle(app, pilot)
        ffmpeg = str(app.query_one("#upkeep-ffmpeg", Static).content)
        about = str(app.query_one("#upkeep-about", Static).content)

    assert "not found" in ffmpeg
    assert about.startswith("MAX CLI")


@pytest.mark.asyncio
async def test_a_local_env_file_is_pointed_out(tmp_path, monkeypatch):
    """A .env in the current folder loads after ~/.max_config.env and wins."""
    (tmp_path / ".env").write_text("GRAB_QUALITY=s\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    app = SettingsApp()
    async with app.run_test(size=SIZE) as pilot:
        await _settle(app, pilot)
        line = str(app.query_one("#upkeep-file", Static).content)

    assert ".env" in line and "GRAB_QUALITY" in line


# --- the dashboard ------------------------------------------------------------


def test_the_sidebar_pages():
    from max_cli.interface.tui.widgets.sidebar import SECTION_KEYS, SECTIONS

    assert [section_id for section_id, _icon, _label in SECTIONS] == [
        "home",
        "download",
        "video",
        "audio",
        "images",
        "pdf",
        "files",
        "chat",
        "queue",
        "history",
        "settings",
    ]
    assert SECTION_KEYS["history"] == "0"
    assert SECTION_KEYS["settings"] == ","
    assert len(set(SECTION_KEYS.values())) == len(SECTION_KEYS)


@pytest.mark.asyncio
async def test_the_comma_key_opens_settings():
    from max_cli.interface.tui.app import MaxDashboardApp

    app = MaxDashboardApp()
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.query_one("#sidebar").focus()
        await pilot.press(",")
        await pilot.pause()
        shown = app.query_one("#settings-panel").display

    assert shown


@pytest.mark.asyncio
@pytest.mark.parametrize("old_page", ["config", "system"])
async def test_a_saved_old_page_opens_settings(old_page):
    from max_cli.interface.tui.app import MaxDashboardApp
    from max_cli.interface.tui.ui_prefs import save_pref

    save_pref("last_page", old_page)
    app = MaxDashboardApp()
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        shown = app.query_one("#settings-panel").display

    assert shown


def test_keep_days_matches_the_buttons():
    assert settings_panel.KEEP_DAYS == 30


def test_folder_size_skips_files_that_vanish_mid_walk(tmp_path, monkeypatch):
    """The task store renames temp files while the page adds up sizes; a
    FileNotFoundError from one of them crashed the page's worker."""
    (tmp_path / "kept.json").write_bytes(b"x" * 10)
    gone = tmp_path / "queue.json.tmp"
    gone.write_bytes(b"y" * 5)
    real_stat = Path.stat
    looks = {"count": 0}

    def stat(self, *args, **kwargs):
        # The walk sees the file (first look); it's renamed before its size
        # is read (second look).
        if self.name == gone.name:
            looks["count"] += 1
            if looks["count"] > 1:
                gone.unlink(missing_ok=True)
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)

    assert settings_panel._folder_size(tmp_path) == 10
    assert looks["count"] >= 2


@pytest.mark.asyncio
async def test_a_late_worker_result_is_ignored_when_the_page_is_closing():
    """The sizes worker can finish after shutdown starts; its NoMatches failed
    a dashboard test on the Python 3.9 CI run."""
    app = SettingsApp()
    async with app.run_test(size=SIZE) as pilot:
        await _settle(app, pilot)
        panel = app.query_one(SettingsPanel)
        await panel.remove_children()

        facts = {
            "ffmpeg": None,
            "data_size": 0,
            "cache": (0, 0),
            "backups": (0, 0),
            "undo": 0,
        }
        _show_if_open(panel, panel._show_upkeep, facts)  # must not raise
