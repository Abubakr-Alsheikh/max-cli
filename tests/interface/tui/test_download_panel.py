"""The Download page (grab-page-redesign.md): preview, modes, playlists, several links, rows."""

import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import (
    Button,
    DataTable,
    Input,
    SelectionList,
    Static,
    TabbedContent,
)

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
# Waiting for a state change: up to 100 x 0.05 s, for runs under load.
POLL_ATTEMPTS = 100
POLL_SECONDS = 0.05
# A fake download that waits for Cancel gives up after this long.
FAKE_DOWNLOAD_SECONDS = 10

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
    # The real check imports yt-dlp and asks about its plugins.
    monkeypatch.setattr(
        grab, "youtube_fix_status", lambda **_: grab.YoutubeFixStatus(True, True)
    )
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


# --- options and preview ---------------------------------------------------


@pytest.mark.asyncio
async def test_options_show_without_a_mode_switch():
    """The Simple/Advanced switch went: the options card fits in a corner."""
    app = PanelApp()
    async with app.run_test(size=(110, 60)):
        shown = app.query_one("#dl-advanced").display
        has_fields = bool(app.query("#field-subtitles"))
        switches = app.query("#mode-simple, #mode-advanced")

    assert shown and has_fields
    assert not switches


# --- checking a link ---------------------------------------------------------


def _held_probe(release: threading.Event, answer):
    """A probe that waits for `release`, then returns `answer` or raises it.

    Keep the patch around the whole test: the worker thread may call the
    probe after a shorter `with` block ended, and then the real one ran.
    """

    def held_probe(url):
        release.wait(5)
        if isinstance(answer, Exception):
            raise answer
        return answer

    return patch(PROBE, side_effect=held_probe)


async def _start_check(app: App, pilot) -> None:
    app.query_one("#dl-url", Input).value = URL
    app.query_one("#btn-check", Button).press()
    await pilot.pause()


@pytest.mark.asyncio
async def test_check_locks_its_button_and_spins_until_the_answer():
    release = threading.Event()
    app = PanelApp()
    with _held_probe(release, VIDEO):
        async with app.run_test(size=(110, 60)) as pilot:
            await _start_check(app, pilot)
            button = app.query_one("#btn-check", Button)
            locked, label = button.disabled, str(button.label)
            first = _text(app, "#dl-preview-title")
            await pilot.pause(download_panel.SPINNER_SECONDS * 3)
            later = _text(app, "#dl-preview-title")
            release.set()
            await _settle(app, pilot)
            unlocked, label_after = not button.disabled, str(button.label)
            title = _text(app, "#dl-preview-title")

    assert locked and label == "Checking"
    assert "Checking the link" in first
    assert first[0] != later[0]  # the spinner moved
    assert unlocked and label_after == "Check"
    assert title == "Trailer"


@pytest.mark.asyncio
async def test_a_failed_check_unlocks_the_button():
    release = threading.Event()
    release.set()
    app = PanelApp()
    with _held_probe(release, RuntimeError("no such video")):
        async with app.run_test(size=(110, 60)) as pilot:
            await _start_check(app, pilot)
            await _settle(app, pilot)
            button = app.query_one("#btn-check", Button)
            title = _text(app, "#dl-preview-title")

    assert not button.disabled and str(button.label) == "Check"
    assert title == "Couldn't read this link."


def test_a_slow_check_says_why():
    panel = DownloadPanel()
    panel._check_started = download_panel.time.monotonic() - 10

    assert "slow on the first check" in panel._checking_line().plain


@pytest.mark.asyncio
async def test_an_older_answer_does_not_end_a_newer_check():
    app = PanelApp()
    async with app.run_test(size=(110, 60)) as pilot:
        panel = app.query_one(DownloadPanel)
        panel._start_checking("new link")
        panel._show_probe_error("too late", "old link")
        await pilot.pause()
        still_checking = panel.is_checking
        locked = app.query_one("#btn-check", Button).disabled

    assert still_checking and locked


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

    assert chips[0] == "320 kbps"
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
        # A deadline, so a test that fails before Cancel can't hang the run.
        deadline = time.monotonic() + FAKE_DOWNLOAD_SECONDS
        while not kwargs["should_cancel"]() and time.monotonic() < deadline:
            threading.Event().wait(0.01)
        raise OperationCancelled("Download cancelled")

    app = PanelApp()
    with patch(DOWNLOAD, side_effect=slow_download):
        async with app.run_test(size=(110, 60)) as pilot:
            app.query_one("#dl-url", Input).value = URL
            app.query_one("#btn-download", Button).press()
            # Wait by yielding to the app. started.wait() blocked its event
            # loop, and a thread worker only starts when that loop runs: under
            # load the download never started and the test hung.
            for _ in range(POLL_ATTEMPTS):
                await pilot.pause(POLL_SECONDS)
                if started.is_set():
                    break
            assert started.is_set()
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


@pytest.mark.asyncio
async def test_progress_updates_leave_the_tabs_alone():
    """Relabelling a tab restarts its underline animation, which flashed the
    page on every progress tick. Only a state change may touch the tabs."""
    release = threading.Event()

    def held_download(**kwargs):
        release.wait(5)
        return OK

    app = PanelApp()
    with patch(DOWNLOAD, side_effect=held_download):
        async with app.run_test(size=(110, 60)) as pilot:
            app.query_one("#dl-url", Input).value = URL
            app.query_one("#btn-download", Button).press()
            await pilot.pause()
            panel = app.query_one(DownloadPanel)
            job = panel._jobs[1]
            tab = panel.query_one("#dl-tabs").get_tab("tab-active")
            label_before = tab.label

            for percent in (10.0, 20.0, 30.0):
                panel._row_call(job, "set_progress", percent, 1024.0, 5)
            panel._sync_tab_counts()

            assert tab.label is label_before
            release.set()
            await _settle(app, pilot)
            assert str(tab.label) == "Downloads"


# --- richer preview ----------------------------------------------------------

RICH_VIDEO = MediaInfo(
    url=URL,
    title="Trailer",
    uploader="Studio",
    duration=151,
    qualities=[QualityOption(1080, 82_000_000, fps=60), QualityOption(720, None)],
    audio_size_bytes=2_000_000,
    audio_codec="opus",
    audio_bitrate=131,
    site="youtube.com",
    upload_date="2024-05-01",
    view_count=1_234_567,
    like_count=34_500,
    subtitle_languages=["ar", "de", "en", "es", "fr", "ja"],
    has_auto_captions=True,
    chapter_count=12,
)


def test_media_facts_lists_what_the_site_says():
    facts = download_panel.media_facts(RICH_VIDEO).plain

    for expected in (
        "Studio",
        "2:31",
        "12 chapters",
        "1.2M views",
        "34K likes",
        "2024-05-01",
        "up to 1080p60",
        "opus",
        "131 kbps",
        "ar, de, en, es +2 more",
        "auto captions",
        "youtube.com",
    ):
        assert expected in facts


def test_media_facts_skips_what_the_site_left_out():
    facts = download_panel.media_facts(VIDEO).plain

    assert "Stats" not in facts and "Subtitles" not in facts


def test_media_facts_for_a_playlist_counts_items_and_length():
    playlist = MediaInfo(
        url=URL,
        title="Mix",
        is_playlist=True,
        entries=[PlaylistEntry(1, "a", "u1", 60), PlaylistEntry(2, "b", "u2", 125)],
    )

    assert "2 videos  ·  3:05 in all" in download_panel.media_facts(playlist).plain


@pytest.mark.asyncio
async def test_audio_chips_show_the_mp3_size_of_a_checked_video():
    app = PanelApp()
    with patch(PROBE, return_value=RICH_VIDEO):
        async with app.run_test(size=(140, 60)) as pilot:
            await _check(app, pilot)
            app.query_one("#fmt-audio", Button).press()
            await _settle(app, pilot)
            chips = _chips(app)
            button = str(app.query_one("#btn-download", Button).label)

    # 192 kbps for 151 s is 3.6 million bytes.
    assert "192 kbps · 3.5 MB" in chips
    assert button == "⬇ Download MP3 192 kbps · 3.5 MB"


# --- advanced options ------------------------------------------------------


@pytest.mark.asyncio
async def test_options_are_compact_and_reach_the_download():
    from textual.widgets import Checkbox

    app = PanelApp()
    with patch(DOWNLOAD, return_value=OK) as download:
        async with app.run_test(size=(140, 60)) as pilot:
            await _settle(app, pilot)
            height = app.query_one("#dl-advanced").outer_size.height
            app.query_one("#field-subtitles", Checkbox).value = True
            app.query_one("#dl-url", Input).value = URL
            app.query_one("#btn-download", Button).press()
            await _settle(app, pilot)

    # Two fields and four checkboxes. It was 30 rows: one field per 5 rows.
    assert height <= 12
    assert download.call_args.kwargs["subtitles"] is True


@pytest.mark.asyncio
async def test_tags_reach_the_download_and_the_folder_choice_is_kept():
    from textual.widgets import Checkbox, Select

    with patch(DOWNLOAD, return_value=OK) as download:
        app = PanelApp()
        async with app.run_test(size=(140, 60)) as pilot:
            await _settle(app, pilot)
            app.query_one("#dl-tags #field-artist", Input).value = "Me"
            app.query_one("#dl-tags #field-album", Input).value = "Mine"
            app.query_one("#dl-tags #field-sort_into", Select).value = "artist/album"
            app.query_one("#dl-tags #field-track_numbers", Checkbox).value = False
            app.query_one("#dl-url", Input).value = URL
            app.query_one("#btn-download", Button).press()
            await _settle(app, pilot)

        again = PanelApp()
        async with again.run_test(size=(140, 60)) as pilot:
            await _settle(again, pilot)
            artist = again.query_one("#dl-tags #field-artist", Input).value
            sort_into = again.query_one("#dl-tags #field-sort_into", Select).value
            numbers = again.query_one("#dl-tags #field-track_numbers", Checkbox).value

    sent = download.call_args.kwargs
    assert (sent["artist"], sent["album"]) == ("Me", "Mine")
    assert sent["sort_into"] == "artist/album"
    assert sent["track_numbers"] is False
    # Folders and numbering are kept for next time; the artist isn't.
    assert (artist, sort_into, numbers) == ("", "artist/album", False)


@pytest.mark.asyncio
async def test_a_checked_playlist_says_what_the_files_get():
    app = PanelApp()
    with patch(PROBE, return_value=PLAYLIST):
        async with app.run_test(size=(110, 60)) as pilot:
            await _check(app, pilot)
            hint = str(app.query_one("#dl-tags-hint", Static).render())

    assert "My Mix" in hint
    assert "1-4" in hint


# --- transfers ---------------------------------------------------------------


def _record_history(count: int) -> None:
    for number in range(count):
        DownloadHistory().record_download(
            url=f"{URL}{number}",
            title=f"Video {number}" if number % 2 else f"Song {number}",
            output_files=[],
            settings_used={"audio_only": number % 2 == 0, "quality": "h"},
        )


def _history_titles(app: App) -> list[str]:
    table = app.query_one("#download-history-table", DataTable)
    return [str(table.get_row_at(row)[1]) for row in range(table.row_count)]


@pytest.mark.asyncio
async def test_history_shows_a_page_at_a_time_without_its_own_scrollbar():
    _record_history(20)
    app = PanelApp()
    async with app.run_test(size=(140, 60)) as pilot:
        await _settle(app, pilot)
        app.query_one("#dl-tabs", TabbedContent).active = "tab-history"
        await _settle(app, pilot)
        table = app.query_one("#download-history-table", DataTable)
        first_page = _history_titles(app)
        no_inner_scroll = table.max_scroll_y == 0
        app.query_one("#btn-history-next", Button).press()
        await _settle(app, pilot)
        second_page = _history_titles(app)
        page_label = _text(app, "#dl-history-page")
        app.query_one("#btn-history-next", Button).press()
        await _settle(app, pilot)
        last_page = _history_titles(app)
        next_disabled = app.query_one("#btn-history-next", Button).disabled

    assert len(first_page) == len(second_page) == download_panel.HISTORY_PAGE_ROWS
    assert first_page[0] == "Video 19"  # newest first
    assert not set(first_page) & set(second_page)
    assert page_label == "2 of 3"
    assert len(last_page) == 4 and next_disabled
    assert no_inner_scroll


@pytest.mark.asyncio
async def test_history_filter_narrows_the_list():
    _record_history(6)
    app = PanelApp()
    async with app.run_test(size=(140, 60)) as pilot:
        app.query_one("#dl-history-filter", Input).value = "song"
        await _settle(app, pilot)
        titles = _history_titles(app)
        app.query_one("#dl-history-filter", Input).value = "nothing like this"
        await _settle(app, pilot)
        empty = _text(app, "#dl-history-empty")
        table_shown = app.query_one("#download-history-table").display

    assert titles == ["Song 4", "Song 2", "Song 0"]
    assert empty == "Nothing matches the filter."
    assert not table_shown


def test_history_kind_names_the_format():
    assert download_panel.history_kind({"audio_only": True}) == "Audio MP3"
    assert download_panel.history_kind({"quality": "m"}) == "Video 720p"
    assert download_panel.history_kind({"custom_height": 1440}) == "Video 1440p"


@pytest.mark.asyncio
async def test_clear_finished_removes_only_finished_rows():
    release = threading.Event()

    def download(**kwargs):
        if kwargs["url"].endswith("slow"):
            release.wait(5)
        return OK

    app = PanelApp()
    with patch(DOWNLOAD, side_effect=download):
        async with app.run_test(size=(140, 60)) as pilot:
            app.query_one("#dl-url", Input).value = f"{URL} {URL}slow"
            app.query_one("#btn-download", Button).press()
            panel = app.query_one(DownloadPanel)
            # Wait for states, not a fixed time: the suite runs under load.
            for _ in range(POLL_ATTEMPTS):
                await pilot.pause(POLL_SECONDS)
                if panel._jobs[1].finished and app.query_one("#dl-jobs-bar").display:
                    break
            app.query_one("#btn-clear-finished", Button).press()
            for _ in range(POLL_ATTEMPTS):
                await pilot.pause(POLL_SECONDS)
                if len(app.query(DownloadRow)) == 1:
                    break
            left = [row.job.url for row in app.query(DownloadRow)]
            bar_shown = app.query_one("#dl-jobs-bar").display
            release.set()
            await _settle(app, pilot)

    assert left == [f"{URL}slow"]
    assert not bar_shown


# --- tools -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_sum_up_the_history():
    _record_history(3)
    app = PanelApp()
    async with app.run_test(size=(140, 60)):
        stats = _text(app, "#dl-stats")

    assert "3 downloads" in stats and "1 site" in stats


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "installed, deno, button_shown, text",
    [
        (True, True, False, "installed"),
        (False, True, True, "not installed"),
        (False, False, False, "needs Deno"),
    ],
)
async def test_youtube_fix_status(monkeypatch, installed, deno, button_shown, text):
    monkeypatch.setattr(
        grab, "youtube_fix_status", lambda **_: grab.YoutubeFixStatus(installed, deno)
    )
    app = PanelApp()
    async with app.run_test(size=(140, 60)) as pilot:
        await _settle(app, pilot)
        status = _text(app, "#dl-fix-status")
        shown = app.query_one("#btn-youtube-fix").display

    assert text in status
    assert shown == button_shown


@pytest.mark.asyncio
async def test_installing_the_youtube_fix_asks_first(monkeypatch):
    states = iter(
        [grab.YoutubeFixStatus(False, True), grab.YoutubeFixStatus(True, True)]
    )
    monkeypatch.setattr(grab, "youtube_fix_status", lambda **_: next(states))
    app = PanelApp()
    with patch.object(
        grab, "install_youtube_fix", return_value=ActionResult(True, "Installed.")
    ) as install:
        async with app.run_test(size=(140, 60)) as pilot:
            await _settle(app, pilot)
            app.query_one("#btn-youtube-fix", Button).press()
            await _settle(app, pilot)
            assert isinstance(app.screen, ConfirmDialog)
            app.screen.query_one("#confirm-yes", Button).press()
            await _settle(app, pilot)
            status = _text(app, "#dl-fix-status")

    install.assert_called_once()
    assert "installed" in status and "not" not in status


@pytest.mark.asyncio
async def test_tool_buttons_open_other_pages():
    from max_cli.interface.tui.messages import OpenPage

    opened: list[tuple[str, str]] = []

    class RecordingApp(PanelApp):
        def on_open_page(self, message: OpenPage) -> None:
            opened.append((message.section_id, message.tab))

    app = RecordingApp()
    async with app.run_test(size=(140, 60)) as pilot:
        app.query_one("#btn-goto-queue", Button).press()
        app.query_one("#btn-goto-config", Button).press()
        await _settle(app, pilot)

    assert opened == [("activity", "queue"), ("settings", "")]


@pytest.mark.asyncio
async def test_a_blocked_download_points_at_the_youtube_fix():
    job = download_panel.DownloadJob(1, URL, {}, "Trailer")

    class RowApp(App):
        def compose(self) -> ComposeResult:
            yield DownloadRow(job)

    app = RowApp()
    async with app.run_test():
        row = app.query_one(DownloadRow)
        row.set_failed("HTTP Error 403: Forbidden")
        info = _row_info(row)

    assert "YouTube fix" in info


@pytest.mark.asyncio
async def test_in_the_dashboard_history_never_scrolls_inside_the_page():
    """The app's DataTable rule (height 1fr, min-height 8) made the history a
    tall scroll area inside the scrolling page."""
    from max_cli.interface.tui.app import MaxDashboardApp

    _record_history(20)
    app = MaxDashboardApp()
    async with app.run_test(size=(140, 50)) as pilot:
        app.navigate("download")
        await pilot.pause()
        app.query_one("#dl-tabs", TabbedContent).active = "tab-history"
        await _settle(app, pilot)
        table = app.query_one("#download-history-table", DataTable)
        rows_high, max_scroll = table.outer_size.height, table.max_scroll_y

    assert max_scroll == 0
    assert rows_high == download_panel.HISTORY_PAGE_ROWS + 1  # plus the header
