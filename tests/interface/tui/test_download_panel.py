"""The Download page (grab-page-redesign.md): preview, modes, playlists, several links, rows."""

import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button, DataTable, Input, SelectionList, Static

from max_cli.common.exceptions import OperationCancelled
from max_cli.core.engines.download_history import DownloadHistory
from max_cli.core.engines.task_manager import get_task_manager
from max_cli.core.engines.task_queue import TaskType
from max_cli.core.operations import grab
from max_cli.core.operations.grab import MediaInfo, PlaylistEntry, QualityOption
from max_cli.core.operations.result import ActionResult
from max_cli.interface.tui.ui_prefs import load_prefs
from max_cli.interface.tui.widgets import download_panel
from max_cli.interface.tui.widgets.dialogs import ConfirmDialog
from max_cli.interface.tui.widgets.download_panel import (
    DownloadPanel,
    DownloadRow,
    playlist_items,
    short_size,
)

URL = "https://www.youtube.com/watch?v=abc"
DOWNLOAD = "max_cli.core.operations.grab.download"
PROBE = "max_cli.core.operations.grab.probe"
OK = ActionResult(True, "Downloaded: Trailer", [])

VIDEO = MediaInfo(
    url=URL,
    title="Trailer",
    uploader="Studio",
    duration=151,
    qualities=[
        QualityOption(1440, None),
        QualityOption(1080, 82_000_000),
        QualityOption(720, None),
    ],
    audio_size_bytes=2_000_000,
)
PLAYLIST = MediaInfo(
    url=URL,
    title="My Mix",
    is_playlist=True,
    entries=[PlaylistEntry(i, f"Song {i}", f"u{i}") for i in (1, 2, 3, 4)],
)


class PanelApp(App):
    def compose(self) -> ComposeResult:
        yield DownloadPanel()


@pytest.fixture(autouse=True)
def quiet_page(monkeypatch):
    """No automatic network checks unless a test asks, a clean probe cache, and
    grab settings that don't depend on the machine's own config."""
    from max_cli.config import settings

    monkeypatch.setattr(download_panel, "AUTO_CHECK_SECONDS", 3600)
    monkeypatch.setattr(settings, "GRAB_DEFAULT_TYPE", "video")
    monkeypatch.setattr(settings, "GRAB_QUALITY", "h")
    grab._probe_cache.clear()
    yield
    grab._probe_cache.clear()


async def _settle(app: App, pilot) -> None:
    """Let clicks land, workers finish, and scheduled re-renders (chips, rows) run."""
    await pilot.pause()
    await app.workers.wait_for_complete()
    for _ in range(5):
        await pilot.pause()


def _text(app: App, selector: str) -> str:
    return str(app.query_one(selector, Static).content)


def _chips(app: App) -> list[str]:
    return [str(chip.label) for chip in app.query(".chip")]


def _selected_chip(app: App) -> str:
    return next(str(c.label) for c in app.query(".chip") if c.has_class("-selected"))


def _press_chip(app: App, label_start: str) -> None:
    next(c for c in app.query(".chip") if str(c.label).startswith(label_start)).press()


async def _check(app: App, pilot, text: str = URL) -> None:
    app.query_one("#dl-url", Input).value = text
    app.query_one("#btn-check", Button).press()
    await _settle(app, pilot)


def _row_info(row: DownloadRow) -> str:
    return str(row.query_one(".row-info", Static).content)


# --- helpers ---------------------------------------------------------------


@pytest.mark.parametrize(
    "selected, total, expected",
    [
        ([1, 2, 3, 4], 4, None),
        ([1, 2, 3, 7], 8, "1-3,7"),
        ([5], 8, "5"),
        ([2, 4, 5, 6], 8, "2,4-6"),
    ],
)
def test_playlist_items(selected, total, expected):
    assert playlist_items(selected, total) == expected


def test_short_size():
    assert short_size(82_000_000) == "78 MB"
    assert short_size(2_400_000) == "2.3 MB"
    assert short_size(3 * 1024**3) == "3.0 GB"


# --- modes and preview -----------------------------------------------------


@pytest.mark.asyncio
async def test_advanced_mode_is_remembered():
    app = PanelApp()
    async with app.run_test(size=(110, 60)) as pilot:
        assert not app.query_one("#dl-advanced").display
        assert app.query_one("#mode-simple").has_class("-selected")

        app.query_one("#mode-advanced", Button).press()
        await pilot.pause()

        assert app.query_one("#dl-advanced").display
        assert app.query("#field-subtitles")
    assert load_prefs()["download_mode"] == "advanced"

    app = PanelApp()
    async with app.run_test(size=(110, 60)):
        assert app.query_one("#dl-advanced").display
        assert app.query_one("#mode-advanced").has_class("-selected")


@pytest.mark.asyncio
async def test_preview_shows_real_qualities_and_keeps_the_usual_pick(monkeypatch):
    from max_cli.config import settings

    monkeypatch.setattr(settings, "GRAB_QUALITY", "h")
    app = PanelApp()
    with patch(PROBE, return_value=VIDEO):
        async with app.run_test(size=(110, 60)) as pilot:
            await _check(app, pilot)
            title, meta = (
                _text(app, "#dl-preview-title"),
                _text(app, "#dl-preview-meta"),
            )
            chips, selected = _chips(app), _selected_chip(app)
            button = str(app.query_one("#btn-download", Button).label)

    assert title == "Trailer"
    assert "Studio" in meta and "2:31" in meta
    assert chips == ["Best", "1440p", "1080p · 78 MB", "720p"]
    assert selected == "1080p · 78 MB"
    assert button == "\u2b07 Download 1080p · 78 MB"


@pytest.mark.asyncio
async def test_error_text_with_brackets_does_not_crash_the_page():
    """A token-helper timeout quoting a command line crashed the page (MarkupError)."""
    error = r"Command '['C:\deno.EXE', '--allow-read=C:\cache']' timed out after 15.0 seconds"
    app = PanelApp()
    with patch(PROBE, side_effect=RuntimeError(error)):
        async with app.run_test(size=(110, 60)) as pilot:
            await _check(app, pilot)
            title, meta = (
                _text(app, "#dl-preview-title"),
                _text(app, "#dl-preview-meta"),
            )

    assert "Couldn't read this link" in title
    assert meta == error


@pytest.mark.asyncio
async def test_pasting_a_link_checks_it_automatically(monkeypatch):
    monkeypatch.setattr(download_panel, "AUTO_CHECK_SECONDS", 0.05)
    app = PanelApp()
    with patch(PROBE, return_value=VIDEO) as probe:
        async with app.run_test(size=(110, 60)) as pilot:
            app.query_one("#dl-url", Input).value = URL
            await pilot.pause(0.2)
            await _settle(app, pilot)
            title = _text(app, "#dl-preview-title")

    probe.assert_called_once_with(URL)
    assert title == "Trailer"


@pytest.mark.asyncio
async def test_enter_checks_then_enter_again_downloads():
    app = PanelApp()
    with patch(PROBE, return_value=VIDEO), patch(DOWNLOAD, return_value=OK) as download:
        async with app.run_test(size=(110, 60)) as pilot:
            url_box = app.query_one("#dl-url", Input)
            url_box.value = URL
            url_box.focus()
            await pilot.press("enter")
            await _settle(app, pilot)
            assert _text(app, "#dl-preview-title") == "Trailer"
            download.assert_not_called()

            await pilot.press("enter")
            await _settle(app, pilot)

    download.assert_called_once()


# --- downloading -----------------------------------------------------------


@pytest.mark.asyncio
async def test_download_uses_the_picked_quality_and_folder(tmp_path):
    result = ActionResult(
        True, "Downloaded: Trailer", [tmp_path / "t.mp4"], {"size_bytes": 5000}
    )
    app = PanelApp()
    with (
        patch(PROBE, return_value=VIDEO),
        patch(DOWNLOAD, return_value=result) as download,
    ):
        async with app.run_test(size=(110, 60)) as pilot:
            await _check(app, pilot)
            _press_chip(app, "720p")
            await pilot.pause()
            app.query_one("#dl-output", Input).value = str(tmp_path)
            app.query_one("#btn-download", Button).press()
            await _settle(app, pilot)
            row = app.query_one(DownloadRow)
            info, buttons = _row_info(row), [str(b.label) for b in row.query(Button)]
            url_after = app.query_one("#dl-url", Input).value

    kwargs = download.call_args.kwargs
    assert (kwargs["url"], kwargs["quality"], kwargs["media_type"]) == (
        URL,
        "m",
        "video",
    )
    assert kwargs["output"] == tmp_path
    assert "Done." in info
    assert buttons == ["Open folder"]
    assert url_after == ""
    assert load_prefs()["download_folder"] == str(tmp_path)


@pytest.mark.asyncio
async def test_heights_without_a_preset_download_by_resolution():
    app = PanelApp()
    with patch(PROBE, return_value=VIDEO), patch(DOWNLOAD, return_value=OK) as download:
        async with app.run_test(size=(110, 60)) as pilot:
            await _check(app, pilot)
            _press_chip(app, "1440p")
            await pilot.pause()
            app.query_one("#btn-download", Button).press()
            await _settle(app, pilot)

    assert download.call_args.kwargs["resolution"] == 1440


@pytest.mark.asyncio
async def test_audio_format_offers_bitrates():
    app = PanelApp()
    with patch(DOWNLOAD, return_value=OK) as download:
        async with app.run_test(size=(110, 60)) as pilot:
            app.query_one("#fmt-audio", Button).press()
            await _settle(app, pilot)
            chips = _chips(app)
            app.query_one("#dl-url", Input).value = URL
            app.query_one("#btn-download", Button).press()
            await _settle(app, pilot)

    assert chips[0] == "Best · 320 kbps"
    kwargs = download.call_args.kwargs
    assert (kwargs["media_type"], kwargs["quality"]) == ("audio", "h")
    assert load_prefs()["download_format"] == "audio"


@pytest.mark.asyncio
async def test_playlist_picker_sends_the_ticked_items():
    app = PanelApp()
    with (
        patch(PROBE, return_value=PLAYLIST),
        patch(DOWNLOAD, return_value=OK) as download,
    ):
        async with app.run_test(size=(110, 60)) as pilot:
            await _check(app, pilot)
            playlist = app.query_one("#dl-playlist", SelectionList)
            assert playlist.display and len(playlist.selected) == 4
            playlist.deselect(2)
            await pilot.pause()
            button = str(app.query_one("#btn-download", Button).label)
            app.query_one("#btn-download", Button).press()
            await _settle(app, pilot)

    assert "3 of 4 items" in button
    assert download.call_args.kwargs["playlist_items"] == "1,3-4"


@pytest.mark.asyncio
async def test_playlist_with_nothing_ticked_is_refused():
    app = PanelApp()
    with patch(PROBE, return_value=PLAYLIST), patch(DOWNLOAD) as download:
        async with app.run_test(size=(110, 60)) as pilot:
            await _check(app, pilot)
            app.query_one("#btn-pl-none", Button).press()
            await pilot.pause()
            app.query_one("#btn-download", Button).press()
            await _settle(app, pilot)
            status = _text(app, "#dl-status")

    download.assert_not_called()
    assert "Tick at least one" in status


@pytest.mark.asyncio
async def test_several_links_become_one_download_each():
    links = "https://youtu.be/one https://youtu.be/two https://youtu.be/three"
    app = PanelApp()
    with patch(DOWNLOAD, return_value=OK) as download:
        async with app.run_test(size=(110, 60)) as pilot:
            await _check(app, pilot, links)
            title = _text(app, "#dl-preview-title")
            button = str(app.query_one("#btn-download", Button).label)
            app.query_one("#btn-download", Button).press()
            await _settle(app, pilot)
            rows = len(app.query(DownloadRow))

    assert title == "3 links"
    assert "3 links" in button
    assert rows == 3
    assert sorted(c.kwargs["url"] for c in download.call_args_list) == [
        "https://youtu.be/one",
        "https://youtu.be/three",
        "https://youtu.be/two",
    ]


@pytest.mark.asyncio
async def test_cancel_stops_a_running_download():
    started = threading.Event()

    def slow_download(**kwargs):
        started.set()
        while not kwargs["should_cancel"]():
            threading.Event().wait(0.01)
        raise OperationCancelled("Download cancelled")

    app = PanelApp()
    with patch(DOWNLOAD, side_effect=slow_download):
        async with app.run_test(size=(110, 60)) as pilot:
            app.query_one("#dl-url", Input).value = URL
            app.query_one("#btn-download", Button).press()
            await pilot.pause()
            assert started.wait(5)
            app.query_one("#cancel-1", Button).press()
            await _settle(app, pilot)
            row = app.query_one(DownloadRow)
            info, buttons = _row_info(row), [str(b.label) for b in row.query(Button)]

    assert "Cancelled." in info
    assert buttons == ["Retry"]


@pytest.mark.asyncio
async def test_failed_download_can_be_retried():
    app = PanelApp()
    with patch(
        DOWNLOAD, side_effect=[RuntimeError("HTTP Error 403 [forbidden]"), OK]
    ) as download:
        async with app.run_test(size=(110, 60)) as pilot:
            app.query_one("#dl-url", Input).value = URL
            app.query_one("#btn-download", Button).press()
            await _settle(app, pilot)
            first = _row_info(app.query_one(DownloadRow))
            app.query_one("#retry-1", Button).press()
            await _settle(app, pilot)
            rows = list(app.query(DownloadRow))
            second = _row_info(rows[0])

    assert "HTTP Error 403 [forbidden]" in first
    assert len(rows) == 1 and rows[0].job.job_id == 2
    assert "Done." in second
    assert download.call_count == 2


@pytest.mark.asyncio
async def test_only_the_allowed_number_run_at_once(monkeypatch):
    from max_cli.config import settings

    monkeypatch.setattr(settings, "GRAB_MAX_CONCURRENT", 1)
    release = threading.Event()
    running = []

    def blocking_download(**kwargs):
        running.append(kwargs["url"])
        release.wait(5)
        return OK

    app = PanelApp()
    with patch(DOWNLOAD, side_effect=blocking_download):
        async with app.run_test(size=(110, 60)) as pilot:
            await _check(app, pilot, f"{URL} {URL}2")
            app.query_one("#btn-download", Button).press()
            await pilot.pause(0.3)
            infos = [_row_info(row) for row in app.query(DownloadRow)]
            tab = str(app.query_one("#dl-tabs").get_tab("tab-active").label)
            release.set()
            await _settle(app, pilot)

    assert len(running) == 2
    assert "Waiting for a free slot" in infos[1]
    assert "2 running" in tab


@pytest.mark.asyncio
async def test_queue_for_later_creates_action_tasks():
    app = PanelApp()
    async with app.run_test(size=(110, 60)) as pilot:
        app.query_one("#dl-url", Input).value = URL
        app.query_one("#btn-queue", Button).press()
        await pilot.pause()
        status = _text(app, "#dl-status")

    [task] = get_task_manager().get_all()
    assert task.type == TaskType.ACTION
    assert task.payload["args"]["url"] == URL
    assert "Added 1 to the queue" in status


@pytest.mark.asyncio
async def test_empty_link_is_refused():
    app = PanelApp()
    with patch(DOWNLOAD) as download:
        async with app.run_test(size=(110, 60)) as pilot:
            app.query_one("#btn-download", Button).press()
            await _settle(app, pilot)
            status = _text(app, "#dl-status")

    download.assert_not_called()
    assert "Paste a link first" in status


# --- history ---------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer, cleared", [("#confirm-yes", True), ("#confirm-no", False)]
)
async def test_clearing_history_asks_first(answer, cleared):
    DownloadHistory().record_download(url=URL, title="Trailer", output_files=[])
    app = PanelApp()
    async with app.run_test(size=(110, 60)) as pilot:
        assert app.query_one("#download-history-table", DataTable).row_count == 1
        app.query_one("#btn-clear-history", Button).press()
        await _settle(app, pilot)
        assert isinstance(app.screen, ConfirmDialog)
        app.screen.query_one(answer, Button).press()
        await _settle(app, pilot)
        rows = app.query_one("#download-history-table", DataTable).row_count

    assert rows == (0 if cleared else 1)


@pytest.mark.asyncio
async def test_download_again_puts_the_link_back():
    DownloadHistory().record_download(url=URL, title="Trailer", output_files=[])
    app = PanelApp()
    with patch(PROBE, return_value=VIDEO):
        async with app.run_test(size=(110, 60)) as pilot:
            app.query_one("#btn-history-again", Button).press()
            await _settle(app, pilot)
            url, title = (
                app.query_one("#dl-url", Input).value,
                _text(app, "#dl-preview-title"),
            )
            warning = _text(app, "#dl-duplicate")

    assert url == URL
    assert title == "Trailer"
    assert "You downloaded this before: Trailer" in warning


def test_open_folder_uses_the_system_file_manager(tmp_path):
    from max_cli.common import utils

    with (
        patch.object(utils.sys, "platform", "linux"),
        patch.object(utils.subprocess, "run") as run,
    ):
        utils.open_in_file_manager(tmp_path / "video.mp4")

    run.assert_called_once_with(["xdg-open", str(tmp_path)], check=False)
    assert Path(run.call_args.args[0][1]) == tmp_path
