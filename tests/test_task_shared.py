"""The task store shared by several Max processes (task_manager + file_lock).

The dashboard, CLI commands and the background worker each hold their own
TaskManager. These tests use two managers on one store, and real child
processes where the operating system's lock matters.
"""

import json
import subprocess
import sys
import threading
import time

import pytest

from max_cli.core.engines import task_manager as task_manager_module
from max_cli.core.engines.task_manager import TaskManager, TaskManagerError
from max_cli.core.engines.task_queue import TaskItem, TaskStatus, TaskType

WAIT_SECONDS = 10


def _use_executor(monkeypatch, executor) -> None:
    monkeypatch.setattr(task_manager_module, "get_executor", lambda _type: executor)


def _wait_for(condition) -> bool:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_a_task_added_elsewhere_during_a_run_is_kept(monkeypatch):
    """The worker used to save its own copy of the queue when a task ended,
    dropping tasks other processes added meanwhile."""
    worker, cli = TaskManager(), TaskManager()

    def executor(task):
        cli.add(TaskItem(type=TaskType.CUSTOM, title="added meanwhile"))
        return {}

    _use_executor(monkeypatch, executor)
    worker.add(TaskItem(type=TaskType.CUSTOM, title="first"))

    assert worker.process_now(max_tasks=1) == 1

    assert [t.title for t in TaskManager().get_all()] == ["added meanwhile"]


def test_a_cancel_from_another_process_reaches_the_running_task(monkeypatch):
    monkeypatch.setattr(task_manager_module, "PROGRESS_SAVE_SECONDS", 0.05)
    worker, other = TaskManager(), TaskManager()
    started = threading.Event()

    def executor(task):
        started.set()
        assert _wait_for(lambda: task.status == TaskStatus.CANCELLED)
        return {}

    _use_executor(monkeypatch, executor)
    task = worker.add(TaskItem(type=TaskType.CUSTOM, title="long"))
    runner = threading.Thread(target=worker.process_now)
    runner.start()
    assert started.wait(WAIT_SECONDS)
    other.refresh()

    assert other.cancel(task.id) is True

    runner.join(WAIT_SECONDS)
    assert not runner.is_alive()
    assert TaskManager().get_history()[0].status == TaskStatus.CANCELLED


def test_a_running_tasks_progress_reaches_other_processes(monkeypatch):
    monkeypatch.setattr(task_manager_module, "PROGRESS_SAVE_SECONDS", 0.05)
    worker, viewer = TaskManager(), TaskManager()
    seen = threading.Event()

    def executor(task):
        task.progress = 40.0

        def shown() -> bool:
            viewer.refresh()
            return any(t.progress == 40.0 for t in viewer.get_all())

        if _wait_for(shown):
            seen.set()
        return {}

    _use_executor(monkeypatch, executor)
    worker.add(TaskItem(type=TaskType.CUSTOM))
    worker.process_now()

    assert seen.is_set()


def test_only_one_process_runs_the_queue():
    holder, other = TaskManager(), TaskManager()
    assert holder._worker_lock.acquire(timeout=0)
    try:
        assert other.worker_alive()
        with pytest.raises(TaskManagerError, match="Another Max process"):
            other.process_now()
        assert other.run_until_idle(idle_seconds=0) is None
    finally:
        holder._worker_lock.release()
    assert not other.worker_alive()


def test_a_task_left_running_by_a_dead_worker_runs_again(monkeypatch):
    crashed = TaskManager()
    task = crashed.add(TaskItem(type=TaskType.CUSTOM, title="orphan"))
    crashed._claim(task.id)  # then the process died
    ran = []
    _use_executor(monkeypatch, lambda t: ran.append(t.id) or {})

    assert TaskManager().process_now() == 1

    assert ran == [task.id]
    assert TaskManager().get_history()[0].status == TaskStatus.COMPLETED


# Two real worker processes share one store; each logs the tasks it runs.
WORKER_SCRIPT = """
import sys, time
from pathlib import Path
from max_cli.core.engines.task_manager import TaskManager
from max_cli.core.engines import task_queue

queue_dir, log = Path(sys.argv[1]), Path(sys.argv[2])
TaskManager.QUEUE_DIR = queue_dir
TaskManager.QUEUE_FILE = queue_dir / "queue.json"
TaskManager.HISTORY_FILE = queue_dir / "history.json"
TaskManager.LEGACY_DIR = queue_dir.parent

def run(task):
    with log.open("a", encoding="utf-8") as out:
        out.write(task.id + "\\n")
    time.sleep(0.05)
    return {}

task_queue.register_executor(task_queue.TaskType.CUSTOM, run)
TaskManager().run_until_idle(idle_seconds=1)
"""


def test_two_worker_processes_run_each_task_once(tmp_path):
    queue_dir = TaskManager.QUEUE_DIR
    manager = TaskManager()
    tasks = [manager.add(TaskItem(type=TaskType.CUSTOM)) for _ in range(6)]
    log = tmp_path / "ran.txt"
    workers = [
        subprocess.Popen(
            [sys.executable, "-c", WORKER_SCRIPT, str(queue_dir), str(log)],
        )
        for _ in range(2)
    ]
    for worker in workers:
        assert worker.wait(timeout=120) == 0

    ran = log.read_text(encoding="utf-8").split()
    assert sorted(ran) == sorted(task.id for task in tasks)
    history = json.loads((queue_dir / "history.json").read_text(encoding="utf-8"))
    assert {item["status"] for item in history} == {"completed"}
    assert TaskManager().get_all() == []
