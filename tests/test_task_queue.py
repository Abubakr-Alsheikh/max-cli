import pytest

from max_cli.core.engines import task_manager as task_manager_module
from max_cli.core.engines.task_queue import (
    EXECUTOR_MODULES,
    TaskStatus,
    TaskType,
    TaskItem,
    register_executor,
    get_executor,
    list_registered_executors,
)
from max_cli.core.engines.task_manager import TaskManager


@pytest.fixture
def isolated_manager(tmp_path, monkeypatch) -> TaskManager:
    """TaskManager whose queue/history live in tmp_path, not ~/.max_cli."""
    queue_dir = tmp_path / "tasks"
    monkeypatch.setattr(TaskManager, "QUEUE_DIR", queue_dir)
    monkeypatch.setattr(TaskManager, "QUEUE_FILE", queue_dir / "queue.json")
    monkeypatch.setattr(TaskManager, "HISTORY_FILE", queue_dir / "history.json")
    return TaskManager()


class TestTaskItem:
    def test_task_creation(self):
        task = TaskItem(
            type=TaskType.VIDEO_COMPRESS,
            title="Test",
            payload={"input_path": "/tmp/test.mp4"},
        )
        assert task.type == TaskType.VIDEO_COMPRESS
        assert task.status == TaskStatus.PENDING
        assert task.id is not None

    def test_task_is_active(self):
        task = TaskItem(type=TaskType.CUSTOM, title="Test")
        assert task.is_active is True
        task.status = TaskStatus.COMPLETED
        assert task.is_active is False

    def test_task_to_dict_and_from_dict(self):
        task = TaskItem(
            type=TaskType.DOWNLOAD,
            title="Download",
            payload={"url": "https://example.com"},
        )
        data = task.to_dict()
        restored = TaskItem.from_dict(data)
        assert restored.type == task.type
        assert restored.title == task.title
        assert restored.payload == task.payload


class TestExecutorRegistry:
    def test_register_and_get_executor(self):
        called = []
        register_executor(TaskType.CUSTOM, lambda t: called.append(t.id))
        executor = get_executor(TaskType.CUSTOM)
        assert executor is not None
        task = TaskItem(type=TaskType.CUSTOM, title="Test")
        executor(task)
        assert len(called) == 1

    def test_get_unknown_executor_returns_none(self):
        assert get_executor(TaskType.AI_BATCH) is None

    @pytest.mark.parametrize("task_type", sorted(EXECUTOR_MODULES, key=str))
    def test_get_executor_loads_engine_on_demand(self, task_type):
        assert get_executor(task_type) is not None

    def test_list_registered_executors(self):
        result = list_registered_executors()
        assert "custom" in result
        assert isinstance(result["custom"], bool)


class TestTaskManager:
    @pytest.fixture(autouse=True)
    def _manager(self, isolated_manager):
        self.dm = isolated_manager

    def test_add_and_get_all(self):
        task = TaskItem(type=TaskType.CUSTOM, title="Test")
        self.dm.add(task)
        tasks = self.dm.get_all()
        assert tasks == [task]

    def test_add_and_remove(self):
        task = TaskItem(type=TaskType.CUSTOM, title="Test")
        self.dm.add(task)
        assert self.dm.remove(task.id) is True
        assert self.dm.get(task.id) is None

    def test_cancel_pending(self):
        task = TaskItem(type=TaskType.CUSTOM, title="Test")
        self.dm.add(task)
        assert self.dm.cancel(task.id) is True
        assert task.status == TaskStatus.CANCELLED

    def test_retry_failed(self):
        task = TaskItem(type=TaskType.CUSTOM, title="Test")
        task.status = TaskStatus.FAILED
        task.error = "Test error"
        self.dm.add(task)
        retried = self.dm.retry(task.id)
        assert retried is not None
        assert retried.status == TaskStatus.PENDING
        assert retried.error == ""

    def test_get_stats(self):
        task = TaskItem(type=TaskType.CUSTOM, title="Test")
        self.dm.add(task)
        stats = self.dm.get_stats()
        assert stats["total"] == 1
        assert "pending" in stats
        assert "by_type" in stats

    def test_pause_and_resume(self):
        task = TaskItem(type=TaskType.CUSTOM, title="Test")
        self.dm.add(task)
        assert self.dm.pause(task.id) is True
        assert task.status == TaskStatus.PAUSED
        assert self.dm.resume(task.id) is True
        assert task.status == TaskStatus.PENDING

    def test_clear_pending(self):
        task = TaskItem(type=TaskType.CUSTOM, title="Test")
        self.dm.add(task)
        count = self.dm.clear(status=TaskStatus.PENDING)
        assert count == 1

    def test_get_history_empty(self):
        assert self.dm.get_history() == []


class TestTaskManagerCancelAndExecution:
    """Regression tests for hardening 1.3 (cancel) and 1.4 (locking, loop errors)."""

    @pytest.fixture(autouse=True)
    def _manager(self, isolated_manager):
        self.dm = isolated_manager

    def _use_executor(self, monkeypatch, executor) -> None:
        monkeypatch.setattr(task_manager_module, "get_executor", lambda task_type: executor)

    def test_cancel_pending_removes_task_from_queue(self):
        task = self.dm.add(TaskItem(type=TaskType.CUSTOM, title="pending"))

        assert self.dm.cancel(task.id) is True

        assert task.status == TaskStatus.CANCELLED
        assert self.dm.get_all() == []

    def test_cancel_paused_removes_task_from_queue(self):
        task = self.dm.add(TaskItem(type=TaskType.CUSTOM, title="paused"))
        self.dm.pause(task.id)

        assert self.dm.cancel(task.id) is True
        assert self.dm.get_all() == []

    def test_cancel_unknown_task_returns_false(self):
        assert self.dm.cancel("missing") is False

    def test_cancelled_running_task_is_not_marked_completed(self, monkeypatch):
        task = self.dm.add(TaskItem(type=TaskType.CUSTOM, title="running"))

        def executor_cancelled_midway(running_task):
            self.dm.cancel(running_task.id)
            return {"output_files": []}

        self._use_executor(monkeypatch, executor_cancelled_midway)
        self.dm.process_now()

        assert task.status == TaskStatus.CANCELLED
        assert self.dm.get_all() == []
        assert self.dm.get_history() == [task]

    def test_cancelled_task_is_not_rerun(self, monkeypatch):
        task = self.dm.add(TaskItem(type=TaskType.CUSTOM, title="skip me"))
        calls = []
        self._use_executor(monkeypatch, lambda t: calls.append(t) or {})
        task.status = TaskStatus.CANCELLED  # cancelled after being picked up

        self.dm._execute_task(task)

        assert calls == []
        assert task.status == TaskStatus.CANCELLED

    def test_queue_saves_happen_under_lock(self, monkeypatch):
        self.dm.add(TaskItem(type=TaskType.CUSTOM, title="locked"))
        self._use_executor(monkeypatch, lambda t: {"output_files": []})
        unlocked_saves = []
        original_save_queue = self.dm._save_queue
        original_save_history = self.dm._save_history

        def checked(original):
            def wrapper():
                if not self.dm._lock.locked():
                    unlocked_saves.append(original.__name__)
                original()

            return wrapper

        monkeypatch.setattr(self.dm, "_save_queue", checked(original_save_queue))
        monkeypatch.setattr(self.dm, "_save_history", checked(original_save_history))

        self.dm.process_now()

        assert unlocked_saves == []

    def test_unexpected_error_marks_task_failed_instead_of_vanishing(self, monkeypatch):
        task = self.dm.add(TaskItem(type=TaskType.CUSTOM, title="boom"))

        def broken_execute(_task):
            raise RuntimeError("disk on fire")

        monkeypatch.setattr(self.dm, "_execute_task", broken_execute)

        assert self.dm._process_next() is True

        assert task.status == TaskStatus.FAILED
        assert "disk on fire" in task.error
        assert self.dm.get_history() == [task]

    def test_process_next_returns_false_when_idle(self):
        assert self.dm._process_next() is False


def test_retry_leaves_a_running_task_alone(isolated_manager):
    """retry used to reset a running task to pending, so it could run twice."""
    task = isolated_manager.add(TaskItem(type=TaskType.CUSTOM, title="busy"))
    task.status = TaskStatus.RUNNING

    assert isolated_manager.retry(task.id) is None
    assert task.status == TaskStatus.RUNNING
