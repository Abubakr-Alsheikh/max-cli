# Plan: Unified Event-Driven Progress System

> Status: Completed
> Priority: P1
> Related: Architecture & System Design (Feature 1)

## Overview

Currently, Rich UI elements (`Progress`, `TaskID`, callback functions) are passed from the `interface/` layer down into `common/concurrent.py` utility functions. This couples the Core/Common layer to Rich CLI specifics, violating the strict Core/Interface separation.

This plan introduces an **Event Emitter pattern** using Python's `queue.Queue` where Core Engines emit standardized dictionary events, and the Interface layer subscribes and translates them into Rich UI updates.

## Problem Analysis

### Current Coupling Points

1. **`common/concurrent.py`** — `process_batch_parallel()` accepts `Optional[Progress]` and `Optional[TaskID]` parameters (lines 14-15). It imports `from rich.progress import Progress, TaskID` at module level (line 4).

2. **`cli_images.py`** — Creates Rich `Progress` bar, passes `progress` and `task_id` into `process_batch_parallel()`.

3. **`cli_network.py`** — Creates Rich `Progress` bar, defines a `rich_hook()` callback that updates Rich UI, passes it as `progress_hook` to `NetworkEngine.download_media()`.

4. **`cli_pdf.py`** — Creates Rich `Progress` bar, manually loops and calls `progress.advance(task_id)`.

5. **`cli_media.py`** — Uses `console.status()` spinner for long-running operations.

### Why This Matters

- **Core is not pure**: `common/concurrent.py` imports Rich types. If you ever build a Web UI, REST API, or GUI, you must untangle Rich from the batch processor.
- **Tight coupling**: Every engine that wants to report progress must accept a UI-specific callback or progress object.
- **Inconsistent patterns**: Four different progress patterns exist across the codebase (A, B, C, D patterns).

---

## Goals

- [ ] Remove all Rich imports from `common/concurrent.py`
- [ ] Create a universal `EventEmitter` class in `common/`
- [ ] Define a standardized event schema (typed dicts/Pydantic models)
- [ ] Refactor `process_batch_parallel` to emit events instead of accepting Rich objects
- [ ] Refactor engines to emit progress events (MediaEngine, ImageEngine, PDFEngine, NetworkEngine)
- [ ] Create an `EventSubscriber` utility in `interface/` that listens to events and updates Rich UI
- [ ] Maintain backward compatibility — existing commands should not break
- [ ] Add tests for EventEmitter and EventSubscriber

---

## Implementation Details

### Phase 1: Define Event Schema (`common/events.py`)

Create a new module defining all event types with Pydantic models for type safety:

```python
# src/max_cli/common/events.py

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class EventType(str, Enum):
    PROGRESS = "progress"          # File-level progress update
    BATCH_PROGRESS = "batch_progress"  # Overall batch progress
    FILE_START = "file_start"      # Started processing a file
    FILE_COMPLETE = "file_complete"  # Finished processing a file
    FILE_ERROR = "file_error"      # File processing failed
    STATUS = "status"              # General status message (e.g., "Compressing...")
    LOG = "log"                    # Log message (info, warning, error)
    COMPLETE = "complete"          # Entire operation finished


class EventLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


class BaseEvent(BaseModel):
    type: EventType
    timestamp: datetime = Field(default_factory=datetime.now)
    source: str = ""  # e.g., "ImageEngine", "MediaEngine"


class ProgressEvent(BaseEvent):
    type: EventType = EventType.PROGRESS
    file: str = ""
    current: int = 0
    total: int = 100
    percentage: float = 0.0
    speed: str = ""
    eta: str = ""
    extra: dict[str, Any] = {}


class BatchProgressEvent(BaseEvent):
    type: EventType = EventType.BATCH_PROGRESS
    current: int = 0
    total: int = 0
    percentage: float = 0.0
    description: str = ""


class FileStartEvent(BaseEvent):
    type: EventType = EventType.FILE_START
    file: str = ""
    action: str = ""  # e.g., "compress", "resize"


class FileCompleteEvent(BaseEvent):
    type: EventType = EventType.FILE_COMPLETE
    file: str = ""
    result: dict[str, Any] = {}


class FileErrorEvent(BaseEvent):
    type: EventType = EventType.FILE_ERROR
    file: str = ""
    error: str = ""
    level: EventLevel = EventLevel.ERROR


class StatusEvent(BaseEvent):
    type: EventType = EventType.STATUS
    message: str = ""
    level: EventLevel = EventLevel.INFO


class LogEvent(BaseEvent):
    type: EventType = EventType.LOG
    message: str = ""
    level: EventLevel = EventLevel.INFO


class CompleteEvent(BaseEvent):
    type: EventType = EventType.COMPLETE
    summary: dict[str, Any] = {}


# Union type for all events
MaxEvent = (
    ProgressEvent
    | BatchProgressEvent
    | FileStartEvent
    | FileCompleteEvent
    | FileErrorEvent
    | StatusEvent
    | LogEvent
    | CompleteEvent
)
```

**Design decisions:**
- **Pydantic models**: Provides validation, serialization (for future daemon/IPC), and IDE autocomplete.
- **Enum types**: Prevents typos in event type strings.
- **`source` field**: Identifies which engine emitted the event (useful for debugging and multi-engine operations).
- **`extra` dict**: Escape hatch for engine-specific data without changing the schema.

---

### Phase 2: Create EventEmitter (`common/events.py` — continued)

Add the emitter class to the same module:

```python
import threading
import queue
from typing import Callable, Optional
from collections.abc import Generator


class EventEmitter:
    """Thread-safe event emitter for core engines.
    
    Engines emit events; interface layers subscribe and render UI.
    Supports both callback-based and queue-based consumption.
    """

    def __init__(self):
        self._subscribers: list[Callable[[MaxEvent], None]] = []
        self._lock = threading.Lock()
        self._queue: queue.Queue[MaxEvent] = queue.Queue()

    def subscribe(self, callback: Callable[[MaxEvent], None]) -> None:
        """Register a callback to receive all events."""
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[MaxEvent], None]) -> None:
        """Remove a previously registered callback."""
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def emit(self, event: MaxEvent) -> None:
        """Emit an event to all subscribers and push to the queue."""
        with self._lock:
            for cb in self._subscribers:
                try:
                    cb(event)
                except Exception:
                    pass  # Subscriber errors should not crash the engine
        self._queue.put(event)

    def get_queue(self) -> queue.Queue[MaxEvent]:
        """Get the internal queue for polling-based consumption."""
        return self._queue

    def event_generator(self) -> Generator[MaxEvent, None, None]:
        """Yield events as they arrive (blocks until event or sentinel)."""
        while True:
            event = self._queue.get()
            if event.type == EventType.COMPLETE:
                yield event
                break
            yield event

    def clear(self) -> None:
        """Remove all subscribers and drain the queue."""
        with self._lock:
            self._subscribers.clear()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break


# Singleton accessor
_default_emitter: Optional[EventEmitter] = None
_emitter_lock = threading.Lock()


def get_emitter() -> EventEmitter:
    """Get the default global event emitter."""
    global _default_emitter
    with _emitter_lock:
        if _default_emitter is None:
            _default_emitter = EventEmitter()
        return _default_emitter


def reset_emitter() -> None:
    """Reset the global emitter (useful for testing)."""
    global _default_emitter
    with _emitter_lock:
        if _default_emitter is not None:
            _default_emitter.clear()
            _default_emitter = None
```

**Design decisions:**
- **Dual-mode**: Supports both callback-based (push) and queue-based (pull) consumption. Callbacks for synchronous CLI, queues for future daemon/IPC.
- **Thread-safe**: Uses `threading.Lock` for subscriber list mutations.
- **Sentinel pattern**: `CompleteEvent` acts as a sentinel to stop the generator loop.
- **Subscriber error isolation**: A broken subscriber callback won't crash the engine.

---

### Phase 3: Refactor `common/concurrent.py`

Remove Rich dependency and use events:

```python
# src/max_cli/common/concurrent.py

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, TypeVar

from max_cli.common.events import (
    EventEmitter,
    BatchProgressEvent,
    FileStartEvent,
    FileCompleteEvent,
    FileErrorEvent,
    CompleteEvent,
)

T = TypeVar("T")
R = TypeVar("R")


def process_batch_parallel(
    items: List[T],
    processor: Callable[[T], R],
    max_workers: int = 4,
    emitter: Optional[EventEmitter] = None,
    action: str = "Processing",
) -> List[Dict[str, Any]]:
    """Process items in parallel with optional event emission.

    Args:
        items: List of items to process
        processor: Function to apply to each item
        max_workers: Maximum number of parallel workers
        emitter: Optional EventEmitter for progress tracking
        action: Description of the action (used in event descriptions)

    Returns:
        List of results, including errors for failed items
    """
    results: List[Dict[str, Any]] = []
    total = len(items)
    processed_count = 0
    count_lock = threading.Lock()

    def _emit_progress():
        if emitter:
            with count_lock:
                current = processed_count
            emitter.emit(
                BatchProgressEvent(
                    current=current,
                    total=total,
                    percentage=(current / total * 100) if total > 0 else 0,
                    description=f"{action}...",
                )
            )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(processor, item): item for item in items}

        for future in as_completed(futures):
            item = futures[future]
            item_name = str(item) if hasattr(item, "__str__") else repr(item)

            if emitter:
                emitter.emit(FileStartEvent(file=item_name, action=action))

            try:
                result = future.result()
                if isinstance(result, dict):
                    results.append(result)
                else:
                    results.append({"result": result, "item": item})

                if emitter:
                    emitter.emit(FileCompleteEvent(file=item_name, result=result))
            except Exception as e:
                error_msg = str(e)
                results.append({"error": error_msg, "item": item, "success": False})

                if emitter:
                    emitter.emit(FileErrorEvent(file=item_name, error=error_msg))

            with count_lock:
                processed_count += 1
            _emit_progress()

    if emitter:
        emitter.emit(
            CompleteEvent(
                summary={
                    "total": total,
                    "successful": sum(1 for r in results if "error" not in r),
                    "failed": sum(1 for r in results if "error" in r),
                }
            )
        )

    return results


def process_batch_sequential(
    items: List[T],
    processor: Callable[[T], R],
    emitter: Optional[EventEmitter] = None,
    action: str = "Processing",
) -> List[Dict[str, Any]]:
    """Process items sequentially with optional event emission."""
    results: List[Dict[str, Any]] = []
    total = len(items)

    for i, item in enumerate(items):
        item_name = str(item) if hasattr(item, "__str__") else repr(item)

        if emitter:
            emitter.emit(FileStartEvent(file=item_name, action=action))

        try:
            result = processor(item)
            if isinstance(result, dict):
                results.append(result)
            else:
                results.append({"result": result, "item": item})

            if emitter:
                emitter.emit(FileCompleteEvent(file=item_name, result=result))
        except Exception as e:
            error_msg = str(e)
            results.append({"error": error_msg, "item": item, "success": False})

            if emitter:
                emitter.emit(FileErrorEvent(file=item_name, error=error_msg))

        if emitter:
            emitter.emit(
                BatchProgressEvent(
                    current=i + 1,
                    total=total,
                    percentage=((i + 1) / total * 100) if total > 0 else 0,
                    description=f"{action}...",
                )
            )

    if emitter:
        emitter.emit(
            CompleteEvent(
                summary={
                    "total": total,
                    "successful": sum(1 for r in results if "error" not in r),
                    "failed": sum(1 for r in results if "error" in r),
                }
            )
        )

    return results
```

**Key changes:**
- **No Rich imports**: `concurrent.py` is now 100% pure Python.
- **`emitter` parameter**: Replaces `progress` + `task_id`. Optional, so existing code that doesn't pass it still works (just no events).
- **Thread-safe counting**: Uses a lock for the shared counter in parallel mode.
- **Richer events**: Emits `FileStartEvent`, `FileCompleteEvent`, `FileErrorEvent`, and `CompleteEvent` for granular UI updates.

---

### Phase 4: Create EventSubscriber for Interface (`interface/event_subscriber.py`)

Create a utility that listens to events and drives Rich UI:

```python
# src/max_cli/interface/event_subscriber.py

from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TaskID,
)
from max_cli.common.events import (
    EventEmitter,
    EventType,
    MaxEvent,
    ProgressEvent,
    BatchProgressEvent,
    FileStartEvent,
    FileCompleteEvent,
    FileErrorEvent,
    StatusEvent,
    LogEvent,
    CompleteEvent,
)
from max_cli.common.logger import console


class EventSubscriber:
    """Subscribes to engine events and updates Rich UI."""

    def __init__(self, emitter: EventEmitter):
        self._emitter = emitter
        self._progress: Optional[Progress] = None
        self._batch_task: Optional[TaskID] = None
        self._file_tasks: dict[str, TaskID] = {}
        self._stats: dict[str, int] = {"success": 0, "failed": 0, "total": 0}

    def _handle_event(self, event: MaxEvent) -> None:
        if event.type == EventType.BATCH_PROGRESS:
            self._on_batch_progress(event)
        elif event.type == EventType.FILE_START:
            self._on_file_start(event)
        elif event.type == EventType.FILE_COMPLETE:
            self._on_file_complete(event)
        elif event.type == EventType.FILE_ERROR:
            self._on_file_error(event)
        elif event.type == EventType.STATUS:
            self._on_status(event)
        elif event.type == EventType.PROGRESS:
            self._on_progress(event)
        elif event.type == EventType.COMPLETE:
            self._on_complete(event)

    def _on_batch_progress(self, event: BatchProgressEvent) -> None:
        if self._progress and self._batch_task:
            self._progress.update(
                self._batch_task,
                completed=event.current,
                description=f"[green]{event.description}[/green] ({event.current}/{event.total})",
            )

    def _on_file_start(self, event: FileStartEvent) -> None:
        if self._progress:
            task_id = self._progress.add_task(
                f"[cyan]{event.action}[/cyan] {event.file}",
                total=1,
            )
            self._file_tasks[event.file] = task_id

    def _on_file_complete(self, event: FileCompleteEvent) -> None:
        self._stats["success"] += 1
        if event.file in self._file_tasks:
            task_id = self._file_tasks.pop(event.file)
            if self._progress:
                self._progress.update(task_id, completed=1)

    def _on_file_error(self, event: FileErrorEvent) -> None:
        self._stats["failed"] += 1
        if event.file in self._file_tasks:
            task_id = self._file_tasks.pop(event.file)
            if self._progress:
                self._progress.update(
                    task_id,
                    description=f"[red]✗ {event.file}: {event.error}[/red]",
                )

    def _on_status(self, event: StatusEvent) -> None:
        console.print(f"[dim]{event.message}[/dim]")

    def _on_progress(self, event: ProgressEvent) -> None:
        if self._progress and event.file in self._file_tasks:
            task_id = self._file_tasks[event.file]
            self._progress.update(
                task_id,
                completed=event.percentage / 100,
                description=f"[cyan]{event.file}[/cyan] {event.percentage:.1f}%",
            )

    def _on_complete(self, event: CompleteEvent) -> None:
        summary = event.summary
        console.print(
            f"[green]Done:[/green] {summary.get('successful', 0)} succeeded, "
            f"[red]{summary.get('failed', 0)} failed[/red] "
            f"out of {summary.get('total', 0)} total"
        )

    def subscribe(self) -> None:
        """Start listening to events."""
        self._emitter.subscribe(self._handle_event)

    def unsubscribe(self) -> None:
        """Stop listening to events."""
        self._emitter.unsubscribe(self._handle_event)

    def create_progress_context(self, total: int, description: str = "Processing..."):
        """Create a Rich Progress context and return it for use in a `with` block."""
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            transient=True,
        )
        self._batch_task = self._progress.add_task(description, total=total)
        return self._progress
```

**Design decisions:**
- **Single responsibility**: Only handles Rich UI updates. No business logic.
- **Per-file tasks**: Creates individual task bars for each file, plus a batch-level progress bar.
- **Stats tracking**: Accumulates success/failure counts for final summary.
- **Context manager pattern**: `create_progress_context()` returns a Rich `Progress` that can be used with `with`.

---

### Phase 5: Refactor Interface Commands

Update each CLI file to use the new event system. Example for `cli_images.py`:

**Files updated:**
1. `interface/cli_images.py` — DONE (compress, resize, convert, strip)
2. `interface/cli_pdf.py` — DONE (compress)
3. `interface/cli_network.py` — DONE (download)
4. `interface/cli_files.py` — No changes needed (no batch progress coupling)
5. `interface/cli_media.py` — No changes needed (console.status only, no Progress bars)
6. `interface/cli_audio.py` — No changes needed (console.status only, no Progress bars)

```python
# Before (current):
with Progress(...) as progress:
    task = progress.add_task("...", total=len(files))
    results = process_batch_parallel(
        files, process_file, max_workers=workers, progress=progress, task_id=task
    )

# After (new):
from max_cli.common.events import get_emitter
from max_cli.interface.event_subscriber import EventSubscriber

emitter = get_emitter()
subscriber = EventSubscriber(emitter)
subscriber.subscribe()

with subscriber.create_progress_context(len(files), "Compressing images..."):
    results = process_batch_parallel(
        files, process_file, max_workers=workers, emitter=emitter, action="Compressing"
    )

subscriber.unsubscribe()
```

**Files to update:**
1. `interface/cli_images.py` — `compress`, `resize`, `convert`, `strip`
2. `interface/cli_files.py` — `smart-sort`, `duplicates`, `shred`, `backup`
3. `interface/cli_pdf.py` — `merge`, `compress`, `bundle`, `split`
4. `interface/cli_media.py` — batch commands like `concat`
5. `interface/cli_network.py` — Replace `rich_hook` pattern with event subscription

---

### Phase 6: Refactor Engines to Emit Events

#### MediaEngine Example

```python
# In media_engine.py compress_video():
def compress_video(self, ..., emitter: Optional[EventEmitter] = None):
    if emitter:
        emitter.emit(StatusEvent(message=f"Compressing {input_path.name}..."))
    
    # ... existing ffmpeg logic ...
    
    if emitter:
        emitter.emit(FileCompleteEvent(file=str(input_path), result={"size": output_size}))
```

#### NetworkEngine Example

Replace the `progress_hook` callback pattern:

```python
# In network_engine.py download_media():
def download_media(self, ..., emitter: Optional[EventEmitter] = None):
    def _yt_dlp_hook(d):
        if d["status"] == "downloading" and emitter:
            pct = (d.get("downloaded_bytes", 0) / d.get("total_bytes", 1)) * 100
            emitter.emit(
                ProgressEvent(
                    file=url,
                    percentage=pct,
                    speed=str(d.get("speed", "")),
                )
            )
    
    # Pass _yt_dlp_hook to yt_dlp
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_events.py

def test_emitter_emit_and_subscribe():
    emitter = EventEmitter()
    received = []
    emitter.subscribe(lambda e: received.append(e))
    emitter.emit(StatusEvent(message="test"))
    assert len(received) == 1
    assert received[0].message == "test"

def test_emitter_queue_mode():
    emitter = EventEmitter()
    emitter.emit(StatusEvent(message="hello"))
    emitter.emit(CompleteEvent())
    events = list(emitter.event_generator())
    assert len(events) == 2

def test_process_batch_emits_events():
    emitter = EventEmitter()
    results = process_batch_parallel(
        [1, 2, 3], lambda x: x * 2, emitter=emitter, action="Doubling"
    )
    events = []
    while not emitter.get_queue().empty():
        events.append(emitter.get_queue().get())
    assert any(e.type == EventType.COMPLETE for e in events)

def test_process_batch_handles_errors():
    emitter = EventEmitter()
    def failing(x):
        if x == 2:
            raise ValueError("fail")
        return x
    results = process_batch_parallel(
        [1, 2, 3], failing, emitter=emitter, action="Test"
    )
    assert len(results) == 3
    assert results[1]["error"] == "fail"
```

### Integration Tests

```python
# tests/test_event_subscriber.py

def test_subscriber_updates_progress():
    emitter = EventEmitter()
    subscriber = EventSubscriber(emitter)
    subscriber.subscribe()
    
    emitter.emit(BatchProgressEvent(current=1, total=3, description="Test"))
    emitter.emit(FileStartEvent(file="a.txt", action="Compress"))
    emitter.emit(FileCompleteEvent(file="a.txt"))
    emitter.emit(CompleteEvent(summary={"successful": 1, "failed": 0, "total": 1}))
    
    subscriber.unsubscribe()
    assert subscriber._stats["success"] == 1
```

---

## Migration Path

1. **Step 1**: Create `common/events.py` with `EventEmitter` and event models.
2. **Step 2**: Refactor `common/concurrent.py` to accept `emitter` instead of `progress`/`task_id`. Keep old parameters as deprecated aliases for one release.
3. **Step 3**: Create `interface/event_subscriber.py`.
4. **Step 4**: Update one command group at a time (start with `cli_images.py` — simplest case).
5. **Step 5**: Update engines to accept optional `emitter` parameter.
6. **Step 6**: Update remaining command groups.
7. **Step 7**: Remove deprecated parameters from `process_batch_parallel`.
8. **Step 8**: Update all tests.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Performance overhead from event emission | Events are simple dict creations; negligible overhead. Callbacks run in the same thread. |
| Breaking existing code that passes `progress`/`task_id` | Keep old parameters as deprecated for one release with a warning. |
| Thread safety in parallel batch processing | Use `threading.Lock` for shared state (already done in new design). |
| Engines that don't adopt events | Events are optional. Engines without emitter support still work fine. |

---

## Success Criteria

- [ ] `common/concurrent.py` has zero Rich imports
- [ ] All batch operations emit standardized events
- [ ] `cli_images.py` fully migrated to event-driven progress
- [ ] All existing tests pass
- [ ] New event system tests pass
- [ ] No regression in CLI output quality (Rich UI looks the same or better)
