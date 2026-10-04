import json
import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from max_cli.common.atomic import atomic_write_json
from max_cli.common.exceptions import MaxError
from max_cli.common.file_lock import FileLock, is_locked
from max_cli.config import settings
from max_cli.core.engines import task_migration
from max_cli.core.engines.task_queue import (
    TaskItem,
    TaskStatus,
    TaskType,
    get_executor,
)

logger = logging.getLogger(__name__)

HISTORY_LIMIT = 200
IDLE_POLL_SECONDS = 2
BETWEEN_TASKS_SECONDS = 1
WORKER_STOP_TIMEOUT_SECONDS = 5
STORE_LOCK_NAME = "queue.lock"  # held while a process reads, changes, saves
WORKER_LOCK_NAME = "worker.lock"  # held by the one process running tasks
STORE_LOCK_TIMEOUT_SECONDS = 30
UI_REFRESH_TIMEOUT_SECONDS = 0.1  # try_refresh: a screen redraw never waits longer
WORKER_START_WAIT_SECONDS = 2  # outlasts a worker_alive() probe of worker.lock
READ_ATTEMPTS = 3  # Windows refuses a read while another process replaces the file
READ_RETRY_SECONDS = 0.1
CORRUPT_SUFFIX = ".corrupt-"  # queue.json.corrupt-20261004-150531
PROGRESS_SAVE_SECONDS = 2  # a running task's progress reaches the file
WORKER_IDLE_EXIT_SECONDS = 30  # the background worker stops after this
WORKER_BUSY = (
    "Another Max process is running the queue (the dashboard or the "
    "background worker); it will run these tasks."
)
INTERRUPTED_NOTE = "Interrupted: the worker running it stopped. It runs again."
WORKER_DIED_NOTE = (
    "Stopped: the worker died while running it {count} times. "
    "Retry it once you know why."
)
STORE_BUSY = "Another Max process is holding the task queue; try again."
STORE_UNREADABLE = (
    "Could not read the task queue in {folder} (another program may hold "
    "the file); nothing was changed. Try again."
)
STORE_UNSAVED = "Could not save the task queue to {path}: {error}"


class TaskManagerError(MaxError):
    pass


class TaskManager:
    """Persistent task queue and history, shared by every Max process.

    The dashboard, CLI commands and the background worker (`max queue
    worker`) each run in their own process. Every change is one step under
    queue.lock: reload from disk, change, save, so no process saves over
    another's work. A reload updates the task objects this process already
    holds, by id, instead of replacing them.

    Only the process holding worker.lock runs tasks: the dashboard's worker
    thread, `max queue process` or the background worker, whichever got it
    first. While a task runs, its progress is saved every few seconds, and a
    cancel saved by another process reaches it on the next save.
    """

    QUEUE_DIR = Path.home() / ".max_cli" / "tasks"
    QUEUE_FILE = QUEUE_DIR / "queue.json"
    HISTORY_FILE = QUEUE_DIR / "history.json"
    # Folder holding the old grab and download stores (see task_migration).
    LEGACY_DIR = Path.home() / ".max_cli"

    def __init__(self):
        self._queue: list[TaskItem] = []
        self._history: list[TaskItem] = []
        self._lock = threading.Lock()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        # The task this process runs now: a reload keeps this object.
        self._running_task: Optional[TaskItem] = None
        self._worker_lock = FileLock(self.QUEUE_DIR / WORKER_LOCK_NAME)
        self._ensure_dirs()
        self.refresh()
        self._migrate_legacy_stores()

    def _ensure_dirs(self) -> None:
        self.QUEUE_DIR.mkdir(parents=True, exist_ok=True)

    # --- the shared store -----------------------------------------------------

    @contextmanager
    def _locked(self, timeout: Optional[float] = None) -> Iterator[None]:
        """The lock every Max process shares (waiting up to `timeout`, by
        default STORE_LOCK_TIMEOUT_SECONDS), then this process's lock.

        In that order: a thread waiting for another process holds nothing
        here, so get_stats() and try_refresh() on the UI thread never wait
        for that process. (Two threads of one process conflict on the file
        lock too, so they still take turns.)
        """
        store_lock = FileLock(self.QUEUE_DIR / STORE_LOCK_NAME)
        wait = STORE_LOCK_TIMEOUT_SECONDS if timeout is None else timeout
        if not store_lock.acquire(timeout=wait):
            raise TaskManagerError(STORE_BUSY)
        try:
            with self._lock:
                yield
        finally:
            store_lock.release()

    @contextmanager
    def _store(self, history: bool = True) -> Iterator[None]:
        """Read the store, let the caller change it, save it: one step that
        no other process can split. `history` False saves the queue only.

        A file that can't be read raises TaskManagerError before the change:
        saving the lists held in memory would write over tasks on disk.
        """
        with self._locked():
            queue_read, history_read = self._reload()
            if not queue_read or (history and not history_read):
                raise TaskManagerError(STORE_UNREADABLE.format(folder=self.QUEUE_DIR))
            yield
            self._save_queue()
            if history:
                self._save_history()

    def refresh(self) -> None:
        """Reload queue and history from disk to see other processes' changes.

        Raises TaskManagerError when another process holds the store past
        STORE_LOCK_TIMEOUT_SECONDS."""
        with self._locked():
            self._reload()

    def try_refresh(self, timeout: float = UI_REFRESH_TIMEOUT_SECONDS) -> bool:
        """refresh() for screens that redraw on a timer: it waits at most
        `timeout` and never raises. False keeps the lists from last time."""
        try:
            with self._locked(timeout):
                self._reload()
        except TaskManagerError:
            return False
        return True

    def _reload(self) -> tuple[bool, bool]:
        """Take the stores on disk; whether the queue and the history were
        read. Caller holds the locks.

        A task this process already holds keeps its object and takes the
        saved fields; the task running here keeps its own progress and
        takes only a cancel. A read that fails keeps the current lists (see
        _read_tasks).
        """
        queue = self._read_tasks(self.QUEUE_FILE)
        if queue is not None:
            known = {item.id: item for item in self._queue}
            merged = [
                _merge(known.get(item.id), item, self._running_task) for item in queue
            ]
            running = self._running_task
            if running is not None and all(item is not running for item in merged):
                merged.append(running)
            self._queue = merged
        history = self._read_tasks(self.HISTORY_FILE)
        if history is not None:
            self._history = history
        return queue is not None, history is not None

    @staticmethod
    def _read_tasks(path: Path) -> Optional[list[TaskItem]]:
        """The tasks stored in `path`; None when the file can't be read.

        None means "keep what you have": on Windows a read fails while
        another process replaces the file or a scanner holds it, and
        treating that as an empty store wiped the history. A file that
        isn't a task list is moved aside (see _move_aside) and reads as
        empty. A single bad entry is skipped, not the file.
        """
        if not path.exists():
            return []
        text = _read_text(path)
        if text is None:
            logger.warning("Could not read task store %s; keeping current tasks", path)
            return None
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if not isinstance(data, list):
            return [] if _move_aside(path) else None
        tasks = []
        for item in data:
            try:
                tasks.append(TaskItem.from_dict(item))
            except (ValueError, TypeError) as exc:
                logger.warning("Skipping an unreadable task in %s: %s", path, exc)
        return tasks

    def _save_queue(self) -> None:
        self._save(self.QUEUE_FILE, self._queue)

    def _save_history(self) -> None:
        self._save(self.HISTORY_FILE, self._history)

    def _save(self, path: Path, tasks: list[TaskItem]) -> None:
        """Write `tasks` to `path`; TaskManagerError when the disk refuses,
        so add() never reports a task it didn't store."""
        try:
            self._ensure_dirs()
            atomic_write_json(path, [item.to_dict() for item in tasks], default=str)
        except OSError as exc:
            logger.warning("Failed to save task store %s: %s", path, exc)
            raise TaskManagerError(STORE_UNSAVED.format(path=path, error=exc)) from exc

    def _find(self, task_id: str) -> Optional[TaskItem]:
        return next((item for item in self._queue if item.id == task_id), None)

    def _migrate_legacy_stores(self) -> None:
        """Fold the old grab and download history files into this store once."""
        migrated_queue: list[TaskItem] = []
        migrated_history: list[TaskItem] = []
        legacy_files = [
            task_migration.LEGACY_GRAB_QUEUE,
            task_migration.LEGACY_GRAB_HISTORY,
            task_migration.LEGACY_DOWNLOAD_HISTORY,
        ]
        for file_name in legacy_files:
            legacy_file = self.LEGACY_DIR / file_name
            if not legacy_file.exists():
                continue
            try:
                data = json.loads(legacy_file.read_text(encoding="utf-8"))
                if file_name == task_migration.LEGACY_DOWNLOAD_HISTORY:
                    migrated_history.extend(
                        task_migration.convert_download_history(data)
                    )
                else:
                    queued, finished = task_migration.convert_grab_entries(data)
                    migrated_queue.extend(queued)
                    migrated_history.extend(finished)
                legacy_file.replace(
                    legacy_file.with_name(file_name + task_migration.MIGRATED_SUFFIX)
                )
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                logger.warning("Could not migrate %s; left it in place", legacy_file)
        if not migrated_queue and not migrated_history:
            return
        with self._store():
            known_ids = {task.id for task in self._queue + self._history}
            self._queue.extend(t for t in migrated_queue if t.id not in known_ids)
            self._history.extend(t for t in migrated_history if t.id not in known_ids)
            self._history.sort(key=_finished_at, reverse=True)
            del self._history[HISTORY_LIMIT:]

    # --- changes ----------------------------------------------------------------

    def add(self, task: TaskItem) -> TaskItem:
        with self._store(history=False):
            self._queue.append(task)
        return task

    def remove(self, task_id: str) -> bool:
        with self._store(history=False):
            item = self._find(task_id)
            if item is None or item.status == TaskStatus.RUNNING:
                return False
            self._queue.remove(item)
            return True

    def cancel(self, task_id: str) -> bool:
        """Cancel a queued task.

        Pending/paused tasks leave the queue immediately. A running task is
        marked CANCELLED; the process running it sees that on its next save
        and archives it when its executor returns.
        """
        with self._store(history=False):
            item = self._find(task_id)
            if item is None:
                return False
            if item.status == TaskStatus.RUNNING:
                item.status = TaskStatus.CANCELLED
            elif item.status in (TaskStatus.PENDING, TaskStatus.PAUSED):
                item.status = TaskStatus.CANCELLED
                self._queue.remove(item)
            else:
                return False
            return True

    def pause(self, task_id: str) -> bool:
        with self._store(history=False):
            item = self._find(task_id)
            if item is None or item.status != TaskStatus.PENDING:
                return False
            item.status = TaskStatus.PAUSED
            return True

    def resume(self, task_id: str) -> bool:
        with self._store(history=False):
            item = self._find(task_id)
            if item is None or item.status != TaskStatus.PAUSED:
                return False
            item.status = TaskStatus.PENDING
            return True

    def retry(self, task_id: str) -> Optional[TaskItem]:
        """Reset a task to pending. Running tasks are left alone (returns None)."""
        with self._store():
            item = self._find(task_id)
            if item is not None:
                if item.status == TaskStatus.RUNNING:
                    return None
                _reset(item)
                return item
            for item in self._history:
                if item.id == task_id:
                    _reset(item)
                    self._queue.append(item)
                    self._history.remove(item)
                    return item
        return None

    def record(self, task: TaskItem) -> TaskItem:
        """Add a task that already finished outside the queue to history."""
        with self._store():
            if task.completed_at is None:
                task.completed_at = datetime.now().isoformat()
            self._archive(task)
        return task

    def clear(
        self,
        status: Optional[TaskStatus] = None,
        task_type: Optional[TaskType] = None,
    ) -> int:
        """Remove queued tasks with `status` (default: all but running ones)."""

        def removable(item: TaskItem) -> bool:
            if task_type is not None and item.type != task_type:
                return False
            if status:
                return item.status == status
            return item.status != TaskStatus.RUNNING

        with self._store(history=False):
            before = len(self._queue)
            self._queue = [i for i in self._queue if not removable(i)]
            return before - len(self._queue)

    def clear_history(
        self,
        limit: Optional[int] = None,
        task_type: Optional[TaskType] = None,
    ) -> int:
        with self._store():
            count = len(self._history)
            if task_type is not None:
                self._history = [i for i in self._history if i.type != task_type]
                count -= len(self._history)
            elif limit:
                self._history = self._history[:limit]
                count = count - limit
            else:
                self._history = []
            return count

    # --- reading (what this process loaded last; refresh() to update) ----------

    def get(self, task_id: str) -> Optional[TaskItem]:
        with self._lock:
            found = self._find(task_id)
            if found is not None:
                return found
            return next((i for i in self._history if i.id == task_id), None)

    def get_all(self, status: Optional[TaskStatus] = None) -> list[TaskItem]:
        with self._lock:
            items = list(self._queue)
            if status:
                items = [i for i in items if i.status == status]
            return items

    def get_pending(self, task_type: Optional[TaskType] = None) -> list[TaskItem]:
        with self._lock:
            return [
                i
                for i in self._queue
                if i.status == TaskStatus.PENDING
                and (task_type is None or i.type == task_type)
            ]

    def get_history(
        self,
        limit: int = 50,
        task_type: Optional[TaskType] = None,
    ) -> list[TaskItem]:
        with self._lock:
            items = list(self._history)
            if task_type:
                items = [i for i in items if i.type == task_type]
            return items[:limit] if limit > 0 else items

    def get_stats(self, task_type: Optional[TaskType] = None) -> dict[str, Any]:
        with self._lock:
            queue = [i for i in self._queue if task_type is None or i.type == task_type]
            stats: dict[str, Any] = {
                "total": len(queue),
                "pending": sum(1 for i in queue if i.status == TaskStatus.PENDING),
                "running": sum(1 for i in queue if i.status == TaskStatus.RUNNING),
                "paused": sum(1 for i in queue if i.status == TaskStatus.PAUSED),
                "completed": sum(1 for i in queue if i.status == TaskStatus.COMPLETED),
                "failed": sum(1 for i in queue if i.status == TaskStatus.FAILED),
                "cancelled": sum(1 for i in queue if i.status == TaskStatus.CANCELLED),
                "by_type": {},
            }
            for item in queue:
                t = item.type.value
                stats["by_type"][t] = stats["by_type"].get(t, 0) + 1
        return stats

    # --- running tasks ------------------------------------------------------------

    @property
    def is_worker_running(self) -> bool:
        """True while this process runs queued tasks (the dashboard is open)."""
        return self._running

    def worker_alive(self) -> bool:
        """True while some process (this one included) runs the queue."""
        return is_locked(self.QUEUE_DIR / WORKER_LOCK_NAME)

    def start_worker(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._worker_thread.start()

    def stop_worker(self, wait: bool = True) -> None:
        """Stop after the current task. `wait` False returns at once: the
        daemon thread ends with the process, and a running task goes back
        to pending when the next worker starts."""
        self._running = False
        if self._worker_thread and wait:
            self._worker_thread.join(timeout=WORKER_STOP_TIMEOUT_SECONDS)

    def process_now(
        self, max_tasks: int = 0, task_type: Optional[TaskType] = None
    ) -> int:
        """Run pending tasks (optionally of one type) in this thread.

        Raises TaskManagerError when another process runs the queue."""
        took_lock = not self._worker_lock.held
        if not self._worker_lock.acquire(timeout=0):
            raise TaskManagerError(WORKER_BUSY)
        try:
            if took_lock:
                self._recover_orphans()
            processed = 0
            while max_tasks <= 0 or processed < max_tasks:
                if not self._process_next(task_type):
                    break
                processed += 1
            return processed
        finally:
            if took_lock:
                self._worker_lock.release()

    def run_until_idle(
        self, idle_seconds: float = WORKER_IDLE_EXIT_SECONDS
    ) -> Optional[int]:
        """Run queued tasks until none has come for `idle_seconds`; how many
        ran. None when another process already runs the queue.

        Before it stops it lets go of the queue, then looks once more: a
        process that queued a task while this one held the queue saw a
        live worker and started none, so this worker picks the task up.
        """
        processed = 0
        while self._worker_lock.acquire(timeout=WORKER_START_WAIT_SECONDS):
            try:
                self._recover_orphans()
                idle_since = time.monotonic()
                while time.monotonic() - idle_since < idle_seconds:
                    if self._try_next():
                        processed += 1
                        idle_since = time.monotonic()
                    else:
                        time.sleep(IDLE_POLL_SECONDS)
            finally:
                self._worker_lock.release()
            self.try_refresh(STORE_LOCK_TIMEOUT_SECONDS)
            if not self.get_pending():
                return processed
        return processed or None

    def _process_loop(self) -> None:
        while self._running:
            try:
                if not self._worker_lock.held:
                    if not self._worker_lock.acquire(timeout=0):
                        time.sleep(IDLE_POLL_SECONDS)  # another process runs it
                        continue
                    self._recover_orphans()
            except TaskManagerError as exc:
                logger.warning("Task queue unavailable: %s", exc)
                time.sleep(IDLE_POLL_SECONDS)
                continue
            ran = self._try_next()
            time.sleep(BETWEEN_TASKS_SECONDS if ran else IDLE_POLL_SECONDS)
        self._worker_lock.release()

    def _try_next(self) -> bool:
        """_process_next for the worker loops: a store that stays busy or
        unreadable counts as nothing run, so the worker waits and tries
        again instead of dying."""
        try:
            return self._process_next()
        except TaskManagerError as exc:
            logger.warning("Task queue unavailable: %s", exc)
            return False

    def _recover_orphans(self) -> None:
        """Tasks marked running that no worker runs (the one that ran them
        stopped or crashed) go back to pending; cancelled ones are archived.
        Only the worker-lock holder calls this, so nobody else runs them.

        Each claim counts a run in retry_count. A task whose worker died on
        more than 1 + MAX_RETRIES runs fails instead: one that crashes its
        worker would otherwise run on every start and block the queue."""
        with self._store():
            for item in list(self._queue):
                if item is self._running_task:
                    continue
                if item.status == TaskStatus.RUNNING:
                    if item.retry_count > settings.MAX_RETRIES:
                        item.status = TaskStatus.FAILED
                        item.error = WORKER_DIED_NOTE.format(count=item.retry_count)
                        item.completed_at = datetime.now().isoformat()
                        self._archive(item)
                    else:
                        item.status = TaskStatus.PENDING
                        item.error = INTERRUPTED_NOTE
                elif item.status == TaskStatus.CANCELLED:
                    item.completed_at = datetime.now().isoformat()
                    self._archive(item)

    def _process_next(self, task_type: Optional[TaskType] = None) -> bool:
        """Run the oldest pending task. Returns False when nothing ran."""
        self.refresh()
        for task in self.get_pending(task_type):
            try:
                if self._execute_task(task):
                    return True
            except TaskManagerError:
                # The store, not the task, failed: the task keeps its state
                # on disk (a claimed one goes back to pending on recovery).
                raise
            except Exception as exc:  # noqa: BLE001 - worker must survive and record it
                logger.exception("Task %s failed outside its executor", task.id)
                with self._store():
                    failed = self._find(task.id) or task
                    failed.status = TaskStatus.FAILED
                    failed.error = f"Internal error: {exc}"
                    failed.completed_at = datetime.now().isoformat()
                    self._archive(failed)
                return True
        return False

    def _archive(self, task: TaskItem) -> None:
        """Move a finished task from the queue to history. Caller holds the locks."""
        # By id: a reload can hold an equal-looking copy, and == compares
        # every field, so the stale copy stayed queued forever.
        self._queue = [item for item in self._queue if item.id != task.id]
        self._history.insert(0, task)
        del self._history[HISTORY_LIMIT:]

    def _execute_task(self, task: TaskItem) -> bool:
        """Claim `task` and run it; False when it isn't pending any more
        (cancelled, paused, or another worker took it)."""
        claimed = self._claim(task.id)
        if claimed is None:
            return False
        try:
            self._run_task(claimed)
        finally:
            self._running_task = None
        return True

    def _claim(self, task_id: str) -> Optional[TaskItem]:
        """Mark a pending task running, as saved: one step, so two workers
        can never both take it."""
        with self._store(history=False):
            item = self._find(task_id)
            if item is None or item.status != TaskStatus.PENDING:
                return None
            item.status = TaskStatus.RUNNING
            item.started_at = datetime.now().isoformat()
            item.retry_count += 1
            self._running_task = item
            return item

    def _run_task(self, task: TaskItem) -> None:
        executor = get_executor(task.type)
        if executor is None:
            with self._store(history=False):
                task.status = TaskStatus.FAILED
                task.error = f"No executor registered for task type: {task.type.value}"
            return

        stop_watching = threading.Event()
        watcher = threading.Thread(
            target=self._watch, args=(stop_watching,), daemon=True
        )
        watcher.start()
        try:
            result = executor(task)  # long-running: never hold the locks here
        except Exception as e:  # noqa: BLE001 - executor errors become task state
            stop_watching.set()
            watcher.join()
            with self._store():
                if task.status == TaskStatus.CANCELLED:
                    task.completed_at = datetime.now().isoformat()
                    self._archive(task)
                elif task.retry_count <= settings.MAX_RETRIES:
                    task.status = TaskStatus.PENDING
                    task.error = f"Retry {task.retry_count}/{settings.MAX_RETRIES}: {e}"
                else:
                    task.status = TaskStatus.FAILED
                    task.error = str(e)
                    task.completed_at = datetime.now().isoformat()
                    self._archive(task)
            return
        stop_watching.set()
        watcher.join()
        with self._store():
            task.completed_at = datetime.now().isoformat()
            if task.status != TaskStatus.CANCELLED:
                task.status = TaskStatus.COMPLETED
                task.progress = 100.0
                task.result = result
                task.output_files = result.get("output_files", [])
                task.output_path = result.get("output_path")
            self._archive(task)

    def _watch(self, stop: threading.Event) -> None:
        """While a task runs: save its progress for other processes to show,
        and pick up a cancel they saved (the reload takes it)."""
        while not stop.wait(PROGRESS_SAVE_SECONDS):
            try:
                with self._store(history=False):
                    pass
            except TaskManagerError:
                continue  # the store stayed busy; save on the next round


def _merge(
    held: Optional[TaskItem], saved: TaskItem, running: Optional[TaskItem]
) -> TaskItem:
    """The task object to keep for `saved`: the one this process holds,
    updated, or `saved` itself."""
    if held is None:
        return saved
    if held is running:
        if saved.status == TaskStatus.CANCELLED:
            held.status = TaskStatus.CANCELLED
        return held
    for name in TaskItem.model_fields:
        setattr(held, name, getattr(saved, name))
    return held


def _read_text(path: Path) -> Optional[str]:
    """`path`'s text, tried READ_ATTEMPTS times; None when every try fails."""
    for attempt in range(READ_ATTEMPTS):
        if attempt:
            time.sleep(READ_RETRY_SECONDS)
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            continue
    return None


def _move_aside(path: Path) -> bool:
    """Rename a store that isn't a task list to `<name>.corrupt-<time>`, so
    the next save starts afresh without destroying it. False when the
    rename fails: then the caller keeps its tasks and saves nothing."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    kept = path.with_name(f"{path.name}{CORRUPT_SUFFIX}{stamp}")
    try:
        path.replace(kept)
    except OSError as exc:
        logger.warning("Task store %s is corrupt and could not be moved: %s", path, exc)
        return False
    logger.warning("Task store %s was corrupt; moved it to %s", path, kept.name)
    return True


def _reset(item: TaskItem) -> None:
    item.status = TaskStatus.PENDING
    item.error = ""
    item.progress = 0.0
    item.retry_count = 0


def _finished_at(task: TaskItem) -> str:
    return task.completed_at or task.created_at


_shared_manager: Optional[TaskManager] = None
_shared_manager_lock = threading.Lock()


def get_task_manager() -> TaskManager:
    """Return the process-wide TaskManager.

    Share one instance inside a process: two instances each hold their own
    copy of the queue, and the last one to save overwrites the other's work.
    """
    global _shared_manager
    with _shared_manager_lock:
        if _shared_manager is None:
            _shared_manager = TaskManager()
        return _shared_manager


def reset_task_manager() -> None:
    """Forget the shared instance (tests, or after changing the store paths)."""
    global _shared_manager
    with _shared_manager_lock:
        _shared_manager = None
