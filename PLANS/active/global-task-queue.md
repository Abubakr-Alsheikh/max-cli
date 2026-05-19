# Plan: Global Task Queue (DaemonManager)

> Status: Completed
> Priority: P1
> Related: Architecture & System Design (Feature 2)
> Depends on: Event-Driven Progress System (recommended but not required)

## Overview

Currently, `QueueManager` is tightly coupled to `NetworkEngine` (yt-dlp downloads only). Video compression, AI batch jobs, and other heavy operations block the main thread. This plan generalizes the queue system into a `DaemonManager` that can handle *any* heavy task, enabling true "fire and forget" behavior.

Users will be able to queue any operation:
```bash
max video compress heavy_movie.mp4 --queue
max ai batch-process *.txt --queue
max queue status          # Shows downloads, video compressions, batch renames
max queue cancel <id>
```

## Problem Analysis

### Current QueueManager Limitations

1. **Hardcoded to NetworkEngine**: `QueueManager.__init__()` creates `NetworkEngine()` directly (line 125 of `queue_manager.py`). Cannot queue non-download tasks.

2. **Download-specific QueueItem**: `QueueItem` has fields like `url`, `quality`, `audio_only`, `subtitles`, `playlist_items` — all specific to yt-dlp.

3. **Prints to console**: Uses `console.print()` directly in the Core layer (lines 151, 192, 212, 230, 287, 312, 325, 329) — violates Core/Interface separation.

4. **Single queue file**: Stores only `grab_queue.json`. No separation by task type.

5. **No task type metadata**: Cannot distinguish between a download and a video compression in the queue status.

6. **Daemon thread dies with CLI**: The background worker is a daemon `threading.Thread` — it stops when the CLI process exits. No true background daemon.

### Why This Matters

- Users processing large files want to queue operations and close the terminal.
- Video compression of a 4K movie can take hours — blocking the terminal is unacceptable.
- AI batch jobs on hundreds of files should run asynchronously.
- A unified queue view (`max queue status`) is a powerful UX feature.

---

## Goals

- [ ] Create a generic `TaskItem` model that can represent any type of task
- [ ] Create `DaemonManager` that replaces and generalizes `QueueManager`
- [ ] Support task types: `download`, `video_compress`, `audio_convert`, `ai_batch`, `pdf_merge`, `file_organize`, and custom
- [ ] Add `--queue` flag to heavy commands across all CLI apps
- [ ] Implement `max queue` command group: `status`, `cancel`, `clear`, `retry`, `history`
- [ ] Support true background processing via a persistent daemon process
- [ ] Maintain backward compatibility with existing `QueueManager` usage
- [ ] Add tests for DaemonManager

---

## Implementation Details

### Phase 1: Define Task Schema (`core/engines/task_queue.py`)

Create a new module with generic task models:

```python
# src/max_cli/core/engines/task_queue.py

import json
import threading
import time
import subprocess
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field
from max_cli.config import settings
from max_cli.common.exceptions import MaxError


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class TaskType(str, Enum):
    DOWNLOAD = "download"
    VIDEO_COMPRESS = "video_compress"
    VIDEO_CONVERT = "video_convert"
    VIDEO_TO_AUDIO = "video_to_audio"
    AUDIO_CONVERT = "audio_convert"
    AI_BATCH = "ai_batch"
    PDF_MERGE = "pdf_merge"
    PDF_COMPRESS = "pdf_compress"
    FILE_ORGANIZE = "file_organize"
    FILE_DUPLICATES = "file_duplicates"
    FILE_BACKUP = "file_backup"
    CUSTOM = "custom"


class TaskItem(BaseModel):
    """Generic queue task that can represent any operation."""

    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    title: str = ""
    description: str = ""

    # Generic payload — each task type stores its own args here
    payload: Dict[str, Any] = {}

    # Progress tracking
    progress: float = 0.0
    speed: str = ""
    eta: str = ""

    # Result tracking
    error: str = ""
    result: Dict[str, Any] = {}

    # Timestamps
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    # Retry
    retry_count: int = 0
    max_retries: int = 3

    # Output
    output_path: Optional[str] = None
    output_files: List[str] = []

    @property
    def is_active(self) -> bool:
        return self.status in (TaskStatus.PENDING, TaskStatus.RUNNING)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskItem":
        return cls(**data)
```

**Design decisions:**
- **Pydantic model**: Provides validation, serialization, and IDE autocomplete.
- **`payload` dict**: Flexible container for task-specific arguments. Each task type defines its own schema within this dict.
- **`TaskType` enum**: Enables filtering, type-specific UI rendering, and routing to the correct executor.
- **`status` enum**: More granular than the old string-based status (`pending`, `running`, `completed`, `failed`, `cancelled`, `paused`).

---

### Phase 2: Task Executor Registry

Create a registry that maps `TaskType` to executor functions:

```python
# src/max_cli/core/engines/task_queue.py (continued)

from typing import Callable

TaskExecutor = Callable[[TaskItem], Dict[str, Any]]

_executor_registry: Dict[TaskType, TaskExecutor] = {}
_executor_lock = threading.Lock()


def register_executor(task_type: TaskType, executor: TaskExecutor) -> None:
    """Register an executor function for a task type."""
    with _executor_lock:
        _executor_registry[task_type] = executor


def get_executor(task_type: TaskType) -> Optional[TaskExecutor]:
    """Get the executor function for a task type."""
    with _executor_lock:
        return _executor_registry.get(task_type)


def list_registered_executors() -> Dict[str, bool]:
    """List all registered task types and whether they have executors."""
    with _executor_lock:
        return {t.value: t in _executor_registry for t in TaskType}
```

**Design decisions:**
- **Registry pattern**: Engines register their own executors. `DaemonManager` doesn't need to know about specific engines.
- **Decoupled**: The queue manager only knows about `TaskItem` and executor functions. It doesn't import `MediaEngine`, `AIEngine`, etc.
- **Lazy registration**: Executors are registered when the engine module is loaded, not at startup.

---

### Phase 3: Create DaemonManager

```python
# src/max_cli/core/engines/daemon_manager.py

import json
import threading
import time
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from max_cli.config import settings
from max_cli.common.exceptions import MaxError
from max_cli.common.logger import console  # Only for daemon mode logging
from max_cli.core.engines.task_queue import (
    TaskItem,
    TaskStatus,
    TaskType,
    get_executor,
)


class DaemonError(MaxError):
    """Raised when daemon operations fail."""
    pass


class DaemonManager:
    """
    Manages a global task queue for any type of heavy operation.
    
    Supports:
    - Multiple task types (downloads, video compression, AI batch, etc.)
    - Persistent queue (survives CLI restarts)
    - Background daemon processing
    - Task cancellation, retry, and pause
    """

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

    # --- Queue Operations ---

    def add(self, task: TaskItem) -> TaskItem:
        """Add a task to the queue."""
        with self._lock:
            self._queue.append(task)
            self._save_queue()
        return task

    def remove(self, task_id: str) -> bool:
        """Remove a task from the queue by ID."""
        with self._lock:
            for i, item in enumerate(self._queue):
                if item.id == task_id:
                    if item.status == TaskStatus.RUNNING:
                        return False  # Cannot remove running task
                    self._queue.pop(i)
                    self._save_queue()
                    return True
        return False

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending or running task."""
        with self._lock:
            for item in self._queue:
                if item.id == task_id:
                    if item.status == TaskStatus.RUNNING:
                        item.status = TaskStatus.CANCELLED
                    elif item.status == TaskStatus.PENDING:
                        item.status = TaskStatus.CANCELLED
                        self._queue.remove(item)
                    self._save_queue()
                    return True
        return False

    def pause(self, task_id: str) -> bool:
        """Pause a pending task."""
        with self._lock:
            for item in self._queue:
                if item.id == task_id and item.status == TaskStatus.PENDING:
                    item.status = TaskStatus.PAUSED
                    self._save_queue()
                    return True
        return False

    def resume(self, task_id: str) -> bool:
        """Resume a paused task."""
        with self._lock:
            for item in self._queue:
                if item.id == task_id and item.status == TaskStatus.PAUSED:
                    item.status = TaskStatus.PENDING
                    self._save_queue()
                    return True
        return False

    def retry(self, task_id: str) -> Optional[TaskItem]:
        """Retry a failed task."""
        with self._lock:
            for item in self._queue:
                if item.id == task_id:
                    item.status = TaskStatus.PENDING
                    item.error = ""
                    item.progress = 0.0
                    item.retry_count = 0
                    self._save_queue()
                    return item
            # Check history
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
        """Get a task by ID (queue or history)."""
        with self._lock:
            for item in self._queue:
                if item.id == task_id:
                    return item
            for item in self._history:
                if item.id == task_id:
                    return item
        return None

    def get_all(self, status: Optional[TaskStatus] = None) -> List[TaskItem]:
        """Get all tasks, optionally filtered by status."""
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
        """Clear tasks from the queue. If status is None, clears all."""
        with self._lock:
            if status:
                before = len(self._queue)
                self._queue = [i for i in self._queue if i.status != status]
                count = before - len(self._queue)
            else:
                # Only clear non-running tasks
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
        """Get queue statistics."""
        with self._lock:
            stats = {
                "total": len(self._queue),
                "pending": sum(1 for i in self._queue if i.status == TaskStatus.PENDING),
                "running": sum(1 for i in self._queue if i.status == TaskStatus.RUNNING),
                "paused": sum(1 for i in self._queue if i.status == TaskStatus.PAUSED),
                "completed": sum(1 for i in self._queue if i.status == TaskStatus.COMPLETED),
                "failed": sum(1 for i in self._queue if i.status == TaskStatus.FAILED),
                "cancelled": sum(1 for i in self._queue if i.status == TaskStatus.CANCELLED),
                "by_type": {},
            }
            for item in self._queue:
                t = item.type.value
                stats["by_type"][t] = stats["by_type"].get(t, 0) + 1
        return stats

    # --- Daemon Operations ---

    def start_daemon(self) -> None:
        """Start the background task processor."""
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._process_loop, daemon=True
        )
        self._worker_thread.start()

    def stop_daemon(self) -> None:
        """Stop the background task processor."""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)

    def process_now(self, max_tasks: int = 0) -> int:
        """Process pending tasks synchronously. Returns count processed.
        
        Args:
            max_tasks: Maximum tasks to process (0 = all).
        """
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
        """Background worker loop."""
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
        """Execute a single task using the registered executor."""
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

            # Move to history
            with self._lock:
                if task in self._queue:
                    self._queue.remove(task)
                    self._history.insert(0, task)
                    # Keep only last 200 items in history
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

                # Move to history
                with self._lock:
                    if task in self._queue:
                        self._queue.remove(task)
                        self._history.insert(0, task)
                        if len(self._history) > 200:
                            self._history = self._history[:200]
            self._save_queue()
            self._save_history()
```

**Design decisions:**
- **Separate from QueueManager**: `DaemonManager` is a new class. Old `QueueManager` can be deprecated gradually.
- **Executor registry**: Decouples task execution from queue management. Engines register their own executors.
- **Persistent history**: Completed/failed tasks move to history (max 200 items).
- **Retry with backoff**: Tasks retry up to `max_retries` (default 3) before failing permanently.
- **Pause/resume**: Users can pause pending tasks.

---

### Phase 4: Register Executors in Engines

Each engine registers its executor function when loaded:

```python
# In media_engine.py (at module level or in __init__):

from max_cli.core.engines.task_queue import TaskType, TaskItem, register_executor


def _video_compress_executor(task: TaskItem) -> Dict[str, Any]:
    """Execute a video compression task."""
    from max_cli.core.engines.media_engine import MediaEngine

    engine = MediaEngine()
    payload = task.payload

    input_path = Path(payload["input_path"])
    output_path = Path(payload.get("output_path", input_path.parent / f"{input_path.stem}_compressed.mp4"))

    result = engine.compress_video(
        input_path=input_path,
        output_path=output_path,
        crf=payload.get("crf", 23),
        preset=payload.get("preset", "medium"),
    )

    return {
        "output_path": str(output_path),
        "output_files": [str(output_path)],
        "original_size": result.get("original_size", 0),
        "compressed_size": result.get("compressed_size", 0),
    }


# Register on module load
register_executor(TaskType.VIDEO_COMPRESS, _video_compress_executor)
register_executor(TaskType.VIDEO_CONVERT, _video_convert_executor)
register_executor(TaskType.VIDEO_TO_AUDIO, _video_to_audio_executor)
```

**Design decisions:**
- **Lazy engine import**: The executor imports `MediaEngine` inside the function, not at module level. This avoids loading FFmpeg at startup.
- **Payload-driven**: All task arguments come from `task.payload`. The executor extracts what it needs.
- **Self-contained**: Each executor is a standalone function. No state sharing.

---

### Phase 5: Create `max queue` Command Group

```python
# src/max_cli/interface/cli_queue.py

import typer
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from max_cli.core.engines.daemon_manager import DaemonManager
from max_cli.core.engines.task_queue import TaskStatus, TaskType
from max_cli.common.logger import console

app = typer.Typer(help="Manage background task queue")
daemon = DaemonManager()


@app.command("status")
@app.command("s", hidden=True)
def queue_status():
    """Show current queue status."""
    stats = daemon.get_stats()
    tasks = daemon.get_all()

    if not tasks:
        console.print("[dim]Queue is empty.[/dim]")
        return

    table = Table(
        title=f"Task Queue ({stats['total']} total)",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("ID")
    table.add_column("Type")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Progress")
    table.add_column("Created")

    for task in tasks:
        status_color = {
            TaskStatus.PENDING: "yellow",
            TaskStatus.RUNNING: "blue",
            TaskStatus.COMPLETED: "green",
            TaskStatus.FAILED: "red",
            TaskStatus.CANCELLED: "dim",
            TaskStatus.PAUSED: "cyan",
        }.get(task.status, "white")

        table.add_row(
            task.id,
            task.type.value,
            task.title or task.description[:40],
            f"[{status_color}]{task.status.value}[/{status_color}]",
            f"{task.progress:.0f}%",
            task.created_at[:19],
        )

    console.print(table)

    # Summary
    summary = Text()
    summary.append(f"Pending: {stats['pending']}  ", style="yellow")
    summary.append(f"Running: {stats['running']}  ", style="blue")
    summary.append(f"Failed: {stats['failed']}  ", style="red")
    console.print(summary)


@app.command("history")
@app.command("h", hidden=True)
def queue_history(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of history items"),
    task_type: str = typer.Option(None, "--type", "-t", help="Filter by task type"),
):
    """Show task history."""
    tt = TaskType(task_type) if task_type else None
    history = daemon.get_history(limit=limit, task_type=tt)

    if not history:
        console.print("[dim]No history.[/dim]")
        return

    table = Table(
        title=f"Task History ({len(history)} items)",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("ID")
    table.add_column("Type")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Completed")

    for task in history:
        status_color = "green" if task.status == TaskStatus.COMPLETED else "red"
        table.add_row(
            task.id,
            task.type.value,
            task.title or task.description[:40],
            f"[{status_color}]{task.status.value}[/{status_color}]",
            task.completed_at[:19] if task.completed_at else "N/A",
        )

    console.print(table)


@app.command("cancel")
@app.command("c", hidden=True)
def queue_cancel(
    task_id: str = typer.Argument(..., help="Task ID to cancel"),
):
    """Cancel a queued task."""
    if daemon.cancel(task_id):
        console.print(f"[green]Cancelled task {task_id}[/green]")
    else:
        console.print(f"[red]Task {task_id} not found or is running[/red]")
        raise typer.Exit(1)


@app.command("retry")
@app.command("r", hidden=True)
def queue_retry(
    task_id: str = typer.Argument(..., help="Task ID to retry"),
):
    """Retry a failed task."""
    task = daemon.retry(task_id)
    if task:
        console.print(f"[green]Retrying task {task_id}: {task.title}[/green]")
    else:
        console.print(f"[red]Task {task_id} not found[/red]")
        raise typer.Exit(1)


@app.command("clear")
@app.command("cl", hidden=True)
def queue_clear(
    all_tasks: bool = typer.Option(False, "--all", "-a", help="Clear all tasks"),
    failed_only: bool = typer.Option(False, "--failed", "-f", help="Clear failed tasks only"),
    force: bool = typer.Option(False, "--force", help="Skip confirmation"),
):
    """Clear tasks from the queue."""
    if not force:
        from rich.prompt import Confirm
        if not Confirm.ask("Clear queue?"):
            console.print("[dim]Cancelled.[/dim]")
            return

    if all_tasks:
        count = daemon.clear()
        console.print(f"[green]Cleared {count} tasks[/green]")
    elif failed_only:
        count = daemon.clear(status=TaskStatus.FAILED)
        console.print(f"[green]Cleared {count} failed tasks[/green]")
    else:
        count = daemon.clear(status=TaskStatus.PENDING)
        console.print(f"[green]Cleared {count} pending tasks[/green]")


@app.command("process")
@app.command("p", hidden=True)
def queue_process(
    max_tasks: int = typer.Option(0, "--max", "-n", help="Max tasks to process (0=all)"),
):
    """Process queued tasks now (blocking)."""
    console.print(f"[bold]Processing queue...[/bold]")
    count = daemon.process_now(max_tasks=max_tasks)
    console.print(f"[green]Processed {count} tasks[/green]")


@app.command("stats")
def queue_stats():
    """Show queue statistics."""
    stats = daemon.get_stats()

    panel_lines = []
    panel_lines.append(f"Total in queue:  [bold]{stats['total']}[/bold]")
    panel_lines.append(f"  Pending:       [yellow]{stats['pending']}[/yellow]")
    panel_lines.append(f"  Running:       [blue]{stats['running']}[/blue]")
    panel_lines.append(f"  Paused:        [cyan]{stats['paused']}[/cyan]")
    panel_lines.append(f"  Failed:        [red]{stats['failed']}[/red]")
    panel_lines.append("")
    panel_lines.append("By type:")
    for type_name, count in stats.get("by_type", {}).items():
        panel_lines.append(f"  {type_name}: {count}")

    console.print(Panel("\n".join(panel_lines), title="Queue Statistics"))
```

---

### Phase 6: Add `--queue` Flag to Heavy Commands

Update each heavy command to support `--queue`:

```python
# Example: cli_media.py compress command

@app.command("compress")
def compress_video(
    targets: List[Path] = typer.Argument(...),
    crf: int = typer.Option(23, "--crf", help="Quality (0-51, lower=better)"),
    preset: str = typer.Option("medium", "--preset"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o"),
    queue: bool = typer.Option(False, "--queue", "-q", help="Add to background queue"),
):
    """Compress video files using FFmpeg."""
    from max_cli.core.engines.media_engine import MediaEngine
    from max_cli.core.engines.daemon_manager import DaemonManager
    from max_cli.core.engines.task_queue import TaskItem, TaskType

    if queue:
        daemon = DaemonManager()
        for target in targets:
            task = TaskItem(
                type=TaskType.VIDEO_COMPRESS,
                title=f"Compress {target.name}",
                description=f"CRF={crf}, preset={preset}",
                payload={
                    "input_path": str(target),
                    "output_path": str(output_dir / f"{target.stem}_compressed.mp4") if output_dir else "",
                    "crf": crf,
                    "preset": preset,
                },
            )
            daemon.add(task)
            console.print(f"[green]Queued:[/green] {target.name} (ID: {task.id})")
        console.print("[dim]Run 'max queue status' to monitor.[/dim]")
        return

    # Normal synchronous path
    engine = MediaEngine()
    for target in targets:
        # ... existing compression logic ...
```

**Commands to update:**
1. `cli_media.py`: `compress`, `convert`, `to-audio`, `gif`
2. `cli_network.py`: `download` (migrate from old QueueManager)
3. `cli_ai.py`: `create` (batch mode), batch processing commands
4. `cli_pdf.py`: `merge`, `compress`, `bundle`
5. `cli_files.py`: `smart-sort`, `duplicates`, `backup`

---

### Phase 7: True Background Daemon (Optional, Advanced)

For true "close the terminal and let it run" behavior:

```python
# src/max_cli/core/engines/daemon_process.py

import subprocess
import sys
import os
from pathlib import Path

DAEMON_PID_FILE = Path.home() / ".max_cli" / "tasks" / "daemon.pid"
DAEMON_LOG_FILE = Path.home() / ".max_cli" / "tasks" / "daemon.log"


def start_background_daemon() -> bool:
    """Start a persistent background daemon process.
    
    Uses subprocess to spawn a new Python process that runs the queue processor.
    This survives CLI exit.
    """
    if is_daemon_running():
        return False

    # Spawn a new process
    proc = subprocess.Popen(
        [sys.executable, "-m", "max_cli.core.engines.daemon_worker"],
        stdout=open(DAEMON_LOG_FILE, "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    DAEMON_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    return True


def stop_background_daemon() -> bool:
    """Stop the background daemon process."""
    if not DAEMON_PID_FILE.exists():
        return False

    try:
        pid = int(DAEMON_PID_FILE.read_text(encoding="utf-8"))
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False)
        else:
            os.kill(pid, 15)  # SIGTERM
        DAEMON_PID_FILE.unlink()
        return True
    except (ValueError, FileNotFoundError, ProcessLookupError):
        DAEMON_PID_FILE.unlink(missing_ok=True)
        return False


def is_daemon_running() -> bool:
    """Check if the background daemon is running."""
    if not DAEMON_PID_FILE.exists():
        return False
    try:
        pid = int(DAEMON_PID_FILE.read_text(encoding="utf-8"))
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True,
            )
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)  # Signal 0 checks if process exists
            return True
    except (ValueError, FileNotFoundError, ProcessLookupError, OSError):
        DAEMON_PID_FILE.unlink(missing_ok=True)
        return False
```

**Design decisions:**
- **Cross-platform**: Uses `taskkill` on Windows, `os.kill` on POSIX.
- **PID file**: Tracks the daemon process ID.
- **Log file**: All daemon output goes to a log file.
- **Optional feature**: Only used when user explicitly starts the daemon with `max queue daemon start`.

Add daemon management commands:

```python
@app.command("daemon")
def queue_daemon(
    action: str = typer.Argument("status", help="start, stop, or status"),
):
    """Manage the background daemon process."""
    from max_cli.core.engines.daemon_process import (
        start_background_daemon,
        stop_background_daemon,
        is_daemon_running,
    )

    if action == "start":
        if is_daemon_running():
            console.print("[yellow]Daemon is already running.[/yellow]")
        else:
            start_background_daemon()
            console.print("[green]Daemon started.[/green]")
    elif action == "stop":
        if stop_background_daemon():
            console.print("[green]Daemon stopped.[/green]")
        else:
            console.print("[yellow]Daemon was not running.[/yellow]")
    elif action == "status":
        if is_daemon_running():
            console.print("[green]Daemon is running.[/green]")
        else:
            console.print("[dim]Daemon is not running.[/dim]")
    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        raise typer.Exit(1)
```

---

### Phase 8: Backward Compatibility

Keep `QueueManager` working but mark as deprecated:

```python
# In queue_manager.py, add at the top:
import warnings

warnings.warn(
    "QueueManager is deprecated. Use DaemonManager instead.",
    DeprecationWarning,
    stacklevel=2,
)
```

Or better: wrap `QueueManager` to use `DaemonManager` internally:

```python
# In queue_manager.py (refactored):
class QueueManager:
    """Backward-compatible wrapper around DaemonManager for downloads."""

    def __init__(self):
        self._daemon = DaemonManager()

    def add(self, url, quality, audio_only, ...):
        from max_cli.core.engines.task_queue import TaskItem, TaskType

        task = TaskItem(
            type=TaskType.DOWNLOAD,
            title=url[:50],
            payload={
                "url": url,
                "quality": quality,
                "audio_only": audio_only,
                # ... other params
            },
        )
        return self._daemon.add(task)

    # ... other methods delegate to _daemon ...
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_task_queue.py

def test_task_item_creation():
    task = TaskItem(
        type=TaskType.VIDEO_COMPRESS,
        title="Test",
        payload={"input_path": "/tmp/test.mp4"},
    )
    assert task.type == TaskType.VIDEO_COMPRESS
    assert task.status == TaskStatus.PENDING

def test_executor_registry():
    called = []
    register_executor(TaskType.CUSTOM, lambda t: called.append(t))
    executor = get_executor(TaskType.CUSTOM)
    assert executor is not None
    task = TaskItem(type=TaskType.CUSTOM)
    executor(task)
    assert len(called) == 1

def test_daemon_add_remove():
    daemon = DaemonManager()
    task = TaskItem(type=TaskType.CUSTOM, title="Test")
    daemon.add(task)
    assert len(daemon.get_all()) == 1
    daemon.remove(task.id)
    assert len(daemon.get_all()) == 0

def test_daemon_cancel():
    daemon = DaemonManager()
    task = TaskItem(type=TaskType.CUSTOM, title="Test")
    daemon.add(task)
    assert daemon.cancel(task.id)
    assert task.status == TaskStatus.CANCELLED

def test_daemon_retry():
    daemon = DaemonManager()
    task = TaskItem(type=TaskType.CUSTOM, title="Test")
    task.status = TaskStatus.FAILED
    task.error = "Test error"
    daemon.add(task)
    retried = daemon.retry(task.id)
    assert retried is not None
    assert retried.status == TaskStatus.PENDING
    assert retried.error == ""
```

### Integration Tests

```python
# tests/test_queue_cli.py

def test_queue_status_command():
    runner = CliRunner()
    result = runner.invoke(cli_queue.app, ["status"])
    assert result.exit_code == 0

def test_queue_add_via_flag():
    runner = CliRunner()
    # Test that --queue flag adds to queue instead of running
    result = runner.invoke(cli_media.app, ["compress", "test.mp4", "--queue"])
    assert result.exit_code == 0
    assert "Queued" in result.stdout
```

---

## Migration Path

1. **Step 1**: Create `core/engines/task_queue.py` with `TaskItem`, `TaskType`, `TaskStatus`, and executor registry.
2. **Step 2**: Create `core/engines/daemon_manager.py` with `DaemonManager`.
3. **Step 3**: Create `interface/cli_queue.py` with `max queue` command group.
4. **Step 4**: Register `cli_queue.app` in the command registry.
5. **Step 5**: Add executors to `MediaEngine` module.
6. **Step 6**: Add `--queue` flag to `cli_media.py` compress command (proof of concept).
7. **Step 7**: Add `--queue` flag to remaining heavy commands.
8. **Step 8**: Migrate `QueueManager` to use `DaemonManager` internally.
9. **Step 9**: (Optional) Implement true background daemon process.
10. **Step 10**: Update tests and documentation.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Executor functions import heavy engines at runtime | Executors use lazy imports inside the function body. |
| Queue file corruption on crash | Use atomic writes (write to temp file, then rename). |
| Daemon process orphaned | PID file cleanup on CLI start. `max queue daemon status` checks health. |
| Task payload schema mismatches | Use Pydantic validation in executor functions. Invalid payloads fail fast. |
| Windows subprocess handling | Use `creationflags=subprocess.CREATE_NO_WINDOW` on Windows. |
| Breaking old QueueManager API | Wrap `QueueManager` to delegate to `DaemonManager`. |

---

## Success Criteria

- [ ] `DaemonManager` handles at least 3 different task types
- [ ] `max queue status` shows all queued tasks with Rich formatting
- [ ] `max video compress file.mp4 --queue` adds to queue instead of blocking
- [ ] Old `QueueManager` still works (backward compatibility)
- [ ] All tests pass
- [ ] Background daemon survives CLI exit (if implemented)
