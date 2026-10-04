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
from collections.abc import Iterator
from contextlib import contextmanager

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


def test_only_one_process_runs_the_queue(monkeypatch):
    monkeypatch.setattr(task_manager_module, "WORKER_START_WAIT_SECONDS", 0.2)
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


def test_a_task_that_keeps_killing_its_worker_stops_after_max_retries(monkeypatch):
    """A task that crashes its worker (segfault, out of memory) used to go
    back to pending on every start and block the queue forever."""
    from max_cli.config import settings

    monkeypatch.setattr(settings, "MAX_RETRIES", 1)
    task = TaskManager().add(TaskItem(type=TaskType.CUSTOM, title="poison"))

    TaskManager()._claim(task.id)  # first run: the worker dies
    TaskManager()._recover_orphans()
    assert TaskManager().get_all()[0].status == TaskStatus.PENDING

    TaskManager()._claim(task.id)  # the rerun dies too
    TaskManager()._recover_orphans()

    manager = TaskManager()
    assert manager.get_all() == []
    failed = manager.get_history()[0]
    assert failed.id == task.id
    assert failed.status == TaskStatus.FAILED
    assert "2 times" in failed.error
    assert failed.completed_at is not None


def test_reads_in_this_process_never_wait_for_another_process(monkeypatch):
    """A thread waiting for queue.lock used to hold the manager's own lock,
    so the dashboard's UI thread froze on get_stats() and refresh()."""
    from max_cli.common.file_lock import FileLock

    manager = TaskManager()
    other_process = FileLock(
        TaskManager.QUEUE_DIR / task_manager_module.STORE_LOCK_NAME
    )
    assert other_process.acquire(timeout=0)
    adder = threading.Thread(
        target=manager.add, args=(TaskItem(type=TaskType.CUSTOM),), daemon=True
    )
    try:
        adder.start()
        time.sleep(0.2)  # the adder now waits for queue.lock
        started = time.monotonic()

        assert manager.try_refresh() is False
        assert manager.get_stats()["total"] == 0

        assert time.monotonic() - started < 1
    finally:
        other_process.release()
    adder.join(WAIT_SECONDS)
    assert manager.get_stats()["total"] == 1


def test_try_refresh_reads_the_store_when_it_is_free():
    viewer = TaskManager()
    TaskManager().add(TaskItem(type=TaskType.CUSTOM, title="new"))

    assert viewer.try_refresh() is True
    assert [t.title for t in viewer.get_all()] == ["new"]


class TestUnreadableStore:
    """A refused or corrupt read must never let a save wipe the files."""

    @staticmethod
    @contextmanager
    def _refused(name: str) -> Iterator[None]:
        """Reads of the store file `name` fail, as while a scanner holds it.
        Its own MonkeyPatch: undoing the test's one would also undo the
        fixtures that keep the store out of the real home."""
        path_type = type(TaskManager.QUEUE_FILE)
        real_read = path_type.read_text

        def refused(path, *args, **kwargs):
            if path.name == name:
                raise PermissionError("held by the virus scanner")
            return real_read(path, *args, **kwargs)

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(path_type, "read_text", refused)
            yield

    def test_history_is_not_saved_over_when_it_could_not_be_read(self):
        TaskManager().record(
            TaskItem(type=TaskType.CUSTOM, status=TaskStatus.COMPLETED)
        )
        saved = TaskManager.HISTORY_FILE.read_text(encoding="utf-8")

        with self._refused("history.json"):
            reader = TaskManager()  # its first read failed: no history held
            with pytest.raises(TaskManagerError, match="Could not read"):
                reader.record(
                    TaskItem(type=TaskType.CUSTOM, status=TaskStatus.COMPLETED)
                )

        assert TaskManager.HISTORY_FILE.read_text(encoding="utf-8") == saved

    def test_a_queue_change_still_works_while_history_is_unreadable(self):
        manager = TaskManager()

        with self._refused("history.json"):
            manager.add(TaskItem(type=TaskType.CUSTOM, title="queued"))

        assert [t.title for t in TaskManager().get_all()] == ["queued"]

    def test_queue_is_not_saved_over_when_it_could_not_be_read(self):
        TaskManager().add(TaskItem(type=TaskType.CUSTOM, title="first"))
        saved = TaskManager.QUEUE_FILE.read_text(encoding="utf-8")
        manager = TaskManager()
        manager._queue = []  # as if its first read had failed

        with self._refused("queue.json"):
            with pytest.raises(TaskManagerError, match="Could not read"):
                manager.add(TaskItem(type=TaskType.CUSTOM, title="second"))

        assert TaskManager.QUEUE_FILE.read_text(encoding="utf-8") == saved

    @pytest.mark.parametrize("name", ["queue.json", "history.json"])
    def test_a_corrupt_file_is_moved_aside_not_overwritten(self, name, caplog):
        store = TaskManager.QUEUE_DIR / name
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text("[{not json", encoding="utf-8")

        manager = TaskManager()
        manager.record(TaskItem(type=TaskType.CUSTOM, status=TaskStatus.COMPLETED))

        kept = list(TaskManager.QUEUE_DIR.glob(f"{name}.corrupt-*"))
        assert len(kept) == 1
        assert kept[0].read_text(encoding="utf-8") == "[{not json"
        assert json.loads(store.read_text(encoding="utf-8")) is not None
        assert "corrupt" in caplog.text


def test_add_raises_when_the_queue_cannot_be_saved(monkeypatch):
    """add() used to log the failed save and return, so the CLI said
    "Queued" for a task that was never stored."""
    manager = TaskManager()

    def disk_full(*args, **kwargs):
        raise OSError("No space left on device")

    monkeypatch.setattr(task_manager_module, "atomic_write_json", disk_full)

    with pytest.raises(TaskManagerError, match="save"):
        manager.add(TaskItem(type=TaskType.CUSTOM))


def test_a_starting_worker_waits_out_a_brief_probe(monkeypatch):
    """worker_alive() takes worker.lock for a moment to test it. A worker
    starting in that moment used to give up and leave its tasks pending."""
    from max_cli.common.file_lock import FileLock

    monkeypatch.setattr(task_manager_module, "IDLE_POLL_SECONDS", 0.05)
    ran = []
    _use_executor(monkeypatch, lambda task: ran.append(task.id) or {})
    task = TaskManager().add(TaskItem(type=TaskType.CUSTOM))
    probe = FileLock(TaskManager.QUEUE_DIR / task_manager_module.WORKER_LOCK_NAME)
    assert probe.acquire(timeout=0)
    threading.Timer(0.3, probe.release).start()

    assert TaskManager().run_until_idle(idle_seconds=0.1) == 1

    assert ran == [task.id]
