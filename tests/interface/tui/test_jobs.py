"""Queued work runs inside the dashboard, and the Jobs window shows it.

The maintainer queued a download from the Download page and it stayed
pending: nothing in the dashboard started the queue worker.
"""

import threading
from unittest.mock import patch

import pytest

from max_cli.common.exceptions import OperationCancelled
from max_cli.core.catalog import get_action
from max_cli.core.catalog.runner import enqueue_action
from max_cli.core.engines.task_manager import get_task_manager
from max_cli.core.engines.task_queue import TaskStatus
from max_cli.core.operations.result import ActionResult
from max_cli.interface.tui.app import MaxDashboardApp

DOWNLOAD = "max_cli.core.operations.grab.download"
URL = "https://www.youtube.com/watch?v=abc"
WAIT_SECONDS = 10
POLL_SECONDS = 0.1


async def _wait_for(pilot, condition) -> bool:
    for _ in range(int(WAIT_SECONDS / POLL_SECONDS)):
        if condition():
            return True
        await pilot.pause(POLL_SECONDS)
    return condition()


def _find(task_id: str):
    manager = get_task_manager()
    live = manager.get(task_id)
    if live is not None:
        return live
    return next((item for item in manager.get_history() if item.id == task_id), None)


@pytest.mark.asyncio
async def test_a_queued_download_runs_while_the_dashboard_is_open(tmp_path):
    ok = ActionResult(True, "Downloaded: Trailer", [])
    with patch(DOWNLOAD, return_value=ok) as download:
        task = enqueue_action(
            get_action("grab.download"), {"url": URL, "output": str(tmp_path)}
        )
        app = MaxDashboardApp()
        async with app.run_test(size=(120, 40)) as pilot:
            finished = await _wait_for(
                pilot,
                lambda: getattr(_find(task.id), "status", None) == TaskStatus.COMPLETED,
            )

    assert finished, f"task stayed {_find(task.id)}"
    download.assert_called_once()


@pytest.mark.asyncio
async def test_queued_downloads_report_progress_and_can_be_cancelled(tmp_path):
    started = threading.Event()

    def slow_download(**kwargs):
        kwargs["progress_hook"](
            {
                "status": "downloading",
                "downloaded_bytes": 50,
                "total_bytes": 100,
                "eta": 7,
            }
        )
        started.set()
        while not kwargs["should_cancel"]():
            threading.Event().wait(0.02)
        raise OperationCancelled("Download cancelled")

    # autospec keeps download()'s signature: the executor passes the hooks
    # only to operations whose signature takes them.
    with patch(DOWNLOAD, side_effect=slow_download, autospec=True):
        task = enqueue_action(
            get_action("grab.download"), {"url": URL, "output": str(tmp_path)}
        )
        app = MaxDashboardApp()
        async with app.run_test(size=(120, 40)) as pilot:
            assert await _wait_for(pilot, started.is_set)
            live = get_task_manager().get(task.id)
            assert (live.progress, live.eta) == (50.0, "0:07")

            get_task_manager().cancel(task.id)
            archived = await _wait_for(
                pilot,
                lambda: getattr(_find(task.id), "status", None) == TaskStatus.CANCELLED
                # get() also searches history; the queue itself must be clear.
                and all(item.id != task.id for item in get_task_manager().get_all()),
            )

    assert archived, f"task is {_find(task.id)}"


@pytest.mark.asyncio
async def test_j_opens_and_closes_the_jobs_window():
    from max_cli.interface.tui.widgets.jobs_drawer import JobsDrawer

    app = MaxDashboardApp()
    async with app.run_test(size=(120, 40)) as pilot:
        drawer = app.query_one(JobsDrawer)
        assert not drawer.is_open

        await pilot.press("j")
        await pilot.pause()
        assert drawer.is_open
        assert "Nothing queued" in str(app.query_one("#jobs-list").render())

        await pilot.press("j")
        await pilot.pause()
        assert not drawer.is_open


def test_a_running_job_shows_progress_speed_and_time_left():
    from max_cli.core.engines.task_queue import TaskItem, TaskType
    from max_cli.interface.tui.widgets.jobs_drawer import job_line

    task = TaskItem(
        type=TaskType.ACTION,
        status=TaskStatus.RUNNING,
        title="Lo-fi beats [live]",
        progress=42.0,
        speed="2.10 MB/s",
        eta="0:31",
    )

    line = job_line(task).plain

    assert "42%" in line and "Lo-fi beats [live]" in line
    assert "2.10 MB/s" in line and "0:31 left" in line


@pytest.mark.asyncio
async def test_queueing_from_the_download_page_opens_the_jobs_window(tmp_path):
    from textual.widgets import Button, Input

    from max_cli.interface.tui.widgets.jobs_drawer import JobsDrawer

    release = threading.Event()

    def held_download(**kwargs):
        release.wait(5)
        return ActionResult(True, "Downloaded", [])

    with patch(DOWNLOAD, side_effect=held_download, autospec=True):
        app = MaxDashboardApp()
        async with app.run_test(size=(120, 50)) as pilot:
            app.navigate("download")
            app.query_one("#dl-url", Input).value = URL
            app.query_one("#dl-output", Input).value = str(tmp_path)
            app.query_one("#btn-queue", Button).press()

            assert await _wait_for(pilot, lambda: app.query_one(JobsDrawer).is_open)
            [task] = get_task_manager().get_all() or get_task_manager().get_history()
            assert task.title == URL  # no preview yet, so the link names it
            release.set()


def test_titles_line_up_whatever_the_state():
    from max_cli.core.engines.task_queue import TaskItem, TaskType
    from max_cli.interface.tui.widgets.jobs_drawer import job_line

    columns = {
        job_line(
            TaskItem(type=TaskType.ACTION, status=status, title="TITLE", progress=42)
        ).plain.index("TITLE")
        for status in (
            TaskStatus.RUNNING,
            TaskStatus.PENDING,
            TaskStatus.PAUSED,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        )
    }

    assert len(columns) == 1
