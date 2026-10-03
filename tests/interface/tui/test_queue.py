"""The Queue page: tiles, running, waiting and finished lists, and their buttons."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button, Static

from max_cli.core.engines.task_manager import get_task_manager
from max_cli.core.engines.task_queue import TaskItem, TaskStatus, TaskType
from max_cli.interface.tui.widgets import queue_panel
from max_cli.interface.tui.widgets.dialogs import ConfirmDialog
from max_cli.interface.tui.widgets.queue_panel import (
    QueuePanel,
    QueueTile,
    TaskRow,
    row_actions,
    task_info,
    task_kind,
)

SIZE = (130, 60)


class QueueApp(App):
    def compose(self) -> ComposeResult:
        yield QueuePanel(id="queue-panel")


def _task(status: TaskStatus, title: str, **fields) -> TaskItem:
    return TaskItem(
        type=TaskType.ACTION,
        status=status,
        title=title,
        payload={"action": "grab.download"},
        **fields,
    )


def _queue(*tasks: TaskItem) -> None:
    for task in tasks:
        get_task_manager().add(task)


def _finish(*tasks: TaskItem) -> None:
    for task in tasks:
        get_task_manager().record(task)


def _titles(app: App, list_id: str) -> list[str]:
    return [
        str(row.query_one(".row-title", Static).content)
        for row in app.query_one(list_id).query(TaskRow)
    ]


def _row(app: App, title: str) -> TaskRow:
    return next(
        row
        for row in app.query(TaskRow)
        if str(row.query_one(".row-title", Static).content) == title
    )


def _press(row: TaskRow, label: str) -> None:
    next(b for b in row.query(Button) if str(b.label) == label).press()


def _tile(app: App, tile_id: str) -> str:
    return app.query_one(f"#{tile_id}", QueueTile)._shown[0]


async def _refresh(app: App, pilot) -> None:
    app.query_one(QueuePanel).refresh_data()
    for _ in range(3):
        await pilot.pause()


# --- helpers ---------------------------------------------------------------


def test_task_kind_names_the_action():
    assert task_kind(_task(TaskStatus.PENDING, "x")) == "grab download"
    assert task_kind(TaskItem(type=TaskType.VIDEO_COMPRESS)) == "video compress"


@pytest.mark.parametrize(
    "status, labels",
    [
        (TaskStatus.RUNNING, ["Cancel"]),
        (TaskStatus.PENDING, ["Pause", "Cancel"]),
        (TaskStatus.PAUSED, ["Resume", "Cancel"]),
        (TaskStatus.FAILED, ["Retry"]),
        (TaskStatus.CANCELLED, ["Retry"]),
        (TaskStatus.COMPLETED, ["Run again"]),
    ],
)
def test_each_state_offers_its_buttons(status, labels):
    assert [label for label, _ in row_actions(_task(status, "x"))] == labels


def test_a_finished_task_with_files_can_open_its_folder():
    task = _task(TaskStatus.COMPLETED, "x", output_files=["a.mp4"])

    assert [label for label, _ in row_actions(task)] == ["Open folder", "Run again"]


def test_task_info_says_what_matters_for_each_state():
    running = _task(TaskStatus.RUNNING, "x", progress=42, speed="2 MB/s", eta="1:05")
    failed = _task(TaskStatus.FAILED, "x", error="HTTP Error 403 [x]")
    done = _task(
        TaskStatus.COMPLETED,
        "x",
        output_files=["a", "b"],
        result={"details": {"size_bytes": 2048}},
    )

    assert task_info(running).plain.startswith("42%  ·  2 MB/s  ·  1:05 left")
    assert task_info(_task(TaskStatus.PENDING, "x"), 3).plain.startswith("#3 in line")
    assert task_info(_task(TaskStatus.PAUSED, "x")).plain.startswith("Paused")
    assert "HTTP Error 403 [x]" in task_info(failed).plain  # plain text, not markup
    assert "2 files  ·  2.00 KB" in task_info(done).plain


# --- the page --------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_empty_queue_says_how_to_fill_it():
    app = QueueApp()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        shown = {
            name: app.query_one(f"#queue-{name}-empty").display
            for name in ("running", "waiting", "finished")
        }
        bar = app.query_one("#queue-next-bar").display
        running = _tile(app, "tile-running")

    assert all(shown.values())
    assert not bar
    assert running == "0"


@pytest.mark.asyncio
async def test_tasks_land_in_their_lists_in_order():
    _queue(
        _task(TaskStatus.RUNNING, "Now", progress=40),
        _task(TaskStatus.PENDING, "First"),
        _task(TaskStatus.PAUSED, "Second"),
    )
    _finish(_task(TaskStatus.COMPLETED, "Old"), _task(TaskStatus.FAILED, "Newer"))
    app = QueueApp()
    async with app.run_test(size=SIZE) as pilot:
        await _refresh(app, pilot)
        running = _titles(app, "#queue-running")
        waiting = _titles(app, "#queue-waiting")
        finished = _titles(app, "#queue-finished")
        second = str(_row(app, "Second").query_one(".row-info", Static).content)
        title = app.query_one("#queue-next").border_title
        tiles = [_tile(app, name) for name in ("tile-running", "tile-waiting")]

    assert running == ["Now"]
    assert waiting == ["First", "Second"]
    assert finished == ["Newer", "Old"]
    assert second.startswith("Paused")
    assert title == "UP NEXT (2)"
    assert tiles == ["1", "2"]


@pytest.mark.asyncio
async def test_progress_updates_the_row_in_place():
    """A 2-second refresh must not rebuild rows: that repaints the page."""
    task = _task(TaskStatus.RUNNING, "Now", progress=10)
    _queue(task)
    app = QueueApp()
    async with app.run_test(size=SIZE) as pilot:
        await _refresh(app, pilot)
        row_before = _row(app, "Now")
        live = get_task_manager().get(task.id)
        live.progress = 55
        get_task_manager()._save_queue()
        await _refresh(app, pilot)
        row_after = _row(app, "Now")
        info = str(row_after.query_one(".row-info", Static).content)

    assert row_after is row_before
    assert info.startswith("55%")


@pytest.mark.asyncio
async def test_nothing_redraws_when_nothing_changed():
    _queue(_task(TaskStatus.PENDING, "Waiting"))
    app = QueueApp()
    async with app.run_test(size=SIZE) as pilot:
        await _refresh(app, pilot)
        row = _row(app, "Waiting")
        with patch.object(Static, "update") as update:
            await _refresh(app, pilot)
        same_row = _row(app, "Waiting") is row

    assert same_row
    update.assert_not_called()


@pytest.mark.asyncio
async def test_pause_resume_and_cancel_a_waiting_task():
    task = _task(TaskStatus.PENDING, "Waiting")
    _queue(task)
    app = QueueApp()
    async with app.run_test(size=SIZE) as pilot:
        await _refresh(app, pilot)
        _press(_row(app, "Waiting"), "Pause")
        await _refresh(app, pilot)
        paused = get_task_manager().get(task.id).status
        _press(_row(app, "Waiting"), "Resume")
        await _refresh(app, pilot)
        resumed = get_task_manager().get(task.id).status
        _press(_row(app, "Waiting"), "Cancel")
        await _refresh(app, pilot)
        left = [t.id for t in get_task_manager().get_all()]
        empty = app.query_one("#queue-waiting-empty").display

    assert (paused, resumed) == (TaskStatus.PAUSED, TaskStatus.PENDING)
    assert task.id not in left
    assert empty


@pytest.mark.asyncio
async def test_retry_puts_a_failed_task_back_in_line():
    failed = _task(TaskStatus.FAILED, "Broken", error="boom")
    _finish(failed)
    app = QueueApp()
    async with app.run_test(size=SIZE) as pilot:
        await _refresh(app, pilot)
        _press(_row(app, "Broken"), "Retry")
        await _refresh(app, pilot)
        waiting = _titles(app, "#queue-waiting")
        finished = _titles(app, "#queue-finished")

    assert waiting == ["Broken"]
    assert finished == []


@pytest.mark.asyncio
async def test_cancel_marks_the_running_task():
    task = _task(TaskStatus.RUNNING, "Now")
    _queue(task)
    app = QueueApp()
    async with app.run_test(size=SIZE) as pilot:
        await _refresh(app, pilot)
        _press(_row(app, "Now"), "Cancel")
        await pilot.pause()

    assert get_task_manager().get(task.id).status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_pause_all_and_resume_all():
    tasks = [_task(TaskStatus.PENDING, f"T{n}") for n in range(3)]
    _queue(*tasks)
    app = QueueApp()
    async with app.run_test(size=SIZE) as pilot:
        await _refresh(app, pilot)
        app.query_one("#btn-pause-all", Button).press()
        await _refresh(app, pilot)
        paused = {t.status for t in get_task_manager().get_all()}
        pause_disabled = app.query_one("#btn-pause-all", Button).disabled
        app.query_one("#btn-resume-all", Button).press()
        await _refresh(app, pilot)
        resumed = {t.status for t in get_task_manager().get_all()}

    assert paused == {TaskStatus.PAUSED} and pause_disabled
    assert resumed == {TaskStatus.PENDING}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer, cleared", [("#confirm-yes", True), ("#confirm-no", False)]
)
async def test_clear_waiting_asks_and_keeps_the_running_task(answer, cleared):
    _queue(
        _task(TaskStatus.RUNNING, "Now"),
        _task(TaskStatus.PENDING, "A"),
        _task(TaskStatus.PAUSED, "B"),
    )
    app = QueueApp()
    async with app.run_test(size=SIZE) as pilot:
        await _refresh(app, pilot)
        app.query_one("#btn-clear-waiting", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmDialog)
        app.screen.query_one(answer, Button).press()
        await _refresh(app, pilot)
        left = sorted(t.title for t in get_task_manager().get_all())

    assert left == (["Now"] if cleared else ["A", "B", "Now"])


@pytest.mark.asyncio
async def test_today_tiles_count_only_today():
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    _finish(
        _task(TaskStatus.COMPLETED, "Old", completed_at=yesterday),
        _task(TaskStatus.COMPLETED, "A"),
        _task(TaskStatus.COMPLETED, "B"),
        _task(TaskStatus.FAILED, "C"),
    )
    app = QueueApp()
    async with app.run_test(size=SIZE) as pilot:
        await _refresh(app, pilot)
        done, failed = _tile(app, "tile-done"), _tile(app, "tile-failed")

    assert (done, failed) == ("2", "1")


@pytest.mark.asyncio
async def test_open_folder_opens_the_first_output_folder(tmp_path):
    _finish(
        _task(
            TaskStatus.COMPLETED, "Done", output_files=[str(tmp_path / "a" / "v.mp4")]
        )
    )
    app = QueueApp()
    with patch("max_cli.common.utils.open_in_file_manager") as opened:
        async with app.run_test(size=SIZE) as pilot:
            await _refresh(app, pilot)
            _press(_row(app, "Done"), "Open folder")
            await pilot.pause()

    opened.assert_called_once_with(Path(tmp_path / "a"))


@pytest.mark.asyncio
async def test_history_button_opens_the_history_tab():
    from max_cli.interface.tui.messages import OpenPage

    opened: list[tuple[str, str]] = []

    class RecordingApp(QueueApp):
        def on_open_page(self, message: OpenPage) -> None:
            opened.append((message.section_id, message.tab))

    app = RecordingApp()
    async with app.run_test(size=SIZE) as pilot:
        app.query_one("#btn-goto-history", Button).press()
        await pilot.pause()

    assert opened == [("activity", "history")]


@pytest.mark.asyncio
async def test_in_the_dashboard_the_queue_light_shows_the_worker():
    from max_cli.interface.tui.app import MaxDashboardApp

    app = MaxDashboardApp()
    async with app.run_test(size=(140, 44)) as pilot:
        app.navigate("activity")
        await pilot.pause()
        light = str(app.query_one("#queue-worker", Static).content)

    assert light == "● RUNNING QUEUE"


@pytest.mark.asyncio
async def test_the_queue_light_shows_a_worker_in_another_process():
    """The page alone runs no worker; the background worker holds the lock."""
    from max_cli.core.engines.task_manager import TaskManager

    background = TaskManager()  # stands in for `max queue worker`
    app = QueueApp()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        stopped = str(app.query_one("#queue-worker", Static).content)
        assert background._worker_lock.acquire(timeout=0)
        try:
            app.query_one(QueuePanel).refresh_data()
            await pilot.pause()
            running = str(app.query_one("#queue-worker", Static).content)
        finally:
            background._worker_lock.release()

    assert stopped == "● QUEUE STOPPED"
    assert running == "● RUNNING QUEUE"


def test_finished_count_is_limited():
    assert queue_panel.FINISHED_SHOWN == 8
