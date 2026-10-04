"""core/engines/background_worker.py: the queue runs on after the command."""

import json
import subprocess
import sys
import time

import pytest

from max_cli.core.engines import background_worker
from max_cli.core.engines.task_manager import TaskManager, get_task_manager

# Saved before the autouse fixture swaps it for a recorder.
REAL_SPAWN = background_worker._spawn
WAIT_SECONDS = 90


def test_a_worker_starts_only_when_none_runs(no_background_worker):
    manager = get_task_manager()

    assert background_worker.start_background_worker() is True
    assert manager._worker_lock.acquire(timeout=0)  # now one runs
    try:
        assert background_worker.start_background_worker() is False
    finally:
        manager._worker_lock.release()

    assert len(no_background_worker) == 1


def test_the_detached_worker_runs_a_queued_action(tmp_path, monkeypatch):
    """A real `max queue worker` process, with its home in tmp_path."""
    from max_cli.core.engines.task_queue import TaskItem, TaskType

    home = tmp_path / "home"
    queue_dir = home / ".max_cli" / "tasks"
    for name, value in {
        "QUEUE_DIR": queue_dir,
        "QUEUE_FILE": queue_dir / "queue.json",
        "HISTORY_FILE": queue_dir / "history.json",
        "LEGACY_DIR": home / ".max_cli",
    }.items():
        monkeypatch.setattr(TaskManager, name, value)
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    note = tmp_path / "note.txt"
    note.write_text("hello\n", encoding="utf-8")
    task = TaskManager().add(
        TaskItem(
            type=TaskType.ACTION,
            payload={"action": "files.preview", "args": {"target": str(note)}},
        )
    )

    worker = REAL_SPAWN(queue_dir / "worker.log")
    try:
        history = queue_dir / "history.json"
        deadline = time.monotonic() + WAIT_SECONDS
        finished = []
        while time.monotonic() < deadline and not finished:
            time.sleep(0.2)
            if history.exists():
                finished = [
                    item
                    for item in json.loads(history.read_text(encoding="utf-8"))
                    if item["id"] == task.id
                ]
    finally:
        worker.kill()
        worker.wait(timeout=30)

    log = (queue_dir / "worker.log").read_text(encoding="utf-8", errors="replace")
    assert finished, log
    assert finished[0]["status"] == "completed", log


@pytest.mark.skipif(sys.platform != "win32", reason="Windows creation flags")
def test_the_worker_gets_no_console_window_on_windows():
    """DETACHED_PROCESS left the worker without a console, so every ffmpeg
    or yt-dlp it started opened a window of its own (closing it killed the
    job). CREATE_NO_WINDOW gives the worker a hidden console they share."""
    flags = background_worker._detached()["creationflags"]

    assert flags & subprocess.CREATE_NO_WINDOW
    assert flags & subprocess.CREATE_NEW_PROCESS_GROUP
    assert not flags & subprocess.DETACHED_PROCESS


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX sessions")
def test_the_worker_starts_its_own_session_elsewhere():
    assert background_worker._detached() == {"start_new_session": True}
