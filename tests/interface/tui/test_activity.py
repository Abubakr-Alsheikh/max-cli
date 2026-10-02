"""The Activity page (widgets/activity_panel.py): Queue, History and Undo tabs."""

from pathlib import Path

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button, Checkbox, DataTable, Input, Static

from max_cli.interface.tui.activity_log import ActivityLog
from max_cli.interface.tui.widgets import history_panel
from max_cli.interface.tui.widgets.activity_panel import ActivityPanel
from max_cli.interface.tui.widgets.dialogs import ConfirmDialog

from .waiting import wait_until

SIZE = (140, 50)


class ActivityApp(App):
    def compose(self) -> ComposeResult:
        yield ActivityPanel(id="activity-panel")


def _rows(app: App, table_id: str) -> int:
    return app.query_one(table_id, DataTable).row_count


def _log(count: int, **kwargs) -> None:
    log = ActivityLog()
    for index in range(count):
        log.add_entry(
            kwargs.get("category", "video"),
            kwargs.get("action", f"compress {index}"),
            status=kwargs.get("status", "success"),
            details={"message": f"Video saved: clip{index}.mp4"},
        )


# --- tabs ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_page_opens_on_the_queue_and_switches_tabs():
    app = ActivityApp()
    async with app.run_test(size=SIZE) as pilot:
        page = app.query_one(ActivityPanel)
        first = page.tab
        page.show_tab("undo")
        await pilot.pause()
        second = page.tab
        page.show_tab("nonsense")
        await pilot.pause()
        third = page.tab

    assert (first, second, third) == ("queue", "undo", "undo")


@pytest.mark.asyncio
async def test_the_queue_tab_has_no_second_page_header():
    app = ActivityApp()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        brand = str(app.query_one("#queue-brand", Static).content)
        header = str(app.query_one("#activity-header", Static).content)

    assert brand == ""
    assert "ACTIVITY" in header


@pytest.mark.asyncio
async def test_queue_history_button_switches_to_the_history_tab():
    from max_cli.interface.tui.app import MaxDashboardApp

    app = MaxDashboardApp()
    async with app.run_test(size=(140, 44)) as pilot:
        app.navigate("activity")
        await pilot.pause()
        app.query_one("#btn-goto-history", Button).press()
        page = app.query_one(ActivityPanel)
        switched = await wait_until(pilot, lambda: page.tab == "history")

    assert switched


# --- history -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_pages_instead_of_scrolling():
    _log(history_panel.HISTORY_PAGE_ROWS + 3)
    app = ActivityApp()
    async with app.run_test(size=SIZE) as pilot:
        app.query_one(ActivityPanel).show_tab("history")
        await wait_until(pilot, lambda: _rows(app, "#history-table") > 0)
        first_page = _rows(app, "#history-table")
        app.query_one("#history-next", Button).press()
        await pilot.pause()
        second_page = _rows(app, "#history-table")
        label = str(app.query_one("#history-page", Static).content)

    assert (first_page, second_page) == (history_panel.HISTORY_PAGE_ROWS, 3)
    assert label == "2 of 2"


@pytest.mark.asyncio
async def test_history_filters_by_kind_search_and_failures():
    _log(2, category="video")
    _log(1, category="pdf", action="merge", status="failed")
    app = ActivityApp()
    async with app.run_test(size=SIZE) as pilot:
        app.query_one(ActivityPanel).show_tab("history")
        await wait_until(pilot, lambda: _rows(app, "#history-table") == 3)
        app.query_one("#history-failed", Checkbox).value = True
        failed_only = await wait_until(pilot, lambda: _rows(app, "#history-table") == 1)
        app.query_one("#history-failed", Checkbox).value = False
        app.query_one("#history-search", Input).value = "clip1"
        # Wait on the detail line: the failed-only view had one row too.
        searched = await wait_until(
            pilot,
            lambda: _rows(app, "#history-table") == 1
            and "clip1.mp4" in str(app.query_one("#history-detail", Static).content),
        )

    assert failed_only and searched


@pytest.mark.asyncio
async def test_history_says_what_to_do_when_empty():
    app = ActivityApp()
    async with app.run_test(size=SIZE) as pilot:
        app.query_one(ActivityPanel).show_tab("history")
        await pilot.pause()
        empty = str(app.query_one("#history-empty", Static).content)

    assert empty.startswith("Nothing yet")


@pytest.mark.asyncio
async def test_clear_history_asks_first():
    _log(2)
    app = ActivityApp()
    async with app.run_test(size=SIZE) as pilot:
        app.query_one(ActivityPanel).show_tab("history")
        await pilot.pause()
        app.query_one("#history-clear", Button).press()
        asked = await wait_until(pilot, lambda: isinstance(app.screen, ConfirmDialog))
        app.screen.query_one("#confirm-yes", Button).press()
        cleared = await wait_until(pilot, lambda: ActivityLog().get_entries() == [])

    assert asked and cleared


# --- undo ------------------------------------------------------------------------------


def _ordered(folder: Path) -> str:
    from max_cli.core.operations import files

    (folder / "alpha.txt").write_text("a", encoding="utf-8")
    result = files.order(folder)
    assert result.undo_group
    return result.undo_group


@pytest.mark.asyncio
async def test_undo_lists_changes_and_puts_files_back(tmp_path):
    _ordered(tmp_path)
    app = ActivityApp()
    async with app.run_test(size=SIZE) as pilot:
        app.query_one(ActivityPanel).show_tab("undo")
        await wait_until(pilot, lambda: _rows(app, "#undo-table") == 1)
        button = app.query_one("#undo-run", Button)
        label = str(button.label)
        button.press()
        await wait_until(pilot, lambda: isinstance(app.screen, ConfirmDialog))
        app.screen.query_one("#confirm-yes", Button).press()
        restored = await wait_until(pilot, lambda: (tmp_path / "alpha.txt").exists())
        done = await wait_until(
            pilot, lambda: app.query_one("#undo-run", Button).disabled
        )

    assert label == "Undo files order"
    assert restored and done


@pytest.mark.asyncio
async def test_undo_with_nothing_recorded_explains_itself():
    app = ActivityApp()
    async with app.run_test(size=SIZE) as pilot:
        app.query_one(ActivityPanel).show_tab("undo")
        await pilot.pause()
        disabled = app.query_one("#undo-run", Button).disabled
        empty_shown = app.query_one("#undo-empty").display

    assert disabled and empty_shown


def test_a_briefly_locked_log_is_read_after_a_retry(monkeypatch):
    """Windows refuses a read while another thread replaces the file."""
    ActivityLog().add_entry("files", "order", "success")
    real_read = Path.read_text
    refusals = iter([True, True])

    def flaky(path, *args, **kwargs):
        if path == ActivityLog.LOG_FILE and next(refusals, False):
            raise PermissionError("locked")
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky)

    assert [entry.action for entry in ActivityLog().get_entries()] == ["order"]


def test_a_log_that_stays_locked_never_overwrites_the_history(monkeypatch):
    ActivityLog().add_entry("files", "order", "success")
    saved = ActivityLog.LOG_FILE.read_text(encoding="utf-8")

    def locked(path, *args, **kwargs):
        raise PermissionError("locked")

    # Only the lock is undone afterwards; the test's own home stays.
    with monkeypatch.context() as lock:
        lock.setattr(Path, "read_text", locked)
        log = ActivityLog()
        log.add_entry("ai", "agent", "success")  # must not raise or write

    assert ActivityLog.LOG_FILE.read_text(encoding="utf-8") == saved
