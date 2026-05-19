from max_cli.core.engines.task_queue import (
    TaskStatus,
    TaskType,
    TaskItem,
    register_executor,
    get_executor,
    list_registered_executors,
)
from max_cli.core.engines.daemon_manager import DaemonManager


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

    def test_list_registered_executors(self):
        result = list_registered_executors()
        assert "custom" in result
        assert isinstance(result["custom"], bool)


class TestDaemonManager:
    def setup_method(self):
        self.dm = DaemonManager()

    def test_add_and_get_all(self):
        task = TaskItem(type=TaskType.CUSTOM, title="Test")
        self.dm.add(task)
        tasks = self.dm.get_all()
        assert len(tasks) >= 1

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
        assert stats["total"] >= 1
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
        assert count >= 1

    def test_get_history_empty(self):
        history = self.dm.get_history()
        assert isinstance(history, list)
