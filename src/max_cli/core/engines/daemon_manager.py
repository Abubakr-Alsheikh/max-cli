import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from max_cli.common.exceptions import MaxError
from max_cli.common.logger import console
from max_cli.core.engines.task_queue import (
    TaskItem,
    TaskStatus,
    TaskType,
    get_executor,
)


class DaemonError(MaxError):
    pass


class DaemonManager:
    QUEUE_DIR = Path.home() / ".max_cli" / "tasks"
    QUEUE_FILE = QUEUE_DIR / "queue.json"
    HISTORY_FILE = QUEUE_DIR / "history.json"
    DAEMON_PID_FILE = QUEUE_DIR / "daemon.pid"
    DAEMON_LOG_FILE = QUEUE_DIR / "daemon.log"

    def __init__(self):
        self._queue: List[TaskItem] = []
        self._history: List[TaskItem] = []
        self._lock = threading.Lock()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._ensure_dirs()
        self._load_queue()
        self._load_history()

    def _ensure_dirs(self) -> None:
        self.QUEUE_DIR.mkdir(parents=True, exist_ok=True)

    def _load_queue(self) -> None:
        if not self.QUEUE_FILE.exists():
            return
        try:
            data = json.loads(self.QUEUE_FILE.read_text(encoding="utf-8"))
            self._queue = [TaskItem.from_dict(item) for item in data]
        except Exception:
            self._queue = []

    def _save_queue(self) -> None:
        self._ensure_dirs()
        try:
            data = [item.to_dict() for item in self._queue]
            self.QUEUE_FILE.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as e:
            console.print(f"[red]Failed to save queue: {e}[/red]")

    def _load_history(self) -> None:
        if not self.HISTORY_FILE.exists():
            return
        try:
            data = json.loads(self.HISTORY_FILE.read_text(encoding="utf-8"))
            self._history = [TaskItem.from_dict(item) for item in data]
        except Exception:
            self._history = []

    def _save_history(self) -> None:
        self._ensure_dirs()
        try:
            data = [item.to_dict() for item in self._history]
            self.HISTORY_FILE.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as e:
            console.print(f"[red]Failed to save history: {e}[/red]")

    def add(self, task: TaskItem) -> TaskItem:
        with self._lock:
            self._queue.append(task)
            self._save_queue()
        return task

    def remove(self, task_id: str) -> bool:
        with self._lock:
            for i, item in enumerate(self._queue):
                if item.id == task_id:
                    if item.status == TaskStatus.RUNNING:
                        return False
                    self._queue.pop(i)
                    self._save_queue()
                    return True
        return False

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            for item in self._queue:
                if item.id == task_id:
                    if item.status in (TaskStatus.RUNNING, TaskStatus.PENDING):
                        item.status = TaskStatus.CANCELLED
                    if item.status == TaskStatus.PENDING:
                        self._queue.remove(item)
                    self._save_queue()
                    return True
        return False

    def pause(self, task_id: str) -> bool:
        with self._lock:
            for item in self._queue:
                if item.id == task_id and item.status == TaskStatus.PENDING:
                    item.status = TaskStatus.PAUSED
                    self._save_queue()
                    return True
        return False

    def resume(self, task_id: str) -> bool:
        with self._lock:
            for item in self._queue:
                if item.id == task_id and item.status == TaskStatus.PAUSED:
                    item.status = TaskStatus.PENDING
                    self._save_queue()
                    return True
        return False

    def retry(self, task_id: str) -> Optional[TaskItem]:
        with self._lock:
            for item in self._queue:
                if item.id == task_id:
                    item.status = TaskStatus.PENDING
                    item.error = ""
                    item.progress = 0.0
                    item.retry_count = 0
                    self._save_queue()
                    return item
            for item in self._history:
                if item.id == task_id:
                    item.status = TaskStatus.PENDING
                    item.error = ""
                    item.progress = 0.0
                    item.retry_count = 0
                    self._queue.append(item)
                    self._history.remove(item)
                    self._save_queue()
                    self._save_history()
                    return item
        return None

    def get(self, task_id: str) -> Optional[TaskItem]:
        with self._lock:
            for item in self._queue:
                if item.id == task_id:
                    return item
            for item in self._history:
                if item.id == task_id:
                    return item
        return None

    def get_all(self, status: Optional[TaskStatus] = None) -> List[TaskItem]:
        with self._lock:
            items = list(self._queue)
            if status:
                items = [i for i in items if i.status == status]
            return items

    def get_pending(self) -> List[TaskItem]:
        with self._lock:
            return [i for i in self._queue if i.status == TaskStatus.PENDING]

    def get_history(
        self,
        limit: int = 50,
        task_type: Optional[TaskType] = None,
    ) -> List[TaskItem]:
        with self._lock:
            items = list(self._history)
            if task_type:
                items = [i for i in items if i.type == task_type]
            return items[:limit]

    def clear(self, status: Optional[TaskStatus] = None) -> int:
        with self._lock:
            if status:
                before = len(self._queue)
                self._queue = [i for i in self._queue if i.status != status]
                count = before - len(self._queue)
            else:
                before = len(self._queue)
                self._queue = [i for i in self._queue if i.status == TaskStatus.RUNNING]
                count = before - len(self._queue)
            self._save_queue()
            return count

    def clear_history(self, limit: Optional[int] = None) -> int:
        with self._lock:
            count = len(self._history)
            if limit:
                self._history = self._history[:limit]
                count = count - limit
            else:
                self._history = []
            self._save_history()
            return count

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            stats = {
                "total": len(self._queue),
                "pending": sum(
                    1 for i in self._queue if i.status == TaskStatus.PENDING
                ),
                "running": sum(
                    1 for i in self._queue if i.status == TaskStatus.RUNNING
                ),
                "paused": sum(1 for i in self._queue if i.status == TaskStatus.PAUSED),
                "completed": sum(
                    1 for i in self._queue if i.status == TaskStatus.COMPLETED
                ),
                "failed": sum(1 for i in self._queue if i.status == TaskStatus.FAILED),
                "cancelled": sum(
                    1 for i in self._queue if i.status == TaskStatus.CANCELLED
                ),
                "by_type": {},
            }
            for item in self._queue:
                t = item.type.value
                stats["by_type"][t] = stats["by_type"].get(t, 0) + 1
        return stats

    def start_daemon(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._worker_thread.start()

    def stop_daemon(self) -> None:
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)

    def process_now(self, max_tasks: int = 0) -> int:
        processed = 0
        while True:
            pending = self.get_pending()
            if not pending:
                break
            if max_tasks > 0 and processed >= max_tasks:
                break

            item = pending[0]
            try:
                self._execute_task(item)
                processed += 1
            except Exception as e:
                console.print(f"[red]Error processing task {item.id}: {e}[/red]")
                break

        return processed

    def _process_loop(self) -> None:
        while self._running:
            pending = self.get_pending()
            if not pending:
                time.sleep(2)
                continue

            item = pending[0]
            try:
                self._execute_task(item)
            except Exception:
                pass

            time.sleep(1)

    def _execute_task(self, task: TaskItem) -> None:
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now().isoformat()
        task.retry_count += 1
        self._save_queue()

        executor = get_executor(task.type)
        if executor is None:
            task.status = TaskStatus.FAILED
            task.error = f"No executor registered for task type: {task.type.value}"
            self._save_queue()
            return

        try:
            result = executor(task)
            task.status = TaskStatus.COMPLETED
            task.progress = 100.0
            task.completed_at = datetime.now().isoformat()
            task.result = result
            task.output_files = result.get("output_files", [])
            task.output_path = result.get("output_path")

            with self._lock:
                if task in self._queue:
                    self._queue.remove(task)
                    self._history.insert(0, task)
                    if len(self._history) > 200:
                        self._history = self._history[:200]
            self._save_queue()
            self._save_history()

        except Exception as e:
            if task.retry_count < task.max_retries:
                task.status = TaskStatus.PENDING
                task.error = f"Retry {task.retry_count}/{task.max_retries}: {e}"
            else:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.completed_at = datetime.now().isoformat()

                with self._lock:
                    if task in self._queue:
                        self._queue.remove(task)
                        self._history.insert(0, task)
                        if len(self._history) > 200:
                            self._history = self._history[:200]
            self._save_queue()
            self._save_history()
