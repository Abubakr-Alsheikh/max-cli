"""The Download page (grab-page-redesign.md, G2): modes, preview, downloads, cancel."""

import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button, DataTable, Input, RadioButton, RadioSet, Static

from max_cli.common.exceptions import OperationCancelled
from max_cli.core.engines.download_history import DownloadHistory
from max_cli.core.engines.task_manager import get_task_manager
from max_cli.core.engines.task_queue import TaskType
from max_cli.core.operations import grab
from max_cli.core.operations.grab import MediaInfo, PlaylistEntry, QualityOption
from max_cli.core.operations.result import ActionResult
from max_cli.interface.tui.ui_prefs import load_prefs
from max_cli.interface.tui.widgets.dialogs import ConfirmDialog
from max_cli.interface.tui.widgets.download_panel import DownloadPanel, DownloadRow

URL = "https://www.youtube.com/watch?v=abc"
DOWNLOAD = "max_cli.core.operations.grab.download"
PROBE = "max_cli.core.operations.grab.probe"

VIDEO = MediaInfo(
    url=URL,
    title="Trailer",
    uploader="Studio",
    duration=151,
    qualities=[
        QualityOption(1080, 82_000_000),
        QualityOption(720, None),
        QualityOption(1440, None),
    ],
    audio_size_bytes=2_000_000,
)


class PanelApp(App):
    def compose(self) -> ComposeResult:
        yield DownloadPanel()


@pytest.fixture(autouse=True)
def empty_probe_cache():
    grab._probe_cache.clear()
    yield
    grab._probe_cache.clear()


async def _settle(app: App, pilot) -> None:
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


def _text(app: App, selector: str) -> str:
    return str(app.query_one(selector, Static).content)


def _quality_labels(app: App) -> list[str]:
    return [
        str(b.label) for b in app.query_one("#dl-quality", RadioSet).query(RadioButton)
    ]


@pytest.mark.asyncio
async def test_simple_mode_hides_advanced_options_and_the_choice_is_remembered():
    app = PanelApp()
    async with app.run_test(size=(110, 60)) as pilot:
        assert not app.query_one("#dl-advanced").display

        app.query_one("#mode-advanced", RadioButton).value = True
        await pilot.pause()

        assert app.query_one("#dl-advanced").display
        assert app.query("#field-subtitles")
        assert app.query("#field-player_client")
    assert load_prefs()["download_mode"] == "advanced"

    app = PanelApp()
    async with app.run_test(size=(110, 60)):
        assert app.query_one("#dl-advanced").display


@pytest.mark.asyncio
async def test_check_shows_the_preview_with_real_qualities():
    app = PanelApp()
    with patch(PROBE, return_value=VIDEO):
        async with app.run_test(size=(110, 60)) as pilot:
            app.query_one("#dl-url", Input).value = URL
            app.query_one("#btn-check", Button).press()
            await _settle(app, pilot)

            assert "Trailer" in _text(app, "#dl-preview-title")
            assert "Studio" in _text(app, "#dl-preview-meta")
            assert "2:31" in _text(app, "#dl-preview-meta")
            labels = _quality_labels(app)

    assert labels[0] == "Best"
    assert labels[1].startswith("1080p ~")
    assert labels[2] == "720p"
    assert labels[3] == "1440p"
    assert labels[-1].startswith("Audio (MP3) ~")


@pytest.mark.asyncio
async def test_playlist_preview_says_how_many_items():
    playlist = MediaInfo(
        url=URL,
        title="My Mix",
        is_playlist=True,
        entries=[PlaylistEntry(1, "One", "u1"), PlaylistEntry(2, "Two", "u2")],
    )
    app = PanelApp()
    with patch(PROBE, return_value=playlist):
        async with app.run_test(size=(110, 60)) as pilot:
            app.query_one("#dl-url", Input).value = URL
            app.query_one("#btn-check", Button).press()
            await _settle(app, pilot)
            meta = _text(app, "#dl-preview-meta")

    assert "Playlist, 2 items" in meta


@pytest.mark.asyncio
async def test_bad_link_shows_an_error():
    app = PanelApp()
    with patch(PROBE, side_effect=RuntimeError("Unsupported URL")):
        async with app.run_test(size=(110, 60)) as pilot:
            app.query_one("#dl-url", Input).value = "https://example.com/nothing"
            app.query_one("#btn-check", Button).press()
            await _settle(app, pilot)
            title = _text(app, "#dl-preview-title")

    assert "Couldn't read this link" in title and "Unsupported URL" in title


@pytest.mark.asyncio
async def test_download_uses_the_chosen_quality_and_shows_done(tmp_path):
    saved = tmp_path / "Trailer.mp4"
    result = ActionResult(True, "Downloaded: Trailer", [saved], {"size_bytes": 5_000})
    app = PanelApp()
    with (
        patch(PROBE, return_value=VIDEO),
        patch(DOWNLOAD, return_value=result) as download,
    ):
        async with app.run_test(size=(110, 60)) as pilot:
            app.query_one("#dl-url", Input).value = URL
            app.query_one("#btn-check", Button).press()
            await _settle(app, pilot)
            # Pick "720p" (index 2).
            list(app.query_one("#dl-quality", RadioSet).query(RadioButton))[
                2
            ].value = True
            app.query_one("#dl-output", Input).value = str(tmp_path)
            app.query_one("#btn-download", Button).press()
            await _settle(app, pilot)

            row = app.query_one(DownloadRow)
            info = str(row.query_one(".row-info", Static).content)
            buttons = [str(b.label) for b in row.query(Button)]

    kwargs = download.call_args.kwargs
    assert kwargs["url"] == URL
    assert kwargs["quality"] == "m"
    assert kwargs["media_type"] == "video"
    assert kwargs["output"] == tmp_path
    assert callable(kwargs["should_cancel"])
    assert "Done." in info
    assert buttons == ["Open folder"]
    assert load_prefs()["download_folder"] == str(tmp_path)


@pytest.mark.asyncio
async def test_odd_heights_download_by_resolution(tmp_path):
    app = PanelApp()
    ok = ActionResult(True, "Downloaded", [])
    with patch(PROBE, return_value=VIDEO), patch(DOWNLOAD, return_value=ok) as download:
        async with app.run_test(size=(110, 60)) as pilot:
            app.query_one("#dl-url", Input).value = URL
            app.query_one("#btn-check", Button).press()
            await _settle(app, pilot)
            list(app.query_one("#dl-quality", RadioSet).query(RadioButton))[
                3
            ].value = True
            app.query_one("#btn-download", Button).press()
            await _settle(app, pilot)

    assert download.call_args.kwargs["resolution"] == 1440


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
            info = str(
                app.query_one(DownloadRow).query_one(".row-info", Static).content
            )
            buttons = [str(b.label) for b in app.query_one(DownloadRow).query(Button)]

    assert "Cancelled." in info
    assert buttons == ["Retry"]


@pytest.mark.asyncio
async def test_failed_download_can_be_retried():
    app = PanelApp()
    ok = ActionResult(True, "Downloaded: Trailer", [])
    with patch(DOWNLOAD, side_effect=[RuntimeError("HTTP Error 403"), ok]) as download:
        async with app.run_test(size=(110, 60)) as pilot:
            app.query_one("#dl-url", Input).value = URL
            app.query_one("#btn-download", Button).press()
            await _settle(app, pilot)
            first_info = str(
                app.query_one(DownloadRow).query_one(".row-info", Static).content
            )

            app.query_one("#retry-1", Button).press()
            await _settle(app, pilot)
            rows = list(app.query(DownloadRow))
            second_info = str(rows[0].query_one(".row-info", Static).content)

    assert "HTTP Error 403" in first_info
    assert len(rows) == 1 and rows[0].job.job_id == 2
    assert "Done." in second_info
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
        return ActionResult(True, "Downloaded", [])

    app = PanelApp()
    with patch(DOWNLOAD, side_effect=blocking_download):
        async with app.run_test(size=(110, 60)) as pilot:
            for url in (URL, URL + "2"):
                app.query_one("#dl-url", Input).value = url
                app.query_one("#btn-download", Button).press()
                await pilot.pause()
            await pilot.pause(0.3)
            infos = [
                str(r.query_one(".row-info", Static).content)
                for r in app.query(DownloadRow)
            ]
            release.set()
            await _settle(app, pilot)

    assert running == [URL, URL + "2"]
    assert "Waiting for a free slot" in infos[1]


@pytest.mark.asyncio
async def test_add_to_queue_creates_an_action_task():
    app = PanelApp()
    async with app.run_test(size=(110, 60)) as pilot:
        app.query_one("#dl-url", Input).value = URL
        app.query_one("#btn-queue", Button).press()
        await pilot.pause()
        status = _text(app, "#dl-status")

    [task] = get_task_manager().get_all()
    assert task.type == TaskType.ACTION
    assert task.payload["action"] == "grab.download"
    assert task.payload["args"]["url"] == URL
    assert "Added to the queue" in status


@pytest.mark.asyncio
async def test_empty_link_is_refused():
    app = PanelApp()
    with patch(DOWNLOAD) as download:
        async with app.run_test(size=(110, 60)) as pilot:
            app.query_one("#btn-download", Button).press()
            await _settle(app, pilot)
            status = _text(app, "#dl-status")

    download.assert_not_called()
    assert "'url' is required" in status


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
        await pilot.pause()
        assert isinstance(app.screen, ConfirmDialog)
        app.screen.query_one(answer, Button).press()
        await pilot.pause()
        rows = app.query_one("#download-history-table", DataTable).row_count

    assert rows == (0 if cleared else 1)


@pytest.mark.asyncio
async def test_repeat_link_warns():
    DownloadHistory().record_download(url=URL, title="Trailer", output_files=[])
    app = PanelApp()
    async with app.run_test(size=(110, 60)) as pilot:
        app.query_one("#dl-url", Input).value = URL
        await pilot.pause()
        warning = _text(app, "#dl-duplicate")

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
